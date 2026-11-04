import { beforeEach, describe, expect, it } from "vitest";
import { aiInvoice, app, fakeAi, fileResult, request, uploadAndWait, useTestServices } from "../task4/helpers";

useTestServices();

// e.g. search("currency=USD&total_min=500")
const search = (params: string) => request(app).get(`/api/v1/search?${params}`);
const numbers = async (params: string) =>
  (await search(params)).body.data.invoices.map((invoice: any) => invoice.invoice_number).sort();

describe("Step 3 — Filters: date, amount, currency, supplier and needs review", () => {
  beforeEach(async () => {
    let page = 0;
    // The backend sets "needs review" when an invoice has problems, so a sample that needs review gets one
    const problem = { field: "total", rule: "totals_match", message: "Subtotal + tax is not the total" };
    const invoice = (values: Record<string, string | null>, needsReview = false) => ({
      ...aiInvoice(values, { needs_review: needsReview, validation_errors: needsReview ? [problem] : [] }),
      source: `Page ${++page}`,
    });

    fakeAi.extract = (filename) => fileResult(filename, [
      invoice({ invoice_number: "A-1", invoice_date: "2026-01-15", total: "100.00", currency: "USD", supplier_name: "Acme Ltd" }),
      invoice({ invoice_number: "A-2", invoice_date: "2026-03-01", total: "1150.00", currency: "usd", supplier_name: "Acme Ltd" }, true),
      invoice({ invoice_number: "B-1", invoice_date: "2026-03-31", total: "99.99", currency: "EUR", supplier_name: "Bolt GmbH" }),
      invoice({ invoice_number: "C-1", invoice_date: "2026-06-30", total: "-20.50", currency: "GBP", supplier_name: "50% Off Ltd" }),
      invoice({ invoice_number: "D-1", invoice_date: null, total: null, currency: null, supplier_name: null }, true),
    ]);
    await uploadAndWait("filters.pdf");
  });

  it("Filters by date (the first and last day are included)", async () => {
    expect(await numbers("date_from=2026-03-01&date_to=2026-03-31")).toEqual(["A-2", "B-1"]);
    expect(await numbers("date_from=2026-03-02")).toEqual(["B-1", "C-1"]);
    expect(await numbers("date_to=2026-01-15")).toEqual(["A-1"]);
  });

  it("Filters by total, exactly to the cent", async () => {
    expect(await numbers("total_min=100")).toEqual(["A-1", "A-2"]);
    expect(await numbers("total_min=100.01")).toEqual(["A-2"]);
    expect(await numbers("total_max=99.99")).toEqual(["B-1", "C-1"]);
    expect(await numbers("total_min=99.99&total_max=100.00")).toEqual(["A-1", "B-1"]);
  });

  it("Filters by a negative total (credit notes)", async () => {
    expect(await numbers("total_max=-1")).toEqual(["C-1"]);
  });

  it("Filters by currency, with small or capital letters", async () => {
    expect(await numbers("currency=usd")).toEqual(["A-1", "A-2"]);
    expect(await numbers("currency=EUR")).toEqual(["B-1"]);
  });

  it("Filters by part of the supplier name (% is a normal character)", async () => {
    expect(await numbers("supplier=acme")).toEqual(["A-1", "A-2"]);
    expect(await numbers("supplier=50%25")).toEqual(["C-1"]); // %25 is "%" in a URL
  });

  it("Filters by needs review", async () => {
    expect(await numbers("needs_review=true")).toEqual(["A-2", "D-1"]);
    expect(await numbers("needs_review=false")).toEqual(["A-1", "B-1", "C-1"]);
  });

  it("Leaves out invoices without a date or total when filtering by date or total", async () => {
    expect(await numbers("date_from=2000-01-01")).not.toContain("D-1");
    expect(await numbers("total_max=1000000")).not.toContain("D-1");
  });

  it("Combines several filters (all of them must match)", async () => {
    expect(await numbers("currency=USD&needs_review=false")).toEqual(["A-1"]);
    expect(await numbers("supplier=acme&date_from=2026-02-01&total_min=1000")).toEqual(["A-2"]);
  });

  it("Combines search words and filters", async () => {
    expect(await numbers("q=acme&total_min=500")).toEqual(["A-2"]);
    expect(await numbers("q=acme&currency=EUR")).toEqual([]);
  });

  it("Works without search words when a filter is given, newest first", async () => {
    const response = await search("currency=USD");

    expect(response.status).toBe(200);
    expect(response.body.message).toBe("2 invoices found");
    expect(response.body.data.invoices.map((invoice: any) => invoice.found_in)).toEqual([null, null]);
  });

  it("Sends back the filters that were used", async () => {
    const response = await search("currency=usd&supplier=acme&total_min=500");

    expect(response.body.data.filters).toEqual({ currency: "USD", supplier: "acme", total_min: "500" });
    expect(response.body.data.total).toBe(1);
  });

  it("Ignores an empty filter, so search words or another filter are still needed", async () => {
    const response = await search("currency=&supplier=");

    expect(response.status).toBe(400);
    expect(response.body.message).toBe("Type something to search for, or use a filter, e.g. ?q=acme or ?currency=USD");
  });

  it.each([
    { example: "not a date", params: "date_from=banana", message: "date_from must be a date like 2026-01-31" },
    { example: "a day that doesn't exist", params: "date_to=2026-02-30", message: "date_to must be a date like 2026-01-31" },
    { example: "dates the wrong way round", params: "date_from=2026-05-01&date_to=2026-04-01", message: "date_from must be on or before date_to" },
    { example: "not an amount", params: "total_min=abc", message: "total_min must be an amount like 500 or 499.99" },
    { example: "amount with a comma", params: "total_max=1,000", message: "total_max must be an amount like 500 or 499.99" },
    { example: "3 decimals", params: "total_min=1.234", message: "total_min must be an amount like 500 or 499.99" },
    { example: "amounts the wrong way round", params: "total_min=100&total_max=99.99", message: "total_min must not be bigger than total_max" },
    { example: "currency of 2 letters", params: "currency=US", message: "currency must be a 3-letter code like USD" },
    { example: "needs review is yes", params: "needs_review=yes", message: "needs_review must be true or false" },
    { example: "supplier too long", params: `supplier=${"x".repeat(201)}`, message: "supplier is too long (at most 200 characters)" },
    { example: "a filter given twice", params: "currency=USD&currency=EUR", message: "currency can only be given once" },
  ])("Refuses a wrong filter with a clear message ($example)", async ({ params, message }) => {
    const response = await search(`q=acme&${params}`);

    expect(response.status).toBe(400);
    expect(response.body.message).toBe(message);
  });
});
