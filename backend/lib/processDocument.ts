import fs from "fs";
import path from "path";
import { PoolClient } from "pg";
import envConfig from "../config/env.config";
import { query, transaction } from "./db";
import { AiFileResult, AiInvoice, extractWithAi } from "./aiService";
import { addValidationError, invoicesPointingTo, isDuplicateRule, markDuplicates, refreshNeedsReview } from "./duplicates";
import { addHistory } from "./history";

/*--The background work for one uploaded document--*/
// 1. status "processing"   2. send the file to the AI service   3. save the invoices and their problems
// 4. look for duplicates in all saved invoices   5. status "done" (or "failed" with the reason)
// `attempt` and `attempts` come from the queue: e.g. attempt 2 of 3.
export const processDocument = async (documentId: number, attempt: number, attempts: number) => {
  const found = await query("SELECT * FROM documents WHERE id = $1", [documentId]);
  const document = found.rows[0];
  if (!document) return; // deleted in the meantime: nothing to do

  const start = Date.now();
  await query("UPDATE documents SET status = 'processing', started_at = now(), error = NULL WHERE id = $1", [documentId]);
  await addHistory(documentId, "processing",
    attempt > 1 ? `Processing started (attempt ${attempt} of ${attempts})` : "Processing started");

  let data: Buffer;
  try {
    data = await fs.promises.readFile(path.join(envConfig.BACKEND_FOLDER, document.file_path));
  } catch {
    return markFailed(documentId, "The uploaded file is missing on the server. Please upload it again.");
  }

  let result: AiFileResult;
  try {
    result = await extractWithAi(data, document.filename);
  } catch (error) {
    // The AI service is down or crashed. That is usually temporary, so the queue tries again.
    const reason = error instanceof Error ? error.message : String(error);
    if (attempt >= attempts) {
      return markFailed(documentId, `Tried ${attempts} times, but ${reason}.`);
    }
    await query("UPDATE documents SET status = 'pending' WHERE id = $1", [documentId]);
    await addHistory(documentId, "retry", `Attempt ${attempt} of ${attempts} failed: ${reason}. Trying again soon.`);
    throw error; // tells the queue: try this job again later
  }

  const seconds = (Date.now() - start) / 1000;

  // The file itself could not be read (broken, password-protected, ...). Trying again won't help.
  if (result.error) {
    return markFailed(documentId, result.error, result);
  }
  // Every invoice failed in the AI (e.g. the free Gemini limit is used up): the document failed.
  const failedInvoices = result.invoices.filter((invoice) => invoice.error);
  if (result.invoices.length > 0 && failedInvoices.length === result.invoices.length) {
    return markFailed(documentId, failedInvoices[0].error as string, result);
  }

  await saveResults(documentId, result, seconds);
};

/*--Save everything in one transaction, so a crash never leaves half-saved results--*/
const saveResults = async (documentId: number, result: AiFileResult, seconds: number) => {
  await transaction(async (client) => {
    await removeOldResults(client, documentId);

    let needReview = 0;
    for (const invoice of result.invoices) {
      const { invoiceId, hasProblems } = await saveInvoice(client, documentId, invoice);
      const hasDuplicates = await markDuplicates(client, invoiceId);
      if (hasProblems || hasDuplicates) needReview += 1;
    }

    await client.query(
      `UPDATE documents SET status = 'done', file_type = $2, warnings = $3, invoice_count = $4,
              processing_seconds = $5, finished_at = now()
       WHERE id = $1`,
      [documentId, result.file_type, JSON.stringify(result.warnings), result.invoices.length, seconds]
    );
    const count = result.invoices.length;
    await addHistory(documentId, "done",
      `Done in ${seconds.toFixed(1)} seconds: ${count} ${count === 1 ? "invoice" : "invoices"} found, ${needReview} need review`,
      client);
  });
};

/*--Results of an earlier run (when a document is processed again)--*/
// Deleting them also deletes the duplicate problems they caused on other invoices;
// those other invoices then need review only if they still have other problems.
const removeOldResults = async (client: PoolClient, documentId: number) => {
  const old = await client.query("SELECT id FROM invoices WHERE document_id = $1", [documentId]);
  const oldIds = old.rows.map((row) => row.id);
  if (oldIds.length === 0) return;
  const others = await invoicesPointingTo(client, oldIds);
  await client.query("DELETE FROM invoices WHERE document_id = $1", [documentId]);
  await refreshNeedsReview(client, others);
};

const saveInvoice = async (client: PoolClient, documentId: number, invoice: AiInvoice) => {
  const value = (name: string) => invoice.fields[name]?.value ?? null;
  // Status, evidence and note of every field (the values themselves go in their own columns)
  const fieldDetails = Object.fromEntries(
    Object.entries(invoice.fields).map(([name, field]) => [name, { status: field.status, evidence: field.evidence, note: field.note }])
  );
  // Duplicates are found by the database (markDuplicates), so the AI's own duplicate problems are left out
  const problems = invoice.validation_errors.filter((error) => !isDuplicateRule(error.rule));

  const saved = await client.query(
    `INSERT INTO invoices (document_id, source, method, ai_model, error, invoice_number, invoice_date, supplier_name,
                           customer_name, subtotal, tax, total, currency, field_details, needs_review, warnings, text)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
     RETURNING id`,
    [documentId, invoice.source, invoice.method, invoice.ai_model, invoice.error, value("invoice_number"),
     value("invoice_date"), value("supplier_name"), value("customer_name"), value("subtotal"), value("tax"),
     value("total"), value("currency"), JSON.stringify(fieldDetails), problems.length > 0,
     JSON.stringify(invoice.warnings), invoice.text]
  );
  const invoiceId: number = saved.rows[0].id;

  for (const [index, item] of invoice.line_items.entries()) {
    await client.query(
      `INSERT INTO line_items (invoice_id, position, description, quantity, unit_price, amount, evidence, problems)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
      [invoiceId, index + 1, item.description, item.quantity, item.unit_price, item.amount, item.evidence,
       JSON.stringify(item.problems)]
    );
  }
  for (const error of problems) {
    await addValidationError(client, invoiceId, error.field, error.rule, error.message);
  }
  return { invoiceId, hasProblems: problems.length > 0 };
};

const markFailed = async (documentId: number, error: string, result?: AiFileResult) => {
  await query(
    `UPDATE documents SET status = 'failed', error = $2, file_type = COALESCE($3, file_type),
            warnings = COALESCE($4, warnings), finished_at = now()
     WHERE id = $1`,
    [documentId, error, result?.file_type ?? null, result ? JSON.stringify(result.warnings) : null]
  );
  await addHistory(documentId, "failed", `Failed: ${error}`);
};
