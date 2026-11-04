import { Request, Response } from "express";
import { query, transaction } from "../lib/db";
import { embedSearchWords } from "../lib/embeddings";
import { containsPattern, readFilters } from "../lib/searchFilters";
import { positiveNumber } from "../utils/positiveNumber";
import { sendResponse } from "../utils/response";

const MAX_QUERY_LENGTH = 200;
const MAX_PAGE_SIZE = 100;

/*--Meaning search: which invoices are "close enough"--*/
// Closeness ("similarity") goes from 0 (unrelated) to 1 (the same meaning). With Gemini embeddings,
// even unrelated invoices score about 0.55, and right answers 0.59 to 0.68 (we measured this with
// 12 sample invoices and 12 searches). No single number separates them, so we keep an invoice when:
//   1. it scores at least MIN_SIMILARITY (so nothing is shown when nothing is related at all), and
//   2. it is at most MAX_GAP below the best result (results about as close as the best one).
// On the measured searches this kept all 14 right answers and 4 of the 130 wrong ones.
const MIN_SIMILARITY = 0.58;
const MAX_GAP = 0.03;
const MAX_MEANING_RESULTS = 100; // a meaning search gives at most this many invoices

/*--GET /api/v1/search?q=acme: keyword search in the saved invoices--*/
// Looks in the invoice number, supplier, customer, file name, the line item descriptions and the invoice text
// (small and capital letters are the same). So "chair" finds an invoice with a line "Office chairs".
// The invoice number is also compared without dashes and spaces, so "inv001" finds "INV-001".
// Filters (all optional, see lib/searchFilters.ts): ?date_from= &date_to= &total_min= &total_max= &currency= &supplier= &needs_review=
// With filters, q may be left out: ?currency=EUR gives all EUR invoices. Pages: ?page=2  ?limit=20
// Meaning search: ?q=office furniture&mode=meaning (finds "chairs" too, see meaningSearch below)
export const searchInvoices = async (req: Request, res: Response) => {
  const q = typeof req.query.q === "string" ? req.query.q.trim() : "";
  const page = req.query.page === undefined ? 1 : positiveNumber(req.query.page);
  const limit = req.query.limit === undefined ? 20 : positiveNumber(req.query.limit);
  const mode = req.query.mode ?? "keyword";

  if (mode !== "keyword" && mode !== "meaning") return sendResponse(res, 400, "mode must be keyword or meaning");
  if (mode === "meaning" && !q) {
    return sendResponse(res, 400, "Meaning search needs words to search for, e.g. ?q=office furniture&mode=meaning");
  }

  const filters = readFilters(req.query, 3); // $1 and $2 are used by the search text below
  if ("error" in filters) return sendResponse(res, 400, filters.error);
  if (!q && filters.conditions.length === 0) {
    return sendResponse(res, 400, "Type something to search for, or use a filter, e.g. ?q=acme or ?currency=USD");
  }
  if (q.length > MAX_QUERY_LENGTH) {
    return sendResponse(res, 400, `The search text is too long (at most ${MAX_QUERY_LENGTH} characters)`);
  }
  if (page === null) return sendResponse(res, 400, "page must be a whole number from 1");
  if (limit === null || limit > MAX_PAGE_SIZE) {
    return sendResponse(res, 400, `limit must be a whole number from 1 to ${MAX_PAGE_SIZE}`);
  }
  if (mode === "meaning") return meaningSearch(req, res, q, page, limit);

  // NULL when there is no search text: then nothing is "found in" a field, and only the filters decide
  const pattern = q ? containsPattern(q) : null;
  // "INV 001" -> "INV001", the same form as the invoice_number_key column
  const numberKey = q.toUpperCase().replace(/[^\p{L}\p{N}]/gu, "");

  // Step 1 (WITH ... AS): for every invoice, work out WHERE the search text was found (or NULL = not found).
  // The first match in this list wins, e.g. an invoice whose supplier AND text contain "acme" is found in "supplier".
  // Step 2 (WHERE ...): keep only the invoices where it was found (or all, without search text) that pass the filters.
  const matches = `
    WITH checked AS (
      SELECT i.*, d.filename,
             -- The first line item whose description contains the search text (NULL if none)
             (SELECT li.description FROM line_items li
               WHERE li.invoice_id = i.id AND li.description ILIKE $1
               ORDER BY li.position LIMIT 1) AS matched_line
        FROM invoices i JOIN documents d ON d.id = i.document_id
    ), found AS (
      SELECT checked.*,
             CASE WHEN invoice_number ILIKE $1 OR ($2 <> '' AND invoice_number_key LIKE '%' || $2 || '%') THEN 'invoice number'
                  WHEN supplier_name ILIKE $1 THEN 'supplier'
                  WHEN customer_name ILIKE $1 THEN 'customer'
                  WHEN filename ILIKE $1 THEN 'file name'
                  WHEN matched_line IS NOT NULL THEN 'line item'
                  WHEN text ILIKE $1 THEN 'invoice text'
             END AS found_in
        FROM checked
    )
    SELECT * FROM found
     WHERE ($1::text IS NULL OR found_in IS NOT NULL)
       ${filters.conditions.map((condition) => `AND ${condition}`).join(" ")}`;
  const values = [pattern, numberKey, ...filters.values];
  // The next free placeholder numbers, for the search text, limit and offset of the second query
  const next = values.length + 1;

  const counted = await query(`SELECT count(*)::int AS total FROM (${matches}) results`, values);
  const total: number = counted.rows[0].total;

  const found = await query(
    `SELECT id, document_id, filename, source, invoice_number, invoice_date, supplier_name,
            customer_name, total, currency, needs_review, found_in,
            -- What to show the user: the matching line, or a short piece of the text around the match
            CASE WHEN found_in = 'line item' THEN matched_line
                 WHEN found_in = 'invoice text'
                   THEN substr(text, greatest(1, strpos(lower(text), lower($${next})) - 40), 100)
            END AS matched_text
       FROM (${matches}) results
     -- Best results first: an exact invoice number, then a match in a main field, then in a line, then in the text,
     -- then newest. (COALESCE: an invoice without a number gives NULL here, and DESC would put NULL first)
     ORDER BY COALESCE($2 <> '' AND invoice_number_key = $2, false) DESC,
              CASE found_in WHEN 'line item' THEN 1 WHEN 'invoice text' THEN 2 ELSE 0 END,
              created_at DESC, id DESC
     LIMIT $${next + 1} OFFSET $${next + 2}`,
    [...values, q, limit, (page - 1) * limit]
  );

  const what = `${total} ${total === 1 ? "invoice" : "invoices"} found`;
  return sendResponse(res, 200, q ? `${what} for "${q}"` : what, {
    invoices: found.rows,
    filters: filters.used,
    page,
    limit,
    total,
    total_pages: Math.ceil(total / limit),
  });
};

