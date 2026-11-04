import { describe, expect, it } from "vitest";
import { fillMissingEmbeddings, invoiceSummary } from "../../lib/embeddings";
import {
  aiInvoice, app, fakeAi, fakeEmbedding, fileResult, getDocument, query, request, uploadAndWait, useTestServices,
  waitUntilFinished,
} from "../task4/helpers";

useTestServices();

/*--A line item, as the AI service gives it back--*/
const line = (description: string) => ({
  description, quantity: "1", unit_price: "10.00", amount: "10.00", evidence: description, problems: [],
});

/*--Upload a file with these invoices; returns the document id and the invoice ids--*/
const process = async (filename: string, invoices: unknown[]) => {
  fakeAi.extract = (name) => fileResult(name, invoices);
  const documentId = await uploadAndWait(filename);
  const found = await query("SELECT id FROM invoices WHERE document_id = $1 ORDER BY id", [documentId]);
  return { documentId, invoiceIds: found.rows.map((row) => row.id as number) };
};

const chairs = () => aiInvoice({ invoice_number: "FURN-1", supplier_name: "Acme Ltd", customer_name: "Blue Sky Foods" },
  { line_items: [line("Office chairs"), line("Desk lamps")] });
const internet = () => ({ ...aiInvoice({ invoice_number: "NET-1", supplier_name: "FastNet" },
  { line_items: [line("Broadband, October")] }), source: "Page 2" });

/*--The saved embeddings: { invoice id: { model, the first 4 numbers } }--*/
const savedEmbeddings = async () => {
  const found = await query("SELECT invoice_id, model, embedding::text AS numbers FROM invoice_embeddings ORDER BY invoice_id");
  return Object.fromEntries(found.rows.map((row) =>
    [row.invoice_id, { model: row.model, start: JSON.parse(row.numbers).slice(0, 4) }]));
};
const historySteps = async (documentId: number) =>
  (await getDocument(documentId)).history.map((entry: any) => entry.step);

