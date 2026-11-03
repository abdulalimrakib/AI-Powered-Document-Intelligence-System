import fs from "fs";
import path from "path";
import { describe, expect, it } from "vitest";
import envConfig from "../../config/env.config";
import {
  aiInvoice, app, fakeAi, fileResult, getDocument, query, request, stopFakeAi, uploadAndWait, useTestServices,
  waitUntilFinished,
} from "./helpers";

useTestServices();

const reprocess = (documentId: number | string) => request(app).post(`/api/v1/documents/${documentId}/reprocess`);

describe("Step 7 — Re-processing failed documents", () => {
  it("A document that failed (AI service was down) is processed again and becomes done", async () => {
    await stopFakeAi();
    const id = await uploadAndWait();
    expect((await getDocument(id)).status).toBe("failed");
    const { startFakeAi } = await import("./helpers");
    await startFakeAi();

    const response = await reprocess(id);

    expect(response.status).toBe(202);
    expect(response.body.message).toBe(`Document ${id} will be processed again in the background.`);
    expect(await waitUntilFinished(id)).toBe("done");
    const document = await getDocument(id);
    expect(document.error).toBeNull();
    expect(document.invoices).toHaveLength(1);
    expect(document.history.map((line: any) => line.step)).toContain("reprocess");
  });

  it("Uses the saved file: the file does not have to be uploaded again", async () => {
    fakeAi.extract = (filename) => fileResult(filename, [], { error: "The PDF is damaged and can't be opened" });
    const id = await uploadAndWait("october.pdf");
    fakeAi.extract = (filename) => fileResult(filename, [aiInvoice()]);

    await reprocess(id);
    await waitUntilFinished(id);

    expect(fakeAi.files).toEqual(["october.pdf", "october.pdf"]);
  });

  it("A document that is done, but has an invoice the AI could not read, can be tried again", async () => {
    fakeAi.extract = (filename) => fileResult(filename, [
      aiInvoice(), { ...aiInvoice({ invoice_number: "INV-002" }), source: "Page 2", error: "AI extraction failed: Gemini is busy" },
    ]);
    const id = await uploadAndWait();
    fakeAi.extract = (filename) => fileResult(filename, [aiInvoice(), { ...aiInvoice({ invoice_number: "INV-002" }), source: "Page 2" }]);

    const response = await reprocess(id);
    await waitUntilFinished(id);

    expect(response.status).toBe(202);
    expect((await getDocument(id)).invoices.map((invoice: any) => invoice.error)).toEqual([null, null]);
  });

  it("A document that is done without failures is not processed again (its corrections would be lost)", async () => {
    const id = await uploadAndWait();

    const response = await reprocess(id);

    expect(response.status).toBe(409);
    expect(response.body.message).toBe(`Document ${id} was processed without failures, so there is nothing to try again.`);
  });

  it.each(["pending", "processing"])("A document that is still %s is not sent again", async (status) => {
    const id = await uploadAndWait();
    await query("UPDATE documents SET status = $2 WHERE id = $1", [id, status]);

    const response = await reprocess(id);

    expect(response.status).toBe(409);
    expect(response.body.message).toBe(`Document ${id} is already ${status}. Wait until it is done.`);
  });

  it("A document whose saved file is gone asks for a new upload", async () => {
    fakeAi.extract = (filename) => fileResult(filename, [], { error: "The PDF is damaged and can't be opened" });
    const id = await uploadAndWait();
    const saved = await query("SELECT file_path FROM documents WHERE id = $1", [id]);
    fs.rmSync(path.join(envConfig.BACKEND_FOLDER, saved.rows[0].file_path));

    const response = await reprocess(id);

    expect(response.status).toBe(410);
    expect(response.body.message).toBe(`The file of document ${id} is missing on the server. Please upload it again.`);
  });

  it("Processing again removes the duplicate warnings the old results caused on other invoices", async () => {
    const first = await uploadAndWait("october.pdf");
    fakeAi.extract = (filename) => fileResult(filename, [aiInvoice(), { ...aiInvoice({ invoice_number: "INV-777", total: "5.00" }), source: "Page 2", error: "AI extraction failed: Gemini is busy" }]);
    const second = await uploadAndWait("copy.pdf");
    expect((await getDocument(first)).invoices[0].needs_review).toBe(true);
    // The second time, the AI reads the first invoice of copy.pdf with another number: no duplicate any more
    fakeAi.extract = (filename) => fileResult(filename, [aiInvoice({ invoice_number: "INV-888", total: "20.00" })]);

    await reprocess(second);
    await waitUntilFinished(second);

    expect((await getDocument(first)).invoices[0]).toMatchObject({ needs_review: false, validation_errors: [] });
  });

  it("Answers 404 for an unknown document and 400 for a wrong id", async () => {
    expect((await reprocess(999999)).status).toBe(404);
    expect((await reprocess("abc")).status).toBe(400);
  });
});
