import fs from "fs";
import path from "path";
import { describe, expect, it } from "vitest";
import envConfig from "../../config/env.config";
import { app, query, request, upload, useTestServices } from "./helpers";

useTestServices();

describe("Step 3 — Upload API", () => {
  it("Accepts several files and answers at once with the status pending", async () => {
    const response = await upload(["a.pdf", "%PDF-1.7 a"], ["b.csv", "Invoice No,Total\nINV-1,10\n"]);

    expect(response.status).toBe(201);
    expect(response.body.success).toBe(true);
    expect(response.body.data.documents.map((document: any) => [document.filename, document.status]))
      .toEqual([["a.pdf", "pending"], ["b.csv", "pending"]]);
    expect(response.body.data.rejected).toEqual([]);
  });

  it("Answers in the shape { success, message, statusCode, data }", async () => {
    const response = await upload(["a.pdf", "%PDF-1.7 a"]);

    expect(Object.keys(response.body).sort()).toEqual(["data", "message", "statusCode", "success"]);
    expect(response.body.statusCode).toBe(201);
  });

  it("Rejects an unsupported file type, but keeps the good files of the same upload", async () => {
    const response = await upload(["notes.docx", "hello"], ["a.pdf", "%PDF-1.7 a"]);

    expect(response.status).toBe(201);
    expect(response.body.data.documents).toHaveLength(1);
    expect(response.body.data.rejected).toEqual([{
      filename: "notes.docx",
      reason: "This file type is not supported. Use PDF, JPG, PNG, TIFF, XLSX, XLS or CSV.",
    }]);
  });

  it("Refuses an upload when none of the files can be processed", async () => {
    const response = await upload(["notes.docx", "hello"]);

    expect(response.status).toBe(400);
    expect(response.body.message).toBe("None of the files can be processed.");
  });

  it("Rejects an empty file", async () => {
    const response = await upload(["empty.pdf", ""], ["a.pdf", "%PDF-1.7 a"]);

    expect(response.body.data.rejected).toEqual([{ filename: "empty.pdf", reason: "The file is empty." }]);
  });

  it("Refuses a request without files", async () => {
    const response = await request(app).post("/api/v1/documents");

    expect(response.status).toBe(400);
    expect(response.body.message).toBe("No files were uploaded. Send them in the form field 'files'.");
  });

  it("Refuses a file bigger than 50 MB, and saves nothing", async () => {
    const response = await upload(["small.pdf", "%PDF-1.7 a"], ["big.pdf", Buffer.alloc(51 * 1024 * 1024)]);

    expect(response.status).toBe(413);
    expect(response.body.message).toBe("A file is bigger than 50 MB. Nothing was uploaded.");
    expect((await query("SELECT count(*)::int AS n FROM documents")).rows[0].n).toBe(0);
    expect(fs.readdirSync(envConfig.UPLOAD_FOLDER)).toEqual([]);
  });

  it("Refuses more than 20 files at once", async () => {
    const files = Array.from({ length: 21 }, (_, i): [string, string] => [`f${i}.csv`, "Invoice No\nINV-1\n"]);

    const response = await upload(...files);

    expect(response.status).toBe(400);
    expect(response.body.message).toBe("Too many files: upload at most 20 at once. Nothing was uploaded.");
  });

  it("Refuses files sent in a wrongly named form field", async () => {
    const response = await request(app).post("/api/v1/documents").attach("file", Buffer.from("a"), "a.pdf");

    expect(response.status).toBe(400);
    expect(response.body.message).toBe("Send the files in the form field 'files'.");
  });

  it("Keeps file names with special letters, like Rechnung-Müller.pdf", async () => {
    const response = await upload(["Rechnung-Müller.pdf", "%PDF-1.7 a"]);

    expect(response.body.data.documents[0].filename).toBe("Rechnung-Müller.pdf");
  });

  it("Saves the file under a random name, never under the user's file name", async () => {
    const response = await upload(["../../app.ts.pdf", "%PDF-1.7 a"]);

    const saved = await query("SELECT file_path FROM documents WHERE id = $1", [response.body.data.documents[0].id]);
    const savedName = path.basename(saved.rows[0].file_path);
    expect(savedName).toMatch(/^[0-9a-f-]{36}\.pdf$/);
    expect(fs.readFileSync(path.join(envConfig.UPLOAD_FOLDER, savedName), "utf8")).toBe("%PDF-1.7 a");
  });

  it("Writes 'uploaded' in the document's history", async () => {
    const response = await upload(["a.pdf", "%PDF-1.7 a"]);

    const history = await query("SELECT step, message FROM processing_history WHERE document_id = $1 ORDER BY id",
      [response.body.data.documents[0].id]);
    expect(history.rows[0]).toEqual({ step: "uploaded", message: 'Uploaded "a.pdf" (1 KB)' });
  });

  it("Answers an unknown address with a clear 404 message", async () => {
    const response = await request(app).get("/api/v1/nothing-here");

    expect(response.status).toBe(404);
    expect(response.body).toEqual({
      success: false, message: "Route not found: GET /api/v1/nothing-here", statusCode: 404, data: null,
    });
  });
});
