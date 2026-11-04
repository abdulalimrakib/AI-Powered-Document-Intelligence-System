import { query } from "./db";

// The invoice fields, in the order they are shown (the same as INVOICE_FIELDS in AI/extract_invoice.py)
export const INVOICE_FIELDS = [
  "invoice_number", "invoice_date", "supplier_name", "customer_name", "subtotal", "tax", "total", "currency",
];

/*--Turn invoice rows from the database into the shape the website shows--*/
// Every field becomes { value, status, evidence, note } (the same shape as the AI service gives),
// and each invoice gets its line items and its problems (validation errors).
export const withDetails = async (invoiceRows: any[]) => {
  if (invoiceRows.length === 0) return [];
  const ids = invoiceRows.map((invoice) => invoice.id);

  // Two queries for all invoices together, instead of two per invoice
  const lineItems = await query(
    `SELECT invoice_id, position, description, quantity, unit_price, amount, evidence, problems
     FROM line_items WHERE invoice_id = ANY($1) ORDER BY position`, [ids]);
  const errors = await query(
    `SELECT invoice_id, id, field, rule, message FROM validation_errors WHERE invoice_id = ANY($1) ORDER BY id`, [ids]);

  return invoiceRows.map((row) => ({
    id: row.id,
    document_id: row.document_id,
    source: row.source,
    method: row.method,
    ai_model: row.ai_model,
    error: row.error,
    fields: Object.fromEntries(
      INVOICE_FIELDS.map((name) => [name, {
        value: row[name],
        status: row.field_details[name]?.status ?? (row[name] === null ? "missing" : "found"),
        evidence: row.field_details[name]?.evidence ?? null,
        note: row.field_details[name]?.note ?? null,
      }])
    ),
    line_items: lineItems.rows
      .filter((item) => item.invoice_id === row.id)
      .map(({ invoice_id, ...item }) => item),
    validation_errors: errors.rows
      .filter((error) => error.invoice_id === row.id)
      .map(({ invoice_id, ...error }) => error),
    needs_review: row.needs_review,
    reviewed_at: row.reviewed_at, // when a person marked it as checked (null = not checked)
    warnings: row.warnings,
    updated_at: row.updated_at,
  }));
};
