import { embedWithAi } from "./aiService";
import { query } from "./db";

const MAX_TEXTS = 100; // the AI service takes at most 100 texts in one request
const TEXT_PART = 1_000; // how much of the invoice text to use when it has no line items

/*--The short text whose meaning we store for an invoice--*/
// e.g. "From: Acme Ltd. Bought: Office chairs; Desk lamps"
// Only the words that say what the invoice is about: who sent it and what was bought.
// Left out: the invoice number, customer, amounts and dates. Keyword search and the filters find those,
// and we measured that they make meaning search worse: the same customer on every invoice makes
// all invoices look alike (the right answer was then less clearly first).
export const invoiceSummary = (invoice: {
  supplier_name: string | null; text: string | null; descriptions: string[];
}): string | null => {
  const parts: string[] = [];
  if (invoice.supplier_name) parts.push(`From: ${invoice.supplier_name}`);
  if (invoice.descriptions.length > 0) {
    parts.push(`Bought: ${invoice.descriptions.join("; ")}`);
  } else if (invoice.text?.trim()) {
    // No line items (e.g. a simple receipt): the start of the text says what it is about
    parts.push(`Text: ${invoice.text.trim().slice(0, TEXT_PART)}`);
  }
  return parts.length > 0 ? parts.join(". ") : null;
};

/*--Make and save embeddings for invoices that don't have one yet--*/
// `first`: invoice ids to do first (e.g. the ones just processed). Older invoices without an embedding
// (because an earlier try failed) are done in the same request, so they are filled in automatically.
// Never throws: meaning search is extra, and must never make a good invoice fail.
// Returns how many were saved, and the reason when it failed.
export const fillMissingEmbeddings = async (first: number[] = []): Promise<{ saved: number; error: string | null }> => {
  try {
    const found = await query(
      `SELECT i.id, i.supplier_name, i.text,
              i.updated_at::text AS updated_at,
              COALESCE((SELECT array_agg(li.description ORDER BY li.position) FROM line_items li
                         WHERE li.invoice_id = i.id AND li.description IS NOT NULL), '{}') AS descriptions
         FROM invoices i
        WHERE i.error IS NULL -- an invoice the AI could not read has nothing to describe
          AND NOT EXISTS (SELECT 1 FROM invoice_embeddings e WHERE e.invoice_id = i.id)
        ORDER BY (i.id = ANY($1)) DESC, i.id
        LIMIT $2`,
      [first, MAX_TEXTS]
    );
    const invoices = found.rows
      .map((row) => ({ ...row, summary: invoiceSummary(row) }))
      .filter((invoice) => invoice.summary !== null);
    if (invoices.length === 0) return { saved: 0, error: null };

    const answer = await embedWithAi(invoices.map((invoice) => invoice.summary as string), "document");

    let saved = 0;
    for (const [index, invoice] of invoices.entries()) {
      // pgvector takes the numbers as text: "[0.12,-0.5,...]"
      const numbers = `[${answer.embeddings[index].join(",")}]`;
      // Only if the invoice was not changed (or deleted) while we were waiting for the AI:
      // otherwise these numbers describe old values. It is then simply done again next time.
      const result = await query(
        `INSERT INTO invoice_embeddings (invoice_id, embedding, model)
         SELECT $1, $2, $3 WHERE EXISTS (SELECT 1 FROM invoices WHERE id = $1 AND updated_at::text = $4)
         ON CONFLICT (invoice_id) DO UPDATE SET embedding = EXCLUDED.embedding, model = EXCLUDED.model, created_at = now()`,
        [invoice.id, numbers, answer.model, invoice.updated_at]
      );
      saved += result.rowCount ?? 0;
    }
    return { saved, error: null };
  } catch (error) {
    return { saved: 0, error: error instanceof Error ? error.message : String(error) };
  }
};

/*--The history line when it failed--*/
export const embeddingFailedMessage = (reason: string) =>
  `Meaning search: not added yet (${reason}). The invoices are saved and keyword search finds them; ` +
  "they are added to meaning search automatically later (the next time a document is processed or the server starts).";

/*--The meaning numbers for search words, e.g. "office furniture"--*/
// Every new search costs one Gemini request, so we remember the last searches:
// the same words again (e.g. when going to page 2) don't ask Gemini again.
const MAX_REMEMBERED = 200;
const rememberedSearches = new Map<string, { model: string; numbers: number[] }>();

export const embedSearchWords = async (words: string) => {
  const key = words.toLowerCase();
  const remembered = rememberedSearches.get(key);
  if (remembered) return remembered;

  const answer = await embedWithAi([words], "search"); // throws with a clear reason when not available
  const result = { model: answer.model, numbers: answer.embeddings[0] };
  if (rememberedSearches.size >= MAX_REMEMBERED) {
    rememberedSearches.delete(rememberedSearches.keys().next().value as string); // forget the oldest
  }
  rememberedSearches.set(key, result);
  return result;
};

/*--Forget the remembered searches (used by the tests)--*/
export const forgetSearches = () => rememberedSearches.clear();
