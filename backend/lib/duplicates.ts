import { PoolClient } from "pg";
import { addHistory } from "./history";

// The rules from AI/validate_invoice.py (compare_invoices), done here because only the database
// knows all the invoices that were saved before:
//   same invoice number + same supplier                      -> duplicate
//   same invoice number, supplier unknown on one of them     -> possible duplicate
//   different number, but same supplier, date and total      -> possible duplicate
const DUPLICATE_RULES = ["duplicate_invoice", "possible_duplicate"];

/*--Find the invoices that are the same as this one, anywhere in the database--*/
// Both invoices get the problem (each pointing to the other, with related_invoice_id) and both need review.
// Returns true when a duplicate was found.
export const markDuplicates = async (client: PoolClient, invoiceId: number): Promise<boolean> => {
  const matches = await client.query(
    `SELECT * FROM (
       SELECT old.id AS old_id, old.source AS old_source, old_document.filename AS old_filename,
              old.document_id AS old_document_id, old.invoice_number AS old_number,
              new.source AS new_source, new_document.filename AS new_filename, new.document_id AS new_document_id,
              CASE
                WHEN COALESCE(new.invoice_number_key, '') <> '' AND old.invoice_number_key = new.invoice_number_key THEN
                  CASE
                    WHEN COALESCE(new.supplier_key, '') <> '' AND old.supplier_key = new.supplier_key THEN 'same number and supplier'
                    WHEN COALESCE(new.supplier_key, '') = '' OR COALESCE(old.supplier_key, '') = '' THEN 'same number'
                  END
                WHEN COALESCE(new.supplier_key, '') <> '' AND old.supplier_key = new.supplier_key
                     AND old.invoice_date = new.invoice_date AND old.total = new.total THEN 'same values'
              END AS match
       FROM invoices new
       JOIN documents new_document ON new_document.id = new.document_id
       JOIN invoices old ON old.id <> new.id
                        AND (old.invoice_number_key = new.invoice_number_key OR old.supplier_key = new.supplier_key)
       JOIN documents old_document ON old_document.id = old.document_id
       WHERE new.id = $1
     ) AS candidates
     WHERE match IS NOT NULL
     ORDER BY old_id`,
    [invoiceId]
  );

  for (const row of matches.rows) {
    const [rule, reason] =
      row.match === "same number and supplier"
        ? ["duplicate_invoice", "duplicate: same supplier and invoice number"]
        : row.match === "same number"
          ? ["possible_duplicate", "possible duplicate: same invoice number (supplier unknown)"]
          : ["possible_duplicate", "possible duplicate: same supplier, date and total"];
    // Say where the other one is: in the same file, or in a file uploaded earlier or later
    const sameFile = row.old_document_id === row.new_document_id;
    const oldIsEarlier = row.old_document_id < row.new_document_id;
    const whenOld = sameFile ? "" : oldIsEarlier ? " (uploaded earlier)" : " (uploaded later)";
    const whenNew = sameFile ? "" : oldIsEarlier ? " (uploaded later)" : " (uploaded earlier)";

    await addValidationError(client, invoiceId, "invoice_number", rule,
      `${reason} as ${row.old_filename}, ${row.old_source}${whenOld}`, row.old_id);
    await addValidationError(client, row.old_id, "invoice_number", rule,
      `${reason} as ${row.new_filename}, ${row.new_source}${whenNew}`, invoiceId);
    await client.query("UPDATE invoices SET needs_review = true, updated_at = now() WHERE id IN ($1, $2)",
      [invoiceId, row.old_id]);
    if (!sameFile) {
      // The other document changed too, so its history says why
      await addHistory(row.old_document_id, "duplicate",
        `Invoice ${row.old_number ?? `(${row.old_source})`} needs review: ${reason} as ${row.new_filename}${whenNew}`,
        client, row.old_id);
    }
  }
  return matches.rows.length > 0;
};

/*--Duplicates are found by the database, so the ones from the AI service are left out--*/
// (the AI service only compares invoices inside one file; the database compares with everything)
export const isDuplicateRule = (rule: string) => DUPLICATE_RULES.includes(rule);

/*--Invoices that pointed to these invoices as a duplicate--*/
// Call before deleting or changing the invoices; afterwards pass the ids to refreshNeedsReview().
export const invoicesPointingTo = async (client: PoolClient, invoiceIds: number[]): Promise<number[]> => {
  const found = await client.query(
    `SELECT DISTINCT invoice_id FROM validation_errors
     WHERE related_invoice_id = ANY($1) AND NOT (invoice_id = ANY($1))`, [invoiceIds]);
  return found.rows.map((row) => row.invoice_id);
};

/*--After problems were removed: an invoice needs review only if it still has problems--*/
// (and nobody has marked it as checked)
export const refreshNeedsReview = (client: PoolClient, invoiceIds: number[]) =>
  client.query(
    `UPDATE invoices i SET needs_review = EXISTS (SELECT 1 FROM validation_errors e WHERE e.invoice_id = i.id)
                                          AND i.reviewed_at IS NULL,
                           updated_at = now()
     WHERE i.id = ANY($1)`, [invoiceIds]);

export const addValidationError = (client: PoolClient, invoiceId: number, field: string | null, rule: string,
                                   message: string, relatedInvoiceId: number | null = null) =>
  client.query(
    "INSERT INTO validation_errors (invoice_id, field, rule, message, related_invoice_id) VALUES ($1, $2, $3, $4, $5)",
    [invoiceId, field, rule, message, relatedInvoiceId]);
