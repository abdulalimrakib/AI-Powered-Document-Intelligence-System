/*--Talking to the backend--*/
// Every page uses these functions instead of calling fetch() itself, so the backend address and the
// error handling live in one place. The website only talks to the backend (never to the AI or the database).
//
// Every backend answer looks like { success, message, statusCode, data }. These functions give back `data`,
// or throw an ApiError with a message that can be shown to the user as it is.
//
// Money is text ("1150.00"), exactly as the backend sends it. We never turn it into a number,
// so it is never rounded.

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3002";

/*--The shapes of the backend's answers--*/

export type DocumentStatus = "pending" | "processing" | "done" | "failed";

// One row of the documents list (GET /api/v1/documents)
export type DocumentSummary = {
  id: number;
  filename: string;
  file_type: string | null;
  file_size: number;
  status: DocumentStatus;
  error: string | null;
  invoice_count: number;
  review_count: number; // how many of its invoices need review
  processing_seconds: string | null;
  created_at: string;
  finished_at: string | null;
};

export type FieldStatus = "found" | "uncertain" | "missing" | "corrected";

// One field of an invoice, e.g. the total
export type Field = {
  value: string | null;
  status: FieldStatus;
  evidence: string | null; // the words in the document the value comes from
  note: string | null; // e.g. "corrected by hand"
};

export type LineItem = {
  position: number;
  description: string | null;
  quantity: string | null;
  unit_price: string | null;
  amount: string | null;
  evidence: string | null;
  problems: string[];
};

export type ValidationError = {
  id: number;
  field: string | null; // e.g. "total", or null for the whole invoice
  rule: string; // e.g. "totals_match"
  message: string; // in plain words
};

export const INVOICE_FIELDS = [
  "invoice_number", "invoice_date", "supplier_name", "customer_name", "subtotal", "tax", "total", "currency",
] as const;
export type InvoiceField = (typeof INVOICE_FIELDS)[number];

export type Invoice = {
  id: number;
  document_id: number;
  source: string; // where in the file, e.g. "Pages 1-2"
  method: string; // "gemini" or "spreadsheet columns"
  ai_model: string | null;
  error: string | null; // set when the AI could not read this invoice
  fields: Record<InvoiceField, Field>;
  line_items: LineItem[];
  validation_errors: ValidationError[];
  needs_review: boolean;
  reviewed_at: string | null; // when a person marked it as checked (null = not checked)
  warnings: string[];
  updated_at: string;
};

export type HistoryEntry = {
  id: number;
  step: string; // uploaded, processing, retry, done, failed, duplicate, corrected, reviewed, reprocess, meaning search
  message: string;
  details: unknown;
  invoice_id: number | null;
  created_at: string;
};

// One document with everything in it (GET /api/v1/documents/:id)
export type DocumentDetail = {
  id: number;
  filename: string;
  file_type: string | null;
  file_size: number;
  status: DocumentStatus;
  error: string | null;
  warnings: string[];
  invoice_count: number;
  processing_seconds: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  invoices: Invoice[];
  history: HistoryEntry[];
};

export type Page<T> = { page: number; limit: number; total: number; total_pages: number } & T;

export type UploadResult = {
  documents: { id: number; filename: string; file_size: number; status: DocumentStatus; created_at: string }[];
  rejected: { filename: string; reason: string }[];
};

export type SearchMode = "keyword" | "meaning";

export type SearchFilters = {
  date_from?: string;
  date_to?: string;
  total_min?: string;
  total_max?: string;
  currency?: string;
  supplier?: string;
  needs_review?: "true" | "false";
};

export type SearchResult = {
  id: number;
  document_id: number;
  filename: string;
  source: string;
  invoice_number: string | null;
  invoice_date: string | null;
  supplier_name: string | null;
  customer_name: string | null;
  total: string | null;
  currency: string | null;
  needs_review: boolean;
  // keyword search: "invoice number", "supplier", "customer", "file name", "line item", "invoice text" (null with
  // filters only); meaning search: "meaning"
  found_in: string | null;
  matched_text?: string | null; // keyword search: the matching line, or a short piece of the text
  similarity?: number; // meaning search: 0 (unrelated) to 1 (the same meaning)
};

export type SearchAnswer = Page<{
  invoices: SearchResult[];
  filters: Record<string, string>;
  not_in_meaning_search?: number; // meaning search: invoices that are not added yet
}>;

/*--An error with a message that can be shown to the user--*/
export class ApiError extends Error {
  statusCode: number; // 0 = the backend could not be reached
  data: unknown; // e.g. the list of rejected files of an upload

  constructor(message: string, statusCode: number, data: unknown = null) {
    super(message);
    this.statusCode = statusCode;
    this.data = data;
  }
}

/*--Send one request to the backend and give back its `data`--*/
const request = async <T>(path: string, options: RequestInit = {}): Promise<T> => {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, options);
  } catch {
    // fetch only says "Failed to fetch": say what it means
    throw new ApiError(`The backend can't be reached at ${API_URL}. Is it running? (cd backend && npm run dev)`, 0);
  }

  let body: { success?: boolean; message?: string; statusCode?: number; data?: unknown };
  try {
    body = await response.json();
  } catch {
    throw new ApiError(`The backend gave an answer that can't be read (error ${response.status})`, response.status);
  }
  if (!response.ok || !body.success) {
    throw new ApiError(body.message || `The backend answered with error ${response.status}`, response.status, body.data ?? null);
  }
  return body.data as T;
};

/*--Turn { page: 2, status: "" } into "?page=2" (empty values are left out)--*/
const queryString = (values: Record<string, string | number | undefined>) => {
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(values)) {
    if (value !== undefined && String(value).trim() !== "") params.set(name, String(value).trim());
  }
  const text = params.toString();
  return text ? `?${text}` : "";
};

/*--The API functions--*/

// Upload one or more files. They are processed in the background; each one starts as "pending".
export const uploadFiles = (files: File[]) => {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  return request<UploadResult>("/api/v1/documents", { method: "POST", body: form });
};

// The list of documents, newest first
export const getDocuments = (options: { status?: DocumentStatus | ""; needs_review?: "true" | ""; page?: number } = {}) =>
  request<Page<{ documents: DocumentSummary[] }>>(`/api/v1/documents${queryString(options)}`);

// One document with its invoices, problems and history
export const getDocument = (id: number | string) =>
  request<DocumentDetail>(`/api/v1/documents/${encodeURIComponent(String(id))}`);

// Try a failed document again
export const reprocessDocument = (id: number) =>
  request<{ id: number; filename: string; status: DocumentStatus }>(`/api/v1/documents/${id}/reprocess`, { method: "POST" });

// Correct values ({ total: "1,150.00" }; null or "" empties a field) and/or mark the invoice as checked
export const correctInvoice = (id: number, change: { fields?: Partial<Record<InvoiceField, string | null>>; reviewed?: boolean }) =>
  request<Invoice>(`/api/v1/invoices/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(change),
  });

// Search by keyword (default) or by meaning, with optional filters
export const searchInvoices = (options: { q?: string; mode?: SearchMode; page?: number; limit?: number } & SearchFilters) =>
  request<SearchAnswer>(`/api/v1/search${queryString(options)}`);
