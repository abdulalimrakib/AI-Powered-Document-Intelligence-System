import { ChildProcess, spawn } from "child_process";
import fs from "fs";
import path from "path";
import { Worker } from "bullmq";
import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import envConfig from "../../config/env.config";
import { setupDatabase } from "../../lib/db";
import { documentQueue, startWorker } from "../../lib/queue";
import pool from "../../lib/db";
import { app, getDocument, query, request, upload, waitUntilFinished } from "../task4/helpers";

/*--The backend together with the REAL AI service (no fake)--*/
// All other backend tests use a fake AI service. If the real one ever answered in a different shape, they would
// still pass while the real system breaks. These tests catch that.
// The AI service is started WITHOUT a Gemini key, so these tests can never use the free Gemini limit:
// they use spreadsheets (read without AI) and broken files, and check what happens when Gemini can't be used.

const AI_FOLDER = path.join(__dirname, "..", "..", "..", "AI");
const UVICORN = path.join(AI_FOLDER, ".venv", "bin", "uvicorn");
const AI_PORT = new URL(envConfig.AI_API_URL).port; // 8999, the address the backend tests use

let aiService: ChildProcess;
let worker: Worker;

const CSV = [
  "Invoice No,Date,Supplier,Customer,Subtotal,Tax,Total,Currency",
  "E-1,2026-10-01,Acme Office Supplies,Blue Sky Foods,1000.00,150.00,1150.00,USD",
  'E-2,15/10/2026,FastNet,Blue Sky Foods,"1,000.00",150.00,"1,180.00",EUR', // a wrong total, written differently
].join("\n");

/*--Start the real AI service and wait until it answers (at most 30 seconds)--*/
const startRealAiService = async () => {
  if (!fs.existsSync(UVICORN)) throw new Error("The AI service is not installed. Run: cd AI && uv sync");
  aiService = spawn(UVICORN, ["main:app", "--port", AI_PORT], {
    cwd: AI_FOLDER,
    env: { ...process.env, GEMINI_API_KEY: "" }, // no key: Gemini can't be used
    stdio: "ignore",
  });
  for (let i = 0; i < 300; i++) {
    try {
      if ((await fetch(`${envConfig.AI_API_URL}/health`)).ok) return;
    } catch {
      // not started yet
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error("The real AI service did not start within 30 seconds");
};

beforeAll(async () => {
  if (!envConfig.DATABASE_URL.endsWith("/docintel_test") || !envConfig.UPLOAD_FOLDER.endsWith("test-uploads")) {
    throw new Error("The tests must use the test database and test upload folder. Run them with: npm test");
  }
  await setupDatabase();
  await startRealAiService();
  worker = startWorker();
}, 40_000);

beforeEach(async () => {
  await worker.pause();
  await documentQueue.obliterate({ force: true });
  await query("TRUNCATE documents RESTART IDENTITY CASCADE");
  worker.resume();
});

afterAll(async () => {
  aiService?.kill();
  await worker.close(true);
  await documentQueue.close();
  await pool.end();
});

/*--Upload one file and wait until it is finished; returns the document as the API gives it--*/
const processFile = async (name: string, content: string) => {
  const response = await upload([name, content]);
  const id: number = response.body.data.documents[0].id;
  await waitUntilFinished(id);
  return getDocument(id);
};
const values = (invoice: any) => Object.fromEntries(Object.entries(invoice.fields).map(([name, field]: any) => [name, field.value]));

describe("Step 1 — The backend and the real AI service work together", () => {
  it("Reads a CSV with the real AI service and saves every invoice with clean values", async () => {
    const document = await processFile("two.csv", CSV);

    expect(document.status).toBe("done");
    expect(document.file_type).toBe("csv");
    expect(document.invoices.map(values)).toEqual([
      { invoice_number: "E-1", invoice_date: "2026-10-01", supplier_name: "Acme Office Supplies", customer_name: "Blue Sky Foods",
        subtotal: "1000.00", tax: "150.00", total: "1150.00", currency: "USD" },
      { invoice_number: "E-2", invoice_date: "2026-10-15", supplier_name: "FastNet", customer_name: "Blue Sky Foods",
        subtotal: "1000.00", tax: "150.00", total: "1180.00", currency: "EUR" },
    ]);
    expect(document.invoices[0].method).toBe("spreadsheet columns");
  });

  it("Saves the real AI service's problems: a wrong total needs review", async () => {
    const document = await processFile("two.csv", CSV);

    expect(document.invoices[0]).toMatchObject({ needs_review: false, validation_errors: [] });
    expect(document.invoices[1].needs_review).toBe(true);
    expect(document.invoices[1].validation_errors.map((error: any) => error.rule)).toEqual(["totals_match"]);
  });

  it("Corrects a value through the real AI service: it is cleaned and checked again", async () => {
    const document = await processFile("two.csv", CSV);
    const wrong = document.invoices[1];

    const refused = await request(app).patch(`/api/v1/invoices/${wrong.id}`).send({ fields: { total: "abc" } });
    expect(refused.status).toBe(400);
    expect(refused.body.message).toBe("total: 'abc' is not an amount");

    const fixed = await request(app).patch(`/api/v1/invoices/${wrong.id}`).send({ fields: { total: "1.150,00" } });
    expect(fixed.status).toBe(200);
    expect(fixed.body.data.fields.total).toMatchObject({ value: "1150.00", status: "corrected" });
    expect(fixed.body.data).toMatchObject({ needs_review: false, validation_errors: [] });
  });

  it("Fails a damaged PDF with the real AI service's clear message", async () => {
    const document = await processFile("broken.pdf", "%PDF-1.7 this is not a real pdf");

    expect(document.status).toBe("failed");
    expect(document.error).toBe("The PDF is damaged and can't be opened");
  });

  it("Fails cleanly, with the reason, when the AI is needed but Gemini can't be used", async () => {
    // A text file named .pdf: the AI service finds it is really text, and would need Gemini to read it
    const document = await processFile("fake.pdf", "just some text, not a pdf");

    expect(document.status).toBe("failed");
    expect(document.error).toBe("GEMINI_API_KEY is missing in AI/.env");
    expect(document.warnings).toContain("The file name doesn't match its content: it is really a CSV file");
  });

  it("Keeps a document done when meaning search can't be used, and says why", async () => {
    const document = await processFile("two.csv", CSV);

    expect(document.status).toBe("done");
    const line = document.history.find((entry: any) => entry.step === "meaning search");
    expect(line?.message).toContain("GEMINI_API_KEY is missing");
    const saved = await query("SELECT count(*)::int AS count FROM invoice_embeddings");
    expect(saved.rows[0].count).toBe(0);
  });

  it("Explains in a search that meaning search can't be used, while keyword search works", async () => {
    await processFile("two.csv", CSV);

    const meaning = await request(app).get("/api/v1/search?q=office furniture&mode=meaning");
    expect(meaning.status).toBe(503);
    expect(meaning.body.message).toContain("GEMINI_API_KEY is missing");

    const keyword = await request(app).get("/api/v1/search?q=acme");
    expect(keyword.body.data.invoices.map((invoice: any) => invoice.invoice_number)).toEqual(["E-1"]);
  });
});