/*--GET /api/v1/search?q=office furniture&mode=meaning: search by meaning--*/
// 1. Gemini turns the search words into 768 numbers (lib/embeddings.ts)
// 2. The database compares them with the numbers of every invoice (Step 5) and keeps the closest ones
// The filters work here too, e.g. &currency=USD
const meaningSearch = async (req: Request, res: Response, q: string, page: number, limit: number) => {
  // The same filters as keyword search, but here $1 to $4 are used by the meaning query
  const filters = readFilters(req.query, 5);
  if ("error" in filters) return sendResponse(res, 400, filters.error);

  let search: { model: string; numbers: number[] };
  try {
    search = await embedSearchWords(q);
  } catch (error) {
    const reason = (error instanceof Error ? error.message : String(error)).replace(/\.$/, ""); // no ".." below
    return sendResponse(res, 503,
      `Meaning search can't be used right now: ${reason}. Keyword search still works: leave out mode=meaning.`);
  }

  const kept = await transaction(async (client) => {
    // With filters, the fast index (HNSW) could otherwise give back fewer results than exist.
    // This setting makes it keep looking until it has enough. "LOCAL" = only for this search.
    await client.query("SET LOCAL hnsw.iterative_scan = strict_order");
    const found = await client.query(
      `WITH closest AS (
         -- "<=>" is the cosine distance (0 = the same meaning); similarity = 1 - distance
         SELECT i.id, i.document_id, d.filename, i.source, i.invoice_number, i.invoice_date, i.supplier_name,
                i.customer_name, i.total, i.currency, i.needs_review, 1 - (e.embedding <=> $1::vector) AS similarity
           FROM invoice_embeddings e
           JOIN invoices i ON i.id = e.invoice_id
           JOIN documents d ON d.id = i.document_id
          -- Numbers from different AI models can't be compared, so only the same model as the search
          WHERE e.model = $2 ${filters.conditions.map((condition) => `AND ${condition}`).join(" ")}
          ORDER BY e.embedding <=> $1::vector
          LIMIT ${MAX_MEANING_RESULTS}
       )
       SELECT * FROM closest
        WHERE similarity >= $3 AND similarity >= (SELECT max(similarity) FROM closest) - $4
        ORDER BY similarity DESC, id DESC`,
      [`[${search.numbers.join(",")}]`, search.model, MIN_SIMILARITY, MAX_GAP, ...filters.values]
    );
    return found.rows;
  });

  // Invoices that are not in meaning search yet (Step 5: it failed earlier and is added later)
  const missing = await query(
    `SELECT count(*)::int AS count FROM invoices i
      WHERE i.error IS NULL AND NOT EXISTS (SELECT 1 FROM invoice_embeddings e WHERE e.invoice_id = i.id AND e.model = $1)`,
    [search.model]);

  // At most 100 results, so the pages are cut here
  const invoices = kept.slice((page - 1) * limit, page * limit).map((invoice) => ({
    ...invoice,
    found_in: "meaning",
    similarity: Number(invoice.similarity.toFixed(3)), // e.g. 0.652
  }));
  const total = kept.length;
  return sendResponse(res, 200, `${total} ${total === 1 ? "invoice" : "invoices"} found for "${q}" (by meaning)`, {
    invoices,
    filters: filters.used,
    not_in_meaning_search: missing.rows[0].count,
    page,
    limit,
    total,
    total_pages: Math.ceil(total / limit),
  });
};
