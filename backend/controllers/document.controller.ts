import fs from "fs";
import path from "path";
import { Request, Response } from "express";
import envConfig from "../config/env.config";
import { query, transaction } from "../lib/db";
import { addHistory } from "../lib/history";
import { withDetails } from "../lib/invoiceDetails";
import { addDocumentJob } from "../lib/queue";
import { isSupported } from "../lib/upload";
import { positiveNumber } from "../utils/positiveNumber";
import { sendResponse } from "../utils/response";

/*--POST /api/v1/documents: upload one or more files--*/
// The files are saved and get the status "pending". The slow work (OCR + AI) happens later in the
// background, so this answers at once.
export const uploadDocuments = async (req: Request, res: Response) => {
  const files = (req.files as Express.Multer.File[] | undefined) ?? [];
  if (files.length === 0) {
    return sendResponse(res, 400, "No files were uploaded. Send them in the form field 'files'.");
  }

  // Check every file. A bad file is rejected, but the good ones in the same upload are still accepted.
  const accepted: Express.Multer.File[] = [];
  const rejected: { filename: string; reason: string }[] = [];
  for (const file of files) {
    const reason = !isSupported(file.originalname)
      ? "This file type is not supported. Use PDF, JPG, PNG, TIFF, XLSX, XLS or CSV."
      : file.size === 0
        ? "The file is empty."
        : null;
    if (reason) {
      rejected.push({ filename: file.originalname, reason });
      await fs.promises.unlink(file.path); // don't keep files we won't process
    } else {
      accepted.push(file);
    }
  }

  if (accepted.length === 0) {
    return sendResponse(res, 400, "None of the files can be processed.", { documents: [], rejected });
  }

  try {
    // One transaction: either every accepted file gets its row, or none does.
    const documents = await transaction(async (client) => {
      const saved = [];
      for (const file of accepted) {
        const result = await client.query(
          `INSERT INTO documents (filename, file_path, file_size) VALUES ($1, $2, $3)
           RETURNING id, filename, file_size, status, created_at`,
          [file.originalname, path.relative(envConfig.BACKEND_FOLDER, file.path), file.size]
        );
        const document = result.rows[0];
        await client.query(
          `INSERT INTO processing_history (document_id, step, message) VALUES ($1, 'uploaded', $2)`,
          [document.id, `Uploaded "${file.originalname}" (${readableSize(file.size)})`]
        );
        saved.push(document);
      }
      return saved;
    });

    // Add the documents to the background queue. If Redis is down right now, the documents stay
    // "pending" and are put in the queue again when the server restarts (queueUnfinishedDocuments).
    for (const document of documents) {
      await addDocumentJob(document.id).catch((error) =>
        console.error(`Document ${document.id} could not be added to the queue:`, error));
    }

    const message =
      `${documents.length} ${documents.length === 1 ? "file was" : "files were"} received and will be processed in the background.` +
      (rejected.length ? ` ${rejected.length} rejected.` : "");
    return sendResponse(res, 201, message, { documents, rejected });
  } catch (error) {
    // Nothing was saved in the database, so the files on disk are not needed either.
    await Promise.all(accepted.map((file) => fs.promises.unlink(file.path).catch(() => {})));
    throw error;
  }
};

const STATUSES = ["pending", "processing", "done", "failed"];
const MAX_PAGE_SIZE = 100;

/*--GET /api/v1/documents: the list of documents--*/
// Filters (all optional): ?status=failed  ?needs_review=true  ?page=2  ?limit=20
// Newest first. Each document says how many invoices it has and how many need review.
export const listDocuments = async (req: Request, res: Response) => {
  const { status, needs_review } = req.query;
  const page = req.query.page === undefined ? 1 : positiveNumber(req.query.page);
  const limit = req.query.limit === undefined ? 20 : positiveNumber(req.query.limit);

  if (status !== undefined && !STATUSES.includes(String(status))) {
    return sendResponse(res, 400, `status must be one of: ${STATUSES.join(", ")}`);
  }
  if (needs_review !== undefined && needs_review !== "true" && needs_review !== "false") {
    return sendResponse(res, 400, "needs_review must be true or false");
  }
  if (page === null) return sendResponse(res, 400, "page must be a whole number from 1");
  if (limit === null || limit > MAX_PAGE_SIZE) {
    return sendResponse(res, 400, `limit must be a whole number from 1 to ${MAX_PAGE_SIZE}`);
  }

  // Build the WHERE part from the filters that were given. The values go in as $1, $2 ... (safe).
  const conditions: string[] = [];
  const values: unknown[] = [];
  if (status !== undefined) {
    values.push(status);
    conditions.push(`d.status = $${values.length}`);
  }
  if (needs_review !== undefined) {
    const exists = "EXISTS (SELECT 1 FROM invoices i WHERE i.document_id = d.id AND i.needs_review)";
    conditions.push(needs_review === "true" ? exists : `NOT ${exists}`);
  }
  const where = conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";

  const counted = await query(`SELECT count(*)::int AS total FROM documents d ${where}`, values);
  const total: number = counted.rows[0].total;

  const found = await query(
    `SELECT d.id, d.filename, d.file_type, d.file_size, d.status, d.error, d.invoice_count,
            (SELECT count(*)::int FROM invoices i WHERE i.document_id = d.id AND i.needs_review) AS review_count,
            d.processing_seconds, d.created_at, d.finished_at
     FROM documents d ${where}
     ORDER BY d.created_at DESC, d.id DESC
     LIMIT $${values.length + 1} OFFSET $${values.length + 2}`,
    [...values, limit, (page - 1) * limit]
  );

  return sendResponse(res, 200, `${total} ${total === 1 ? "document" : "documents"} found`, {
    documents: found.rows,
    page,
    limit,
    total,
    total_pages: Math.ceil(total / limit),
  });
};

