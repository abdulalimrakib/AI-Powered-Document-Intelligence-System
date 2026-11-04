import { Request, Response } from "express";
import { CorrectionRejected, validateWithAi, AiInvoice } from "../lib/aiService";
import { query, transaction } from "../lib/db";
import { addValidationError, invoicesPointingTo, isDuplicateRule, markDuplicates, refreshNeedsReview } from "../lib/duplicates";
import { embeddingFailedMessage, fillMissingEmbeddings } from "../lib/embeddings";
import { addHistory } from "../lib/history";
import { INVOICE_FIELDS, withDetails } from "../lib/invoiceDetails";
import { positiveNumber } from "../utils/positiveNumber";
import { sendResponse } from "../utils/response";

const MAX_VALUE_LENGTH = 500;

/*--PATCH /api/v1/invoices/:id: a person corrects values, or marks the invoice as checked--*/
// Body examples:
//   { "fields": { "total": "1,150.00", "supplier_name": "Acme Ltd" } }   correct values ("" or null empties a field)
//   { "reviewed": true }                                                 "I checked it, it is fine" (e.g. a discount)
// A corrected value is cleaned and the invoice is checked again with the same rules as before
// (Task 2 + Task 3, in the AI service). The change is written in the document's history.
export const correctInvoice = async (req: Request, res: Response) => {
  const id = positiveNumber(req.params.id);
  if (id === null) return sendResponse(res, 400, "The invoice id must be a whole number");

  /*--Check the request--*/
  const { fields, reviewed } = req.body ?? {};
  if (fields !== undefined && (typeof fields !== "object" || fields === null || Array.isArray(fields))) {
    return sendResponse(res, 400, 'fields must be an object, e.g. { "total": "1,150.00" }');
  }
  const corrections: Record<string, string | null> = fields ?? {};
  for (const [name, value] of Object.entries(corrections)) {
    if (!INVOICE_FIELDS.includes(name)) {
      return sendResponse(res, 400, `'${name}' is not an invoice field. Fields: ${INVOICE_FIELDS.join(", ")}`);
    }
    if (value !== null && typeof value !== "string") {
      return sendResponse(res, 400, `${readable(name)} must be text (or null to empty it)`);
    }
    if (value !== null && value.length > MAX_VALUE_LENGTH) {
      return sendResponse(res, 400, `${readable(name)} is too long (at most ${MAX_VALUE_LENGTH} characters)`);
    }
  }
  if (reviewed !== undefined && typeof reviewed !== "boolean") {
    return sendResponse(res, 400, "reviewed must be true or false");
  }
  if (Object.keys(corrections).length === 0 && reviewed === undefined) {
    return sendResponse(res, 400, 'Nothing to change. Send { "fields": { ... } } and/or { "reviewed": true }');
  }

  const found = await query("SELECT * FROM invoices WHERE id = $1", [id]);
  const row = found.rows[0];
  if (!row) return sendResponse(res, 404, `Invoice ${id} was not found`);
  const [invoice] = await withDetails([row]);

  /*--Clean the new values and check the invoice again (AI service)--*/
  let checked: AiInvoice | null = null;
  if (Object.keys(corrections).length > 0) {
    try {
      checked = await validateWithAi(
        { fields: invoice.fields, line_items: invoice.line_items, text: row.text }, corrections);
    } catch (error) {
      if (error instanceof CorrectionRejected) return sendResponse(res, 400, error.message);
      const reason = error instanceof Error ? error.message : String(error);
      return sendResponse(res, 503, `The correction can't be checked right now: ${reason}. Please try again later.`);
    }
  }

  /*--Save it all in one transaction--*/
  await transaction(async (client) => {
    const notes: string[] = [];
    let changes: { field: string; old: string | null; new: string | null }[] = [];

    if (checked) {
      const result = checked;
      changes = Object.keys(corrections).map((name) => ({
        field: name, old: invoice.fields[name].value, new: result.fields[name].value,
      }));
      // The meaning numbers describe the old values: remove them (they are made again below)
      await client.query("DELETE FROM invoice_embeddings WHERE invoice_id = $1", [id]);
      // The old problems (also duplicates in both directions) are replaced by the new check
      const others = await invoicesPointingTo(client, [id]);
      await client.query("DELETE FROM validation_errors WHERE invoice_id = $1 OR related_invoice_id = $1", [id]);

      const value = (name: string) => result.fields[name].value;
      const fieldDetails = Object.fromEntries(INVOICE_FIELDS.map((name) => [name, {
        status: result.fields[name].status, evidence: result.fields[name].evidence, note: result.fields[name].note,
      }]));
      await client.query(
        `UPDATE invoices SET invoice_number = $2, invoice_date = $3, supplier_name = $4, customer_name = $5,
                subtotal = $6, tax = $7, total = $8, currency = $9, field_details = $10,
                reviewed_at = NULL, updated_at = now()
         WHERE id = $1`,
        [id, value("invoice_number"), value("invoice_date"), value("supplier_name"), value("customer_name"),
         value("subtotal"), value("tax"), value("total"), value("currency"), JSON.stringify(fieldDetails)]
      );
      for (const problem of result.validation_errors.filter((error) => !isDuplicateRule(error.rule))) {
        await addValidationError(client, id, problem.field, problem.rule, problem.message);
      }
      // This invoice, and the ones that were its duplicates before: do they still need review?
      await refreshNeedsReview(client, [id, ...others]);
      // Then look for duplicates again (e.g. the invoice number changed)
      await markDuplicates(client, id);
      notes.push("Corrected by hand: " + changes
        .map((change) => `${readable(change.field)} ${change.old ?? "(empty)"} → ${change.new ?? "(empty)"}`)
        .join("; "));
    }

    if (reviewed === true) {
      await client.query("UPDATE invoices SET reviewed_at = now(), needs_review = false, updated_at = now() WHERE id = $1", [id]);
      notes.push("Marked as checked by a person");
    } else if (reviewed === false) {
      await client.query("UPDATE invoices SET reviewed_at = NULL, updated_at = now() WHERE id = $1", [id]);
      await refreshNeedsReview(client, [id]);
      notes.push("Marked as not checked");
    }

    const name = invoice.fields.invoice_number.value ?? `(${invoice.source})`;
    await addHistory(row.document_id, checked ? "corrected" : "reviewed", `Invoice ${name}: ${notes.join(". ")}`,
      client, id, { changes, reviewed: reviewed ?? null });
  });

  // Meaning search, with the new values. If it fails, the correction is still saved.
  if (checked) {
    const embedded = await fillMissingEmbeddings([id]);
    if (embedded.error) {
      await addHistory(row.document_id, "meaning search", embeddingFailedMessage(embedded.error), undefined, id);
    }
  }

  const updated = await query("SELECT * FROM invoices WHERE id = $1", [id]);
  const [result] = await withDetails(updated.rows);
  return sendResponse(res, 200,
    result.needs_review ? "Saved. The invoice still needs review." : "Saved. The invoice has no open problems.",
    result);
};

const readable = (field: string) => field.replace(/_/g, " "); // "invoice_date" -> "invoice date"
