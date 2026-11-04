import { vi } from "vitest";
import type { DocumentDetail, DocumentSummary, Field, Invoice, SearchResult } from "@/lib/api";

/*--A fake backend: the website's fetch() calls come here instead of going to the real backend--*/
// Each test says what to answer, e.g.
//   const backend = startFakeBackend((call) => call.path === "/api/v1/documents" ? ok({ documents: [] }) : undefined);
// and can look at the calls the website made: backend.calls[0].path, .method, .query, .body
export type Call = { method: string; path: string; query: URLSearchParams; body: unknown };
type Answer = { status: number; body: unknown } | "unreachable";

export const startFakeBackend = (answer: (call: Call) => Answer | undefined) => {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn(async (address: string, options: RequestInit = {}) => {
    const url = new URL(address);
    const body = typeof options.body === "string" ? JSON.parse(options.body) : options.body ?? null;
    const call = { method: options.method ?? "GET", path: url.pathname, query: url.searchParams, body };
    calls.push(call);
    const reply = answer(call) ?? notFound(call);
    if (reply === "unreachable") throw new TypeError("Failed to fetch"); // what a browser does when nothing answers
    return new Response(JSON.stringify(reply.body), { status: reply.status, headers: { "Content-Type": "application/json" } });
  }));
  return { calls };
};

/*--Answers in the backend's shape: { success, message, statusCode, data }--*/
export const ok = (data: unknown, status = 200) => ({ status, body: { success: true, message: "OK", statusCode: status, data } });
export const fail = (status: number, message: string, data: unknown = null) =>
  ({ status, body: { success: false, message, statusCode: status, data } });
const notFound = (call: Call) => fail(404, `Route not found: ${call.method} ${call.path}`);

/*--Sample data (change any value)--*/
export const field = (value: string | null, extra: Partial<Field> = {}): Field => ({
  value, status: value === null ? "missing" : "found", evidence: value, note: null, ...extra,
});

export const sampleInvoice = (extra: Partial<Invoice> = {}): Invoice => ({
  id: 11,
  document_id: 5,
  source: "Page 1",
  method: "gemini",
  ai_model: "gemini-3.5-flash",
  error: null,
  fields: {
    invoice_number: field("INV-001", { evidence: "Invoice No: INV-001" }),
    invoice_date: field("2026-10-15"),
    supplier_name: field("Acme Ltd"),
    customer_name: field("Blue Sky Foods"),
    subtotal: field("1000.00"),
    tax: field("150.00"),
    total: field("1150.00", { evidence: "Total: $1,150.00" }),
    currency: field("USD"),
  },
  line_items: [{ position: 1, description: "Office chairs", quantity: "10", unit_price: "100.00", amount: "1000.00", evidence: null, problems: [] }],
  validation_errors: [],
  needs_review: false,
  reviewed_at: null,
  warnings: [],
  updated_at: "2026-11-04T08:00:00Z",
  ...extra,
});

export const sampleDocument = (extra: Partial<DocumentDetail> = {}): DocumentDetail => ({
  id: 5,
  filename: "october.pdf",
  file_type: "pdf",
  file_size: 120_000,
  status: "done",
  error: null,
  warnings: [],
  invoice_count: 1,
  processing_seconds: "4.20",
  created_at: "2026-11-04T08:00:00Z",
  started_at: "2026-11-04T08:00:01Z",
  finished_at: "2026-11-04T08:00:05Z",
  invoices: [sampleInvoice()],
  history: [
    { id: 1, step: "uploaded", message: 'Uploaded "october.pdf" (118 KB)', details: null, invoice_id: null, created_at: "2026-11-04T08:00:00Z" },
    { id: 2, step: "done", message: "Done in 4.2 seconds: 1 invoice found, 0 need review", details: null, invoice_id: null, created_at: "2026-11-04T08:00:05Z" },
  ],
  ...extra,
});

export const sampleSummary = (extra: Partial<DocumentSummary> = {}): DocumentSummary => ({
  id: 5,
  filename: "october.pdf",
  file_type: "pdf",
  file_size: 120_000,
  status: "done",
  error: null,
  invoice_count: 1,
  review_count: 0,
  processing_seconds: "4.20",
  created_at: "2026-11-04T08:00:00Z",
  finished_at: "2026-11-04T08:00:05Z",
  ...extra,
});

export const page = <T extends object>(items: T, total: number, pageNumber = 1, limit = 20) =>
  ({ ...items, page: pageNumber, limit, total, total_pages: Math.ceil(total / limit) });

export const sampleResult = (extra: Partial<SearchResult> = {}): SearchResult => ({
  id: 11,
  document_id: 5,
  filename: "october.pdf",
  source: "Page 1",
  invoice_number: "INV-001",
  invoice_date: "2026-10-15",
  supplier_name: "Acme Ltd",
  customer_name: "Blue Sky Foods",
  total: "1150.00",
  currency: "USD",
  needs_review: false,
  found_in: "supplier",
  matched_text: null,
  ...extra,
});
