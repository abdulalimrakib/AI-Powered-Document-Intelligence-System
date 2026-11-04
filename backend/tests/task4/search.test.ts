import { beforeEach, describe, expect, it } from "vitest";
import { aiInvoice, app, fakeAi, fileResult, request, uploadAndWait, useTestServices } from "./helpers";

useTestServices();

const search = async (q: string, extra = "") =>
  (await request(app).get(`/api/v1/search?q=${encodeURIComponent(q)}${extra}`)).body;
const numbers = (body: any) => body.data.invoices.map((invoice: any) => invoice.invoice_number);

describe("Step 8 — Search", () => {
  beforeEach(async () => {
    fakeAi.extract = (filename) => fileResult(filename, [
      aiInvoice({ invoice_number: "INV-100", supplier_name: "Acme Ltd", customer_name: "Blue Sky Foods" }),
      { ...aiInvoice({ invoice_number: "INV-1001", supplier_name: "Acme Ltd", customer_name: "Green Leaf Cafe", total: "200.00" }), source: "Page 2" },
    ]);
    await uploadAndWait("acme-october.pdf");
    fakeAi.extract = (filename) => fileResult(filename, [
      aiInvoice({ invoice_number: "GX-77", supplier_name: "Globex Supplies", customer_name: "Blue Sky Foods", total: "57.50" }),
      { ...aiInvoice({ invoice_number: "PCT-1", supplier_name: "Fifty 50% Off Ltd", customer_name: "Corner_Shop", total: "10.00" }), source: "Page 2" },
      { ...aiInvoice({ invoice_number: "PCT-2", supplier_name: "Fifty 50 Off Ltd", customer_name: "Corner Shop", total: "12.00" }), source: "Page 3" },
    ]);
    await uploadAndWait("others.pdf");
  });

  it("Finds invoices by supplier, with small or capital letters", async () => {
    expect(numbers(await search("acme"))).toEqual(["INV-1001", "INV-100"]);
    expect(numbers(await search("ACME LTD"))).toEqual(["INV-1001", "INV-100"]);
  });

  it("Finds invoices by customer", async () => {
    const body = await search("blue sky");

    expect(numbers(body).sort()).toEqual(["GX-77", "INV-100"]);
    expect(body.data.invoices[0].found_in).toBe("customer");
  });

  it("Finds invoices by file name", async () => {
    const body = await search("october");

    expect(numbers(body)).toEqual(["INV-1001", "INV-100"]);
    expect(body.data.invoices[0]).toMatchObject({ found_in: "file name", filename: "acme-october.pdf" });
  });

  it("Finds an invoice number written without dashes or with spaces, the exact one first", async () => {
    expect(numbers(await search("inv 100"))).toEqual(["INV-100", "INV-1001"]);
    expect(numbers(await search("inv100"))).toEqual(["INV-100", "INV-1001"]);
  });

  it("Treats % and _ as normal characters, not as wildcards", async () => {
    expect(numbers(await search("50%"))).toEqual(["PCT-1"]);
    expect(numbers(await search("_"))).toEqual(["PCT-1"]);
  });

  it("Says when nothing is found", async () => {
    const body = await search("nothing like this");

    expect(body.message).toBe('0 invoices found for "nothing like this"');
    expect(body.data.invoices).toEqual([]);
  });

  it("Splits the results into pages", async () => {
    const body = await search("acme", "&limit=1&page=2");

    expect(numbers(body)).toEqual(["INV-100"]);
    expect(body.data).toMatchObject({ page: 2, limit: 1, total: 2, total_pages: 2 });
  });

  it.each([
    { example: "empty", q: "", message: "Type something to search for, or use a filter, e.g. ?q=acme or ?currency=USD" },
    { example: "only spaces", q: "   ", message: "Type something to search for, or use a filter, e.g. ?q=acme or ?currency=USD" },
    { example: "201 characters", q: "x".repeat(201), message: "The search text is too long (at most 200 characters)" },
  ])("Refuses an empty or too long search ($example)", async ({ q, message }) => {
    const response = await request(app).get(`/api/v1/search?q=${encodeURIComponent(q)}`);

    expect(response.status).toBe(400);
    expect(response.body.message).toBe(message);
  });
});
