import { Request, Response } from "express";
import { query } from "../lib/db";
import { positiveNumber } from "../utils/positiveNumber";
import { sendResponse } from "../utils/response";

const MAX_QUERY_LENGTH = 200;
const MAX_PAGE_SIZE = 100;

/*--GET /api/v1/search?q=acme: keyword search in the saved invoices--*/
// Looks in the invoice number, supplier, customer and file name (small and capital letters are the same).
// The invoice number is also compared without dashes and spaces, so "inv001" finds "INV-001".
// Optional: ?page=2  ?limit=20. Meaning search ("office furniture" finds "chairs") comes in Task 5.
export const searchInvoices = async (req: Request, res: Response) => {
  const q = typeof req.query.q === "string" ? req.query.q.trim() : "";
  const page = req.query.page === undefined ? 1 : positiveNumber(req.query.page);
  const limit = req.query.limit === undefined ? 20 : positiveNumber(req.query.limit);

  if (!q) return sendResponse(res, 400, "Type something to search for, e.g. ?q=acme");
  if (q.length > MAX_QUERY_LENGTH) {
    return sendResponse(res, 400, `The search text is too long (at most ${MAX_QUERY_LENGTH} characters)`);
  }
  if (page === null) return sendResponse(res, 400, "page must be a whole number from 1");
  if (limit === null || limit > MAX_PAGE_SIZE) {
    return sendResponse(res, 400, `limit must be a whole number from 1 to ${MAX_PAGE_SIZE}`);
  }

  // In a LIKE pattern, % and _ are wildcards. A user typing "50%" means the text "50%", so we escape them.
  const pattern = `%${q.replace(/[\\%_]/g, (character) => "\\" + character)}%`;
  // "INV 001" -> "INV001", the same form as the invoice_number_key column
  const numberKey = q.toUpperCase().replace(/[^\p{L}\p{N}]/gu, "");

  const matches = `
    FROM invoices i JOIN documents d ON d.id = i.document_id
    WHERE i.invoice_number ILIKE $1 OR i.supplier_name ILIKE $1 OR i.customer_name ILIKE $1 OR d.filename ILIKE $1
       OR ($2 <> '' AND i.invoice_number_key LIKE '%' || $2 || '%')`;

  const counted = await query(`SELECT count(*)::int AS total ${matches}`, [pattern, numberKey]);
  const total: number = counted.rows[0].total;

  const found = await query(
    `SELECT i.id, i.document_id, d.filename, i.source, i.invoice_number, i.invoice_date, i.supplier_name,
            i.customer_name, i.total, i.currency, i.needs_review,
            -- Where the search text was found, so the website can show it
            CASE WHEN i.invoice_number ILIKE $1 OR ($2 <> '' AND i.invoice_number_key LIKE '%' || $2 || '%') THEN 'invoice number'
                 WHEN i.supplier_name ILIKE $1 THEN 'supplier'
                 WHEN i.customer_name ILIKE $1 THEN 'customer'
                 ELSE 'file name'
            END AS found_in
     ${matches}
     -- Best results first: an exact invoice number, then newest.
     -- (COALESCE: an invoice without a number gives NULL here, and DESC would put NULL first)
     ORDER BY COALESCE(i.invoice_number_key = $2, false) DESC, i.created_at DESC, i.id DESC
     LIMIT $3 OFFSET $4`,
    [pattern, numberKey, limit, (page - 1) * limit]
  );

  return sendResponse(res, 200, `${total} ${total === 1 ? "invoice" : "invoices"} found for "${q}"`, {
    invoices: found.rows,
    page,
    limit,
    total,
    total_pages: Math.ceil(total / limit),
  });
};
