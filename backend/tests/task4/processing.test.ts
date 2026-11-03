import fs from "fs";
import path from "path";
import { describe, expect, it } from "vitest";
import envConfig from "../../config/env.config";
import { queueUnfinishedDocuments } from "../../lib/queue";
import {
  aiInvoice, fakeAi, fileResult, getDocument, query, stopFakeAi, upload, uploadAndWait, useTestServices,
  waitUntilFinished,
} from "./helpers";

useTestServices();

const historySteps = async (documentId: number) =>
  (await query("SELECT step FROM processing_history WHERE document_id = $1 ORDER BY id", [documentId]))
    .rows.map((row) => row.step);

describe("Step 4 — Background processing", () => {
  it("Processes an uploaded file in the background and saves its invoices", async () => {
    fakeAi.extract = (filename) => fileResult(filename, [aiInvoice({ invoice_number: "INV-001" }, {
      line_items: [{ description: "Chairs", quantity: "10", unit_price: "100.00", amount: "1000.00",
        evidence: "Chairs 10 100.00 1,000.00", problems: [] }],
    })]);

    const id = await uploadAndWait("october.pdf");

    const document = await getDocument(id);
    expect(document.status).toBe("done");
    expect(document.invoice_count).toBe(1);
    expect(document.invoices[0].fields.invoice_number.value).toBe("INV-001");
    expect(document.invoices[0].line_items[0]).toMatchObject({ position: 1, description: "Chairs", amount: "1000.00" });
    expect(fakeAi.files).toEqual(["october.pdf"]);
    expect(await historySteps(id)).toEqual(["uploaded", "processing", "done"]);
  });

  it("Saves money and dates exactly, as text (no rounding, no time-zone shift)", async () => {
    fakeAi.extract = (filename) => fileResult(filename, [aiInvoice({ subtotal: "0.10", tax: "0.20", total: "0.30" })]);

    const id = await uploadAndWait();

    const saved = await query("SELECT subtotal, tax, total, invoice_date, subtotal + tax = total AS adds_up FROM invoices WHERE document_id = $1", [id]);
    expect(saved.rows[0]).toEqual({ subtotal: "0.10", tax: "0.20", total: "0.30", invoice_date: "2026-10-15", adds_up: true });
  });

  it("Saves the problems the AI service found, and the invoice needs review", async () => {
    fakeAi.extract = (filename) => fileResult(filename, [aiInvoice({ total: "1180.00" }, {
      validation_errors: [{ field: "total", rule: "totals_match",
        message: "subtotal 1,000.00 + tax 150.00 = 1,150.00, but the total says 1,180.00" }],
      needs_review: true,
    })]);

    const id = await uploadAndWait();

    const invoice = (await getDocument(id)).invoices[0];
    expect(invoice.needs_review).toBe(true);
    expect(invoice.validation_errors.map((error: any) => error.rule)).toEqual(["totals_match"]);
  });

  it("A file the AI service can't read fails with its reason, and is not tried again", async () => {
    fakeAi.extract = (filename) => fileResult(filename, [], { error: "The PDF is damaged and can't be opened" });

    const id = await uploadAndWait("broken.pdf");

    const document = await getDocument(id);
    expect(document.status).toBe("failed");
    expect(document.error).toBe("The PDF is damaged and can't be opened");
    expect(fakeAi.files).toHaveLength(1);
  });

  it("When the AI could not read any invoice (e.g. Gemini limit used up), the document fails", async () => {
    const limit = "AI extraction failed: the free Gemini limit is used up for today on every model we use (4). Try again in about 2 h 9 min.";
    fakeAi.extract = (filename) => fileResult(filename, [aiInvoice({}, { error: limit })]);

    const id = await uploadAndWait();

    const document = await getDocument(id);
    expect(document.status).toBe("failed");
    expect(document.error).toBe(limit);
  });

  it("When the AI service is down, it tries 3 times and then fails with a clear reason", async () => {
    await stopFakeAi();

    const id = await uploadAndWait();

    const document = await getDocument(id);
    expect(document.status).toBe("failed");
    expect(document.error).toBe("Tried 3 times, but the AI service is not running at http://localhost:8999.");
    expect(await historySteps(id)).toEqual(
      ["uploaded", "processing", "retry", "processing", "retry", "processing", "failed"]);
  });

  it("When the AI service works again during the retries, the document is done", async () => {
    let calls = 0;
    fakeAi.extract = (filename) => (++calls === 1 ? "crash" : fileResult(filename, [aiInvoice()]));

    const id = await uploadAndWait();

    expect((await getDocument(id)).status).toBe("done");
    expect(await historySteps(id)).toEqual(["uploaded", "processing", "retry", "processing", "done"]);
  });

  it("A file that is missing on the server fails with a clear reason", async () => {
    const saved = await query(
      `INSERT INTO documents (filename, file_path, file_size) VALUES ('gone.pdf', 'storage/test-uploads/gone.pdf', 10)
       RETURNING id`);
    const id = saved.rows[0].id;

    await queueUnfinishedDocuments();
    await waitUntilFinished(id);

    expect((await getDocument(id)).error).toBe("The uploaded file is missing on the server. Please upload it again.");
  });

  it("After a restart, documents that were not finished are put back in the queue", async () => {
    fs.writeFileSync(path.join(envConfig.UPLOAD_FOLDER, "waiting.pdf"), "%PDF-1.7 a");
    const saved = await query(
      `INSERT INTO documents (filename, file_path, file_size, status)
       VALUES ('waiting.pdf', 'storage/test-uploads/waiting.pdf', 10, 'processing') RETURNING id`);

    expect(await queueUnfinishedDocuments()).toBe(1);
    expect(await waitUntilFinished(saved.rows[0].id)).toBe("done");
  });

  it("Finds a duplicate of an invoice uploaded earlier; both invoices point to each other", async () => {
    const first = await uploadAndWait("october.pdf");
    fakeAi.extract = (filename) => fileResult(filename, [aiInvoice({ invoice_number: "inv 001", supplier_name: "ACME LTD." })]);
    const second = await uploadAndWait("copy.pdf");

    const earlier = (await getDocument(first)).invoices[0];
    const later = (await getDocument(second)).invoices[0];
    expect(later.needs_review).toBe(true);
    expect(later.validation_errors[0].message).toBe("duplicate: same supplier and invoice number as october.pdf, Page 1 (uploaded earlier)");
    expect(earlier.needs_review).toBe(true);
    expect(earlier.validation_errors[0].message).toBe("duplicate: same supplier and invoice number as copy.pdf, Page 1 (uploaded later)");
    expect((await getDocument(first)).history.at(-1).step).toBe("duplicate");
  });

  it("Finds a possible duplicate: another number, but the same supplier, date and total", async () => {
    await uploadAndWait("october.pdf");
    fakeAi.extract = (filename) => fileResult(filename, [aiInvoice({ invoice_number: "INV-0O1" })]);
    const second = await uploadAndWait("scan.pdf");

    expect((await getDocument(second)).invoices[0].validation_errors.map((error: any) => error.rule))
      .toEqual(["possible_duplicate"]);
  });

  it("Finds duplicates inside one file too", async () => {
    fakeAi.extract = (filename) => fileResult(filename, [aiInvoice(), { ...aiInvoice(), source: "Page 2" }]);

    const id = await uploadAndWait();

    const [first, second] = (await getDocument(id)).invoices;
    expect(first.validation_errors[0].message).toBe("duplicate: same supplier and invoice number as invoice.pdf, Page 2");
    expect(second.validation_errors[0].message).toBe("duplicate: same supplier and invoice number as invoice.pdf, Page 1");
  });

  it("The same invoice number from two different suppliers is not a duplicate", async () => {
    await uploadAndWait("acme.pdf");
    fakeAi.extract = (filename) => fileResult(filename, [aiInvoice({ supplier_name: "Globex Inc", total: "99.00" })]);
    const second = await uploadAndWait("globex.pdf");

    expect((await getDocument(second)).invoices[0].validation_errors).toEqual([]);
  });

  it("Processes the documents one at a time", async () => {
    const response = await upload(["a.pdf", "%PDF-1.7 a"], ["b.pdf", "%PDF-1.7 b"], ["c.pdf", "%PDF-1.7 c"]);
    const ids: number[] = response.body.data.documents.map((document: any) => document.id);
    for (const id of ids) await waitUntilFinished(id);

    const times = await query("SELECT started_at, finished_at FROM documents ORDER BY started_at");
    for (let i = 1; i < times.rows.length; i++) {
      expect(times.rows[i].started_at >= times.rows[i - 1].finished_at).toBe(true);
    }
  });
});
