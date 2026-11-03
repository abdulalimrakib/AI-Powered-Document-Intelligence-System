import fs from "fs";
import http from "http";
import express from "express";
import multer from "multer";
import request from "supertest";
import { Worker } from "bullmq";
import { afterAll, beforeAll, beforeEach } from "vitest";
import app from "../../app";
import envConfig from "../../config/env.config";
import pool, { query, setupDatabase } from "../../lib/db";
import { documentQueue, startWorker } from "../../lib/queue";

export { app, request, query };

/*--A sample invoice, as the AI service gives it back (change any value)--*/
// e.g. aiInvoice({ total: "1180.00" }) or aiInvoice({ supplier_name: null })
export const aiInvoice = (values: Record<string, string | null> = {}, extra: Record<string, unknown> = {}) => {
  const all: Record<string, string | null> = {
    invoice_number: "INV-001", invoice_date: "2026-10-15", supplier_name: "Acme Ltd", customer_name: "Blue Sky Foods",
    subtotal: "1000.00", tax: "150.00", total: "1150.00", currency: "USD", ...values,
  };
  return {
    source: "Page 1",
    method: "gemini",
    ai_model: "gemini-test",
    error: null as string | null,
    fields: Object.fromEntries(Object.entries(all).map(([name, value]) => [name, {
      value, status: value === null ? "missing" : "found", evidence: value, note: null,
    }])),
    line_items: [] as unknown[],
    validation_errors: [] as { field: string | null; rule: string; message: string }[],
    needs_review: false,
    warnings: [] as string[],
    text: `INVOICE ${all.invoice_number}`,
    ...extra,
  };
};

/*--A sample answer for one file--*/
export const fileResult = (filename: string, invoices: unknown[], extra: Record<string, unknown> = {}) => ({
  filename, file_type: "pdf", invoice_count: invoices.length, invoices, warnings: [], error: null,
  processing_seconds: 0.1, ...extra,
});

/*--The fake AI service--*/
// A small web server on port 8999 that answers like the real AI service. Each test decides what it answers.
type FakeAnswer = object | "crash";
export const fakeAi = {
  // POST /extract: what to answer for a file (default: one complete invoice)
  extract: (filename: string): FakeAnswer => fileResult(filename, [aiInvoice()]),
  // POST /validate: the problems the "check" finds after a correction (default: none)
  problemsAfterCorrection: [] as { field: string | null; rule: string; message: string }[],
  rejectCorrection: null as string | null, // e.g. "total: 'abc' is not an amount" -> answers 400
  files: [] as string[], // the names of the files sent to /extract
  validateRequests: [] as any[], // the bodies sent to /validate
};

const resetFakeAi = () => {
  fakeAi.extract = (filename) => fileResult(filename, [aiInvoice()]);
  fakeAi.problemsAfterCorrection = [];
  fakeAi.rejectCorrection = null;
  fakeAi.files = [];
  fakeAi.validateRequests = [];
};

let fakeServer: http.Server | null = null;

export const startFakeAi = () =>
  new Promise<void>((resolve) => {
    const fake = express();
    fake.use(express.json());
    fake.post("/extract", multer().array("files"), (req, res) => {
      const file = (req.files as Express.Multer.File[])[0];
      fakeAi.files.push(file.originalname);
      const answer = fakeAi.extract(file.originalname);
      if (answer === "crash") {
        res.status(500).end();
        return;
      }
      res.json([answer]);
    });
    // Like the real one: the corrected values become "corrected"; the problems are chosen by the test
    fake.post("/validate", (req, res) => {
      fakeAi.validateRequests.push(req.body);
      if (fakeAi.rejectCorrection) {
        res.status(400).json({ detail: fakeAi.rejectCorrection });
        return;
      }
      const { invoice, corrections } = req.body;
      const fields = { ...invoice.fields };
      for (const [name, typed] of Object.entries(corrections as Record<string, string | null>)) {
        fields[name] = typed
          ? { value: typed.trim(), status: "corrected", evidence: typed, note: "corrected by hand" }
          : { value: null, status: "missing", evidence: null, note: null };
      }
      const problems = fakeAi.problemsAfterCorrection;
      res.json({ ...invoice, fields, validation_errors: problems, needs_review: problems.length > 0 });
    });
    fakeServer = fake.listen(8999, () => resolve());
  });

export const stopFakeAi = () =>
  new Promise<void>((resolve) => {
    if (!fakeServer) return resolve();
    fakeServer.closeAllConnections(); // don't wait for kept-open connections
    fakeServer.close(() => resolve());
    fakeServer = null;
  });

/*--Use in every test file: a clean test database, the fake AI service and the worker--*/
export const useTestServices = () => {
  let worker: Worker;
  beforeAll(async () => {
    // Safety: the tests empty the database and the upload folder before each test, so they must
    // never run against the real ones (the settings come from vitest.config.ts)
    if (!envConfig.DATABASE_URL.endsWith("/docintel_test") || !envConfig.UPLOAD_FOLDER.endsWith("test-uploads")) {
      throw new Error("The tests must use the test database and test upload folder. Run them with: npm test");
    }
    await setupDatabase();
    await startFakeAi();
    worker = startWorker();
  });
  beforeEach(async () => {
    // Let the worker finish what it is doing first: emptying the tables while it saves results
    // would make the two wait for each other forever (a "deadlock")
    await worker.pause();
    await documentQueue.obliterate({ force: true }); // no jobs left from an earlier test
    await query("TRUNCATE documents RESTART IDENTITY CASCADE"); // empty all tables
    worker.resume();
    fs.rmSync(envConfig.UPLOAD_FOLDER, { recursive: true, force: true });
    fs.mkdirSync(envConfig.UPLOAD_FOLDER, { recursive: true });
    resetFakeAi();
    if (!fakeServer) await startFakeAi(); // a test may have stopped it
  });
  afterAll(async () => {
    await worker.close(true);
    await documentQueue.close();
    await stopFakeAi();
    await pool.end();
  });
};

/*--Upload files: upload(["a.pdf", "content"], ["b.csv", "content"])--*/
export const upload = (...files: [string, string | Buffer][]) => {
  let call = request(app).post("/api/v1/documents");
  for (const [name, content] of files) {
    call = call.attach("files", Buffer.isBuffer(content) ? content : Buffer.from(content), name);
  }
  return call;
};

/*--Upload one file and wait until the worker has finished it. Returns the document id.--*/
export const uploadAndWait = async (name = "invoice.pdf", content = "%PDF-1.7 a sample invoice") => {
  const response = await upload([name, content]);
  const id: number = response.body.data.documents[0].id;
  await waitUntilFinished(id);
  return id;
};

/*--Wait until a document is "done" or "failed" (at most 10 seconds). Returns its status.--*/
export const waitUntilFinished = async (documentId: number): Promise<string> => {
  for (let i = 0; i < 200; i++) {
    const found = await query("SELECT status FROM documents WHERE id = $1", [documentId]);
    const status = found.rows[0]?.status;
    if (status === "done" || status === "failed") return status;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(`Document ${documentId} was not finished after 10 seconds`);
};

/*--Read one document through the API--*/
export const getDocument = async (documentId: number) =>
  (await request(app).get(`/api/v1/documents/${documentId}`)).body.data;
