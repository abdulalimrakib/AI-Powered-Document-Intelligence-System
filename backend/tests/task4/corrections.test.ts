import { describe, expect, it } from "vitest";
import {
  aiInvoice, app, fakeAi, fileResult, getDocument, query, request, stopFakeAi, uploadAndWait, useTestServices,
} from "./helpers";

useTestServices();

const correct = (invoiceId: number, body: unknown) =>
  request(app).patch(`/api/v1/invoices/${invoiceId}`).send(body as object);

/*--Upload one invoice with a wrong total, and give back its id--*/
const invoiceWithWrongTotal = async () => {
  fakeAi.extract = (filename) => fileResult(filename, [aiInvoice({ total: "1180.00" }, {
    validation_errors: [{ field: "total", rule: "totals_match", message: "the total does not add up" }],
    needs_review: true,
  })]);
  const documentId = await uploadAndWait();
  return { documentId, invoiceId: (await getDocument(documentId)).invoices[0].id as number };
};

describe("Step 6 — Manual corrections", () => {
  it("Saves a corrected value and marks it as corrected", async () => {
    const { invoiceId } = await invoiceWithWrongTotal();

    const response = await correct(invoiceId, { fields: { total: "1150.00" } });

    expect(response.status).toBe(200);
    expect(response.body.data.fields.total).toEqual({
      value: "1150.00", status: "corrected", evidence: "1150.00", note: "corrected by hand",
    });
  });

  it("Sends the invoice, its text and the corrections to the AI service to be checked again", async () => {
    const { invoiceId } = await invoiceWithWrongTotal();

    await correct(invoiceId, { fields: { total: "1,150.00" } });

    const sent = fakeAi.validateRequests[0];
    expect(sent.corrections).toEqual({ total: "1,150.00" });
    expect(sent.invoice.fields.total.value).toBe("1180.00");
    expect(sent.invoice.text).toBe("INVOICE INV-001");
  });

  it("An invoice with no problems left after the correction no longer needs review", async () => {
    const { invoiceId } = await invoiceWithWrongTotal();

    const response = await correct(invoiceId, { fields: { total: "1150.00" } });

    expect(response.body.message).toBe("Saved. The invoice has no open problems.");
    expect(response.body.data.needs_review).toBe(false);
    expect(response.body.data.validation_errors).toEqual([]);
  });

  it("An invoice that still has problems after the correction still needs review", async () => {
    const { invoiceId } = await invoiceWithWrongTotal();
    fakeAi.problemsAfterCorrection = [{ field: "supplier_name", rule: "missing_field", message: "supplier name is missing" }];

    const response = await correct(invoiceId, { fields: { supplier_name: "" } });

    expect(response.body.message).toBe("Saved. The invoice still needs review.");
    expect(response.body.data.validation_errors.map((error: any) => error.rule)).toEqual(["missing_field"]);
  });

  it("Writes the change in the history, with the old and the new value", async () => {
    const { documentId, invoiceId } = await invoiceWithWrongTotal();

    await correct(invoiceId, { fields: { total: "1150.00" } });

    const last = (await getDocument(documentId)).history.at(-1);
    expect(last.step).toBe("corrected");
    expect(last.message).toBe("Invoice INV-001: Corrected by hand: total 1180.00 → 1150.00");
    expect(last.details.changes).toEqual([{ field: "total", old: "1180.00", new: "1150.00" }]);
    expect(last.invoice_id).toBe(invoiceId);
  });

  it("A value the AI service can't understand is refused with its reason, and nothing changes", async () => {
    const { invoiceId } = await invoiceWithWrongTotal();
    fakeAi.rejectCorrection = "total: 'abc' is not an amount";

    const response = await correct(invoiceId, { fields: { total: "abc" } });

    expect(response.status).toBe(400);
    expect(response.body.message).toBe("total: 'abc' is not an amount");
    const saved = await query("SELECT total, needs_review FROM invoices WHERE id = $1", [invoiceId]);
    expect(saved.rows[0]).toEqual({ total: "1180.00", needs_review: true });
  });

  it("Correcting the invoice number removes the duplicate problem from both invoices", async () => {
    const first = await uploadAndWait("october.pdf");
    const second = await uploadAndWait("copy.pdf");
    const copyId = (await getDocument(second)).invoices[0].id;
    expect((await getDocument(first)).invoices[0].needs_review).toBe(true);

    await correct(copyId, { fields: { invoice_number: "INV-555", total: "99.00" } });

    expect((await getDocument(first)).invoices[0]).toMatchObject({ needs_review: false, validation_errors: [] });
    expect((await getDocument(second)).invoices[0]).toMatchObject({ needs_review: false, validation_errors: [] });
  });

  it("Correcting a value can also find a new duplicate", async () => {
    await uploadAndWait("october.pdf");
    fakeAi.extract = (filename) => fileResult(filename, [aiInvoice({ invoice_number: "INV-999", total: "99.00" })]);
    const second = await uploadAndWait("other.pdf");
    const otherId = (await getDocument(second)).invoices[0].id;

    const response = await correct(otherId, { fields: { invoice_number: "INV-001" } });

    expect(response.body.data.validation_errors.map((error: any) => error.rule)).toEqual(["duplicate_invoice"]);
  });

  it("Marks an invoice as checked by a person, and back again", async () => {
    const { invoiceId } = await invoiceWithWrongTotal();

    const checked = await correct(invoiceId, { reviewed: true });
    expect(checked.body.data.needs_review).toBe(false);
    expect(checked.body.data.validation_errors).toHaveLength(1); // the problem is still shown
    expect(checked.body.data.reviewed_at).not.toBeNull(); // the website shows "checked by a person"

    const unchecked = await correct(invoiceId, { reviewed: false });
    expect(unchecked.body.data.needs_review).toBe(true);
    expect(unchecked.body.data.reviewed_at).toBeNull();
  });

  it.each([
    { example: "unknown field", body: { fields: { colour: "red" } }, message: "'colour' is not an invoice field. Fields: invoice_number, invoice_date, supplier_name, customer_name, subtotal, tax, total, currency" },
    { example: "fields is a list", body: { fields: ["total"] }, message: 'fields must be an object, e.g. { "total": "1,150.00" }' },
    { example: "a number instead of text", body: { fields: { total: 1150 } }, message: "total must be text (or null to empty it)" },
    { example: "501 characters", body: { fields: { total: "1".repeat(501) } }, message: "total is too long (at most 500 characters)" },
    { example: 'reviewed is "yes"', body: { reviewed: "yes" }, message: "reviewed must be true or false" },
    { example: "nothing to change", body: {}, message: 'Nothing to change. Send { "fields": { ... } } and/or { "reviewed": true }' },
  ])("Refuses a wrong request with a clear message ($example)", async ({ body, message }) => {
    const { invoiceId } = await invoiceWithWrongTotal();

    const response = await correct(invoiceId, body);

    expect(response.status).toBe(400);
    expect(response.body.message).toBe(message);
  });

  it("Answers 404 for an invoice that does not exist", async () => {
    const response = await correct(999999, { reviewed: true });

    expect(response.status).toBe(404);
  });

  it("When the AI service is down, the correction is refused (503) and nothing changes", async () => {
    const { invoiceId } = await invoiceWithWrongTotal();
    await stopFakeAi();

    const response = await correct(invoiceId, { fields: { total: "1150.00" } });

    expect(response.status).toBe(503);
    expect(response.body.message).toBe(
      "The correction can't be checked right now: the AI service is not running at http://localhost:8999. Please try again later.");
    const saved = await query("SELECT total FROM invoices WHERE id = $1", [invoiceId]);
    expect(saved.rows[0].total).toBe("1180.00");
  });
});