describe("Step 5 — Saving the meaning of every invoice (embeddings)", () => {
  it("Saves an embedding for every invoice after processing", async () => {
    const { invoiceIds } = await process("october.pdf", [chairs(), internet()]);

    expect(await savedEmbeddings()).toEqual({
      [invoiceIds[0]]: { model: "fake-embedding", start: [1, 0, 0, 0.1] }, // furniture
      [invoiceIds[1]]: { model: "fake-embedding", start: [0, 1, 0, 0.1] }, // internet
    });
  });

  it("Asks for all invoices of a document in one request, as invoices to store", async () => {
    await process("october.pdf", [chairs(), internet()]);

    expect(fakeAi.embedRequests).toEqual([{
      purpose: "document",
      texts: [
        "From: Acme Ltd. Bought: Office chairs; Desk lamps",
        "From: FastNet. Bought: Broadband, October",
      ],
    }]);
  });

  it("Uses the start of the text when an invoice has no line items", () => {
    const summary = invoiceSummary({
      supplier_name: "Corner Cafe", descriptions: [],
      text: "  RECEIPT\nCoffee beans 2 x 12.50\n" + "x".repeat(5000),
    });

    expect(summary?.startsWith("From: Corner Cafe. Text: RECEIPT\nCoffee beans")).toBe(true);
    expect(summary?.length).toBeLessThan(1100); // only the start of a long text
  });

  it("Has nothing to describe when an invoice has no values and no text", () => {
    expect(invoiceSummary({ supplier_name: null, descriptions: [], text: " " }))
      .toBeNull();
  });

  it("Skips an invoice the AI could not read", async () => {
    const broken = { ...aiInvoice({}, { error: "AI extraction failed: Gemini is busy" }), source: "Page 2" };
    const { invoiceIds } = await process("october.pdf", [chairs(), broken]);

    expect(Object.keys(await savedEmbeddings())).toEqual([String(invoiceIds[0])]);
  });

  it("Keeps the document done when meaning search is not available, and says why in the history", async () => {
    fakeAi.embedUnavailable = "Meaning search is not available: the free Gemini limit for embeddings is used up";
    const { documentId, invoiceIds } = await process("october.pdf", [chairs()]);

    const document = await getDocument(documentId);
    expect(document.status).toBe("done");
    expect(invoiceIds).toHaveLength(1); // the invoice is saved
    expect(await savedEmbeddings()).toEqual({});
    expect(document.history.at(-1)).toMatchObject({ step: "meaning search" });
    expect(document.history.at(-1).message).toContain("the free Gemini limit for embeddings is used up");
    expect(document.history.at(-1).message).toContain("keyword search finds them");
  });

  it("Keeps the document done when the AI service crashes while making embeddings", async () => {
    // Only /embed fails: a stopped server would also fail /extract
    fakeAi.embedUnavailable = "Meaning search is not available: Gemini is busy. Try again later.";
    const { documentId } = await process("october.pdf", [chairs()]);

    expect((await getDocument(documentId)).status).toBe("done");
    expect(await historySteps(documentId)).toEqual(["uploaded", "processing", "done", "meaning search"]);
  });

  it("Adds no history line when meaning search works", async () => {
    const { documentId } = await process("october.pdf", [chairs()]);

    expect(await historySteps(documentId)).toEqual(["uploaded", "processing", "done"]);
  });

  it("Adds invoices that were missed earlier the next time a document is processed", async () => {
    fakeAi.embedUnavailable = "the limit is used up";
    const first = await process("october.pdf", [chairs()]);
    expect(await savedEmbeddings()).toEqual({});

    fakeAi.embedUnavailable = null; // the next day: it works again
    const second = await process("november.pdf", [internet()]);

    expect(Object.keys(await savedEmbeddings()).map(Number)).toEqual([first.invoiceIds[0], second.invoiceIds[0]]);
    // The new invoice is sent first, the missed one after it, in one request
    expect(fakeAi.embedRequests.at(-1)?.texts.map((text) => text.split(".")[0])).toEqual(["From: FastNet", "From: Acme Ltd"]);
  });

  it("Can add the missing invoices on its own (as the server does when it starts)", async () => {
    fakeAi.embedUnavailable = "the limit is used up";
    await process("october.pdf", [chairs(), internet()]);

    fakeAi.embedUnavailable = null;
    expect(await fillMissingEmbeddings()).toEqual({ saved: 2, error: null });
    expect(await fillMissingEmbeddings()).toEqual({ saved: 0, error: null }); // nothing left to do
  });

  it("Gives the reason instead of crashing when the AI service is not running", async () => {
    await process("october.pdf", [chairs()]);
    await query("DELETE FROM invoice_embeddings");

    const { stopFakeAi } = await import("../task4/helpers");
    await stopFakeAi();
    expect(await fillMissingEmbeddings()).toEqual({ saved: 0, error: "the AI service is not running at http://localhost:8999" });
  });

  it("Makes the embedding again after a correction, with the new values", async () => {
    const { invoiceIds } = await process("october.pdf", [chairs()]);

    const response = await request(app).patch(`/api/v1/invoices/${invoiceIds[0]}`)
      .send({ fields: { supplier_name: "Office Furniture World" } });

    expect(response.status).toBe(200);
    expect(fakeAi.embedRequests.at(-1)).toEqual({
      purpose: "document",
      texts: ["From: Office Furniture World. Bought: Office chairs; Desk lamps"],
    });
    expect(Object.keys(await savedEmbeddings())).toEqual([String(invoiceIds[0])]);
  });

  it("Removes the old embedding when the correction can't be added to meaning search", async () => {
    const { documentId, invoiceIds } = await process("october.pdf", [chairs()]);
    fakeAi.embedUnavailable = "the limit is used up";

    const response = await request(app).patch(`/api/v1/invoices/${invoiceIds[0]}`)
      .send({ fields: { supplier_name: "Office Furniture World" } });

    expect(response.status).toBe(200); // the correction is saved anyway
    expect(response.body.data.fields.supplier_name.value).toBe("Office Furniture World");
    expect(await savedEmbeddings()).toEqual({}); // the old one described "Acme Ltd": not kept
    expect((await getDocument(documentId)).history.at(-1)).toMatchObject({ step: "meaning search", invoice_id: invoiceIds[0] });
  });

  it("Does not make a new embedding when an invoice is only marked as checked", async () => {
    const { invoiceIds } = await process("october.pdf", [chairs()]);
    const requests = fakeAi.embedRequests.length;

    await request(app).patch(`/api/v1/invoices/${invoiceIds[0]}`).send({ reviewed: true });

    expect(fakeAi.embedRequests.length).toBe(requests); // nothing about its meaning changed
    expect(Object.keys(await savedEmbeddings())).toEqual([String(invoiceIds[0])]);
  });

  it("Does not save numbers for old values when the invoice is changed while the AI is working", async () => {
    const { invoiceIds } = await process("october.pdf", [chairs()]);
    await query("DELETE FROM invoice_embeddings");
    // While the AI is "thinking", someone changes the invoice
    fakeAi.whileEmbedding = () => query("UPDATE invoices SET supplier_name = 'Other Ltd', updated_at = now() WHERE id = $1", [invoiceIds[0]]);

    expect(await fillMissingEmbeddings()).toEqual({ saved: 0, error: null });
    expect(await savedEmbeddings()).toEqual({}); // it is simply done again next time
  });

  it("Keeps one embedding per invoice when a document is processed again", async () => {
    const { documentId } = await process("october.pdf", [chairs(), internet()]);

    await request(app).post(`/api/v1/documents/${documentId}/reprocess`);
    await waitUntilFinished(documentId);

    const found = await query("SELECT invoice_id FROM invoice_embeddings e JOIN invoices i ON i.id = e.invoice_id WHERE i.document_id = $1", [documentId]);
    expect(found.rowCount).toBe(2);
  });

  it("The fake meaning numbers group invoices by topic (used by the next step)", () => {
    expect(fakeEmbedding("Office chairs").slice(0, 4)).toEqual([1, 0, 0, 0.1]);
    expect(fakeEmbedding("Broadband").slice(0, 4)).toEqual([0, 1, 0, 0.1]);
    expect(fakeEmbedding("Something else").slice(0, 4)).toEqual([0, 0, 0, 0.1]);
  });
});