/*--GET /api/v1/documents/:id: one document with its status, invoices, problems and history--*/
// The website calls this every few seconds while a document is "pending" or "processing".
export const getDocument = async (req: Request, res: Response) => {
  const id = positiveNumber(req.params.id);
  if (id === null) return sendResponse(res, 400, "The document id must be a whole number");

  const found = await query(
    `SELECT id, filename, file_type, file_size, status, error, warnings, invoice_count, processing_seconds,
            created_at, started_at, finished_at
     FROM documents WHERE id = $1`, [id]);
  const document = found.rows[0];
  if (!document) return sendResponse(res, 404, `Document ${id} was not found`);

  const invoices = await query("SELECT * FROM invoices WHERE document_id = $1 ORDER BY id", [id]);
  const history = await query(
    "SELECT id, step, message, details, invoice_id, created_at FROM processing_history WHERE document_id = $1 ORDER BY id",
    [id]);

  return sendResponse(res, 200, `Document ${id} is ${document.status}`, {
    ...document,
    invoices: await withDetails(invoices.rows),
    history: history.rows,
  });
};

/*--POST /api/v1/documents/:id/reprocess: try a document again--*/
// For a document that failed (e.g. the AI service was down, or the free Gemini limit was used up), or that
// is done but has invoices the AI could not read. The file was kept, so it doesn't need to be uploaded again.
// A document that is done without failures is not processed again: that would throw away its
// corrections and use the free Gemini limit for nothing.
export const reprocessDocument = async (req: Request, res: Response) => {
  const id = positiveNumber(req.params.id);
  if (id === null) return sendResponse(res, 400, "The document id must be a whole number");

  const found = await query(
    `SELECT d.id, d.filename, d.file_path, d.status,
            (SELECT count(*)::int FROM invoices i WHERE i.document_id = d.id AND i.error IS NOT NULL) AS failed_invoices
     FROM documents d WHERE d.id = $1`, [id]);
  const document = found.rows[0];
  if (!document) return sendResponse(res, 404, `Document ${id} was not found`);

  if (document.status === "pending" || document.status === "processing") {
    return sendResponse(res, 409, `Document ${id} is already ${document.status}. Wait until it is done.`);
  }
  if (document.status === "done" && document.failed_invoices === 0) {
    return sendResponse(res, 409,
      `Document ${id} was processed without failures, so there is nothing to try again.`);
  }
  if (!fs.existsSync(path.join(envConfig.BACKEND_FOLDER, document.file_path))) {
    return sendResponse(res, 410, `The file of document ${id} is missing on the server. Please upload it again.`);
  }

  const reason = document.status === "failed"
    ? "it failed"
    : `${document.failed_invoices} ${document.failed_invoices === 1 ? "invoice" : "invoices"} could not be read`;
  try {
    await transaction(async (client) => {
      await client.query(
        `UPDATE documents SET status = 'pending', error = NULL, started_at = NULL, finished_at = NULL,
                processing_seconds = NULL
         WHERE id = $1`, [id]);
      await addHistory(id, "reprocess", `Sent to be processed again (${reason})`, client);
      // Added before the transaction is saved: if the queue can't be reached, nothing changes.
      await addDocumentJob(id);
    });
  } catch (error) {
    console.error(error);
    return sendResponse(res, 503, "The job queue can't be reached right now. Please try again later.");
  }

  return sendResponse(res, 202, `Document ${id} will be processed again in the background.`, {
    id, filename: document.filename, status: "pending",
  });
};

const readableSize = (bytes: number) =>
  bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
