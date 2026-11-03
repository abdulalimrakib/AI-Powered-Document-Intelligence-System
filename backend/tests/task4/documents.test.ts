import { describe, expect, it } from "vitest";
import { aiInvoice, app, fakeAi, fileResult, getDocument, request, uploadAndWait, useTestServices } from "./helpers";

useTestServices();

const list = async (filters = "") => (await request(app).get(`/api/v1/documents${filters}`)).body;

/*--Three documents: one fine, one that needs review, one that failed--*/
const uploadThree = async () => {
  const fine = await uploadAndWait("fine.pdf");
  fakeAi.extract = (filename) => fileResult(filename, [aiInvoice({ invoice_number: "INV-002", total: "1180.00" }, {
    validation_errors: [{ field: "total", rule: "totals_match", message: "the total does not add up" }],
    needs_review: true,
  })]);
  const review = await uploadAndWait("review.pdf");
  fakeAi.extract = (filename) => fileResult(filename, [], { error: "The PDF is damaged and can't be opened" });
  const broken = await uploadAndWait("broken.pdf");
  return { fine, review, broken };
};

describe("Step 5 — Status and results API", () => {
  it("Lists the documents, newest first, with their invoice and review counts", async () => {
    await uploadThree();

    const body = await list();

    expect(body.message).toBe("3 documents found");
    expect(body.data.documents.map((document: any) =>
      [document.filename, document.status, document.invoice_count, document.review_count]))
      .toEqual([["broken.pdf", "failed", 0, 0], ["review.pdf", "done", 1, 1], ["fine.pdf", "done", 1, 0]]);
  });

  it("Filters the list by status", async () => {
    await uploadThree();

    const body = await list("?status=failed");

    expect(body.data.documents.map((document: any) => document.filename)).toEqual(["broken.pdf"]);
  });

  it("Filters the list to documents that need review (or don't)", async () => {
    await uploadThree();

    expect((await list("?needs_review=true")).data.documents.map((document: any) => document.filename))
      .toEqual(["review.pdf"]);
    expect((await list("?needs_review=false")).data.documents.map((document: any) => document.filename))
      .toEqual(["broken.pdf", "fine.pdf"]);
  });

  it("Splits the list into pages", async () => {
    await uploadThree();

    const body = await list("?limit=2&page=2");

    expect(body.data.documents.map((document: any) => document.filename)).toEqual(["fine.pdf"]);
    expect(body.data).toMatchObject({ page: 2, limit: 2, total: 3, total_pages: 2 });
  });

  it.each([
    ["?status=finished", "status must be one of: pending, processing, done, failed"],
    ["?needs_review=yes", "needs_review must be true or false"],
    ["?page=0", "page must be a whole number from 1"],
    ["?page=abc", "page must be a whole number from 1"],
    ["?limit=500", "limit must be a whole number from 1 to 100"],
  ])("Refuses a wrong filter with a clear message (%s)", async (filters, message) => {
    const response = await request(app).get(`/api/v1/documents${filters}`);

    expect(response.status).toBe(400);
    expect(response.body.message).toBe(message);
  });

  it("Gives one document with its invoices, fields, line items, problems and history", async () => {
    const { review } = await uploadThree();

    const document = await getDocument(review);

    expect(document).toMatchObject({ filename: "review.pdf", status: "done", invoice_count: 1 });
    const invoice = document.invoices[0];
    expect(invoice.fields.total).toEqual({ value: "1180.00", status: "found", evidence: "1180.00", note: null });
    expect(invoice.fields.customer_name.value).toBe("Blue Sky Foods");
    expect(invoice.line_items).toEqual([]);
    expect(invoice.validation_errors).toMatchObject([{ field: "total", rule: "totals_match" }]);
    expect(invoice.needs_review).toBe(true);
    expect(document.history.map((line: any) => line.step)).toEqual(["uploaded", "processing", "done"]);
  });

  it("Gives a failed document with its reason", async () => {
    const { broken } = await uploadThree();

    const document = await getDocument(broken);

    expect(document).toMatchObject({ status: "failed", error: "The PDF is damaged and can't be opened", invoices: [] });
  });

  it("Answers 404 for a document that does not exist", async () => {
    const response = await request(app).get("/api/v1/documents/999999");

    expect(response.status).toBe(404);
    expect(response.body.message).toBe("Document 999999 was not found");
  });

  it.each(["abc", "-1", "1.5", "0"])("Answers 400 for an id that is not a whole number (%s)", async (id) => {
    const response = await request(app).get(`/api/v1/documents/${id}`);

    expect(response.status).toBe(400);
  });
});
