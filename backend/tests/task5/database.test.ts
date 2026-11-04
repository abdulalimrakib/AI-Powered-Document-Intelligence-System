import { describe, expect, it } from "vitest";
import { setupDatabase } from "../../lib/db";
import { aiInvoice, fakeAi, fileResult, getDocument, query, uploadAndWait, useTestServices } from "../task4/helpers";

useTestServices();

/*--Make a 768-number embedding for tests: mostly 0, with a few chosen values--*/
// e.g. embedding({ 0: 1 }) = [1, 0, 0, ...]. pgvector takes it as text: "[1,0,0,...]"
const embedding = (values: Record<number, number>, size = 768) =>
  `[${Array.from({ length: size }, (_, i) => values[i] ?? 0).join(",")}]`;

/*--Upload one file with one invoice and return the invoice id--*/
const saveInvoice = async (invoiceNumber: string) => {
  fakeAi.extract = (filename) => fileResult(filename, [aiInvoice({ invoice_number: invoiceNumber })]);
  const documentId = await uploadAndWait(`${invoiceNumber}.pdf`);
  // Processing already saves an embedding (Step 5); remove it, so these tests choose the numbers themselves
  await query("DELETE FROM invoice_embeddings");
  const found = await query("SELECT id FROM invoices WHERE document_id = $1", [documentId]);
  return { documentId, invoiceId: found.rows[0].id as number };
};

const saveEmbedding = (invoiceId: number, values: string) =>
  query("INSERT INTO invoice_embeddings (invoice_id, embedding, model) VALUES ($1, $2, 'test-model')", [invoiceId, values]);

describe("Step 1 — A place to store the meaning of each invoice", () => {
  it("Saves an embedding (768 numbers) for an invoice", async () => {
    const { invoiceId } = await saveInvoice("INV-1");
    await saveEmbedding(invoiceId, embedding({ 0: 1 }));

    const found = await query("SELECT vector_dims(embedding) AS size, model FROM invoice_embeddings WHERE invoice_id = $1", [invoiceId]);
    expect(found.rows[0]).toEqual({ size: 768, model: "test-model" });
  });

  it("Refuses an embedding with the wrong number of values", async () => {
    const { invoiceId } = await saveInvoice("INV-1");
    await expect(saveEmbedding(invoiceId, embedding({ 0: 1 }, 3))).rejects.toThrow(/expected 768 dimensions/);
  });

  it("Keeps only one embedding per invoice", async () => {
    const { invoiceId } = await saveInvoice("INV-1");
    await saveEmbedding(invoiceId, embedding({ 0: 1 }));
    await expect(saveEmbedding(invoiceId, embedding({ 1: 1 }))).rejects.toThrow(/duplicate key/);
  });

  it("Refuses an embedding for an invoice that doesn't exist", async () => {
    await expect(saveEmbedding(12345, embedding({ 0: 1 }))).rejects.toThrow(/foreign key/);
  });

  it("Deleting a document also deletes the embeddings of its invoices", async () => {
    const { documentId, invoiceId } = await saveInvoice("INV-1");
    await saveEmbedding(invoiceId, embedding({ 0: 1 }));

    await query("DELETE FROM documents WHERE id = $1", [documentId]);
    const left = await query("SELECT count(*)::int AS count FROM invoice_embeddings");
    expect(left.rows[0].count).toBe(0);
  });

  it("Finds the closest invoice first", async () => {
    // Pretend: dimension 0 = "furniture", dimension 1 = "internet". Real embeddings work the same way, with 768 meanings.
    const chairs = await saveInvoice("CHAIRS");
    const desks = await saveInvoice("DESKS");
    const internet = await saveInvoice("INTERNET");
    await saveEmbedding(chairs.invoiceId, embedding({ 0: 0.9, 1: 0.1 }));
    await saveEmbedding(desks.invoiceId, embedding({ 0: 0.7, 1: 0.3 }));
    await saveEmbedding(internet.invoiceId, embedding({ 0: 0.1, 1: 0.9 }));

    // "<=>" is pgvector's cosine distance: 0 = the same meaning, bigger = less alike
    const found = await query(
      `SELECT i.invoice_number FROM invoice_embeddings e JOIN invoices i ON i.id = e.invoice_id
       ORDER BY e.embedding <=> $1 LIMIT 3`,
      [embedding({ 0: 1 })] // the search: "furniture"
    );
    expect(found.rows.map((row) => row.invoice_number)).toEqual(["CHAIRS", "DESKS", "INTERNET"]);
  });

  it("Has the fast index for finding the closest embeddings", async () => {
    const found = await query("SELECT indexdef FROM pg_indexes WHERE indexname = 'invoice_embeddings_idx'");
    expect(found.rows[0].indexdef).toMatch(/USING hnsw \(embedding vector_cosine_ops\)/);
  });

  it("Setting up the database again keeps the saved embeddings", async () => {
    const { invoiceId } = await saveInvoice("INV-1");
    await saveEmbedding(invoiceId, embedding({ 0: 1 }));

    await setupDatabase(); // what the backend does every time it starts
    const left = await query("SELECT count(*)::int AS count FROM invoice_embeddings");
    expect(left.rows[0].count).toBe(1);
  });

  it("The invoice API does not send the embedding numbers to the website", async () => {
    const { documentId, invoiceId } = await saveInvoice("INV-1");
    await saveEmbedding(invoiceId, embedding({ 0: 1 }));

    const document = await getDocument(documentId);
    expect(document.invoices[0].fields.invoice_number.value).toBe("INV-1");
    expect(JSON.stringify(document)).not.toMatch(/embedding/);
  });
});
