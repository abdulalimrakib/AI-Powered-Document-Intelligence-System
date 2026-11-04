import { beforeEach, describe, expect, it } from "vitest";
import { forgetSearches } from "../../lib/embeddings";
import { aiInvoice, app, fakeAi, fileResult, query, request, uploadAndWait, useTestServices } from "../task4/helpers";

useTestServices();

const meaning = (q: string, extra = "") =>
  request(app).get(`/api/v1/search?q=${encodeURIComponent(q)}&mode=meaning${extra}`);
const numbers = (body: any) => body.data.invoices.map((invoice: any) => invoice.invoice_number);

/*--An invoice with these line items (the fake meaning numbers come from the words in them)--*/
let page = 0;
const invoice = (invoiceNumber: string, items: string[], values: Record<string, string> = {}) => ({
  ...aiInvoice({ invoice_number: invoiceNumber, ...values }, {
    line_items: items.map((description) => ({
      description, quantity: "1", unit_price: "10.00", amount: "10.00", evidence: description, problems: [],
    })),
  }),
  source: `Page ${++page}`,
});
const save = async (filename: string, invoices: unknown[]) => {
  fakeAi.extract = (name) => fileResult(name, invoices);
  await uploadAndWait(filename);
};

describe("Step 6 — Meaning search (?mode=meaning)", () => {
  beforeEach(async () => {
    forgetSearches(); // every test starts without remembered searches
    await save("october.pdf", [
      invoice("FURN-1", ["Office chairs", "Desk lamps"], { currency: "USD" }),
      invoice("NET-1", ["Broadband, October"]),
    ]);
  });

  it("Finds an invoice by meaning, even without the same words", async () => {
    // "office furniture" is not written on FURN-1, but chairs and desks are furniture
    const response = await meaning("office furniture");

    expect(response.status).toBe(200);
    expect(numbers(response.body)).toEqual(["FURN-1"]);
    expect(response.body.data.invoices[0]).toMatchObject({ found_in: "meaning", similarity: 1 });
    expect(response.body.message).toBe('1 invoice found for "office furniture" (by meaning)');
  });

  it("Asks the AI for the search words as a search (not as an invoice)", async () => {
    await meaning("office furniture");

    expect(fakeAi.embedRequests.at(-1)).toEqual({ texts: ["office furniture"], purpose: "search" });
  });

  it("Shows nothing when no invoice is related", async () => {
    const response = await meaning("coffee"); // neither furniture nor internet

    expect(response.status).toBe(200);
    expect(response.body.data.invoices).toEqual([]);
    expect(response.body.message).toBe('0 invoices found for "coffee" (by meaning)');
  });

  it("Leaves out invoices that are much less close than the best one", async () => {
    // MIX-1 is half furniture, half internet (similarity about 0.71): related, but far below FURN-1 (1.0)
    await save("mixed.pdf", [invoice("MIX-1", ["Desk", "Wifi router"])]);

    expect(numbers((await meaning("office furniture")).body)).toEqual(["FURN-1"]);
  });

  it("Shows a less close invoice when it is the best there is", async () => {
    await save("mixed.pdf", [invoice("MIX-1", ["Desk", "Wifi router"])]);
    await query("DELETE FROM invoices WHERE invoice_number = 'FURN-1'");

    const response = await meaning("office furniture");

    expect(numbers(response.body)).toEqual(["MIX-1"]);
    expect(response.body.data.invoices[0].similarity).toBeCloseTo(0.709, 3);
  });

  it("Gives several equally close invoices, newest first", async () => {
    await save("november.pdf", [invoice("FURN-2", ["Meeting table"])]);

    expect(numbers((await meaning("office furniture")).body)).toEqual(["FURN-2", "FURN-1"]);
  });

  it("Puts the closest invoice first, even when another one is newer", async () => {
    await save("november.pdf", [invoice("FURN-2", ["Meeting table"])]);
    // Make the newer FURN-2 a little less close (similarity 0.989 instead of 1)
    const slightlyDifferent = `[${Array.from({ length: 768 }, (_, i) => (i === 0 ? 1 : i === 3 ? 0.25 : 0)).join(",")}]`;
    await query(`UPDATE invoice_embeddings SET embedding = $1
                  WHERE invoice_id = (SELECT id FROM invoices WHERE invoice_number = 'FURN-2')`, [slightlyDifferent]);

    const response = await meaning("office furniture");

    expect(numbers(response.body)).toEqual(["FURN-1", "FURN-2"]);
    expect(response.body.data.invoices.map((found: any) => found.similarity)).toEqual([1, 0.989]);
  });

  it("Works together with the filters", async () => {
    await save("november.pdf", [invoice("FURN-2", ["Meeting table"], { currency: "EUR", total: "500.00", subtotal: "500.00", tax: "0.00" })]);

    expect(numbers((await meaning("office furniture", "&currency=EUR")).body)).toEqual(["FURN-2"]);
    expect(numbers((await meaning("office furniture", "&total_min=1000")).body)).toEqual(["FURN-1"]); // 1150.00
    expect(numbers((await meaning("office furniture", "&currency=GBP")).body)).toEqual([]);
  });

  it("Splits the results into pages, and asks the AI only once for the same words", async () => {
    await save("november.pdf", [invoice("FURN-2", ["Meeting table"])]);
    const before = fakeAi.embedRequests.length;

    const first = await meaning("office furniture", "&limit=1");
    const second = await meaning("Office Furniture", "&limit=1&page=2"); // small or capital letters: the same

    expect(numbers(first.body)).toEqual(["FURN-2"]);
    expect(numbers(second.body)).toEqual(["FURN-1"]);
    expect(second.body.data).toMatchObject({ page: 2, limit: 1, total: 2, total_pages: 2 });
    expect(fakeAi.embedRequests.length - before).toBe(1); // page 2 used the remembered numbers
  });

  it("Says how many invoices are not in meaning search yet", async () => {
    fakeAi.embedUnavailable = "the limit is used up";
    await save("november.pdf", [invoice("FURN-2", ["Meeting table"])]); // could not be added
    fakeAi.embedUnavailable = null;

    const response = await meaning("office furniture");

    expect(numbers(response.body)).toEqual(["FURN-1"]);
    expect(response.body.data.not_in_meaning_search).toBe(1);
  });

  it("Only compares with invoices whose numbers were made by the same AI model", async () => {
    await query("UPDATE invoice_embeddings SET model = 'an-older-model'"); // e.g. after changing GEMINI_EMBEDDING_MODEL

    const response = await meaning("office furniture");

    expect(response.body.data.invoices).toEqual([]);
    expect(response.body.data.not_in_meaning_search).toBe(2);
  });

  it("Does not send the meaning numbers or the invoice text to the website", async () => {
    const response = await meaning("office furniture");

    expect(Object.keys(response.body.data.invoices[0]).sort()).toEqual([
      "currency", "customer_name", "document_id", "filename", "found_in", "id", "invoice_date", "invoice_number",
      "needs_review", "similarity", "source", "supplier_name", "total",
    ]);
  });

  it("Explains when meaning search can't be used, and that keyword search still works", async () => {
    fakeAi.embedUnavailable = "Meaning search is not available: the free Gemini limit for embeddings is used up for today. Try again in about 2 h 9 min.";

    const response = await meaning("office furniture");

    expect(response.status).toBe(503);
    expect(response.body.message).toBe(
      "Meaning search can't be used right now: the free Gemini limit for embeddings is used up for today. " +
      "Try again in about 2 h 9 min. Keyword search still works: leave out mode=meaning.");
  });

  it("Keyword search is still the default", async () => {
    const response = await request(app).get("/api/v1/search?q=chairs");

    expect(numbers(response.body)).toEqual(["FURN-1"]);
    expect(response.body.data.invoices[0].found_in).toBe("line item");
  });

  it.each([
    { example: "unknown mode", params: "q=chairs&mode=magic", message: "mode must be keyword or meaning" },
    { example: "no search words", params: "mode=meaning&currency=USD", message: "Meaning search needs words to search for, e.g. ?q=office furniture&mode=meaning" },
    { example: "a wrong filter", params: "q=chairs&mode=meaning&total_min=abc", message: "total_min must be an amount like 500 or 499.99" },
  ])("Refuses a wrong meaning search with a clear message ($example)", async ({ params, message }) => {
    const response = await request(app).get(`/api/v1/search?${params}`);

    expect(response.status).toBe(400);
    expect(response.body.message).toBe(message);
  });
});
