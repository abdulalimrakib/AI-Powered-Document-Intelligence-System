# AI-Powered Document Intelligence System — Backend

Express API for the AI-Powered Document Intelligence System.

## Run locally

The backend needs Postgres (database) and Redis (job queue). Both run in Docker. Start them once from the project root:

```bash
docker compose up -d      # Postgres on port 5440, Redis on port 6380
```

Then, in this folder:

```bash
npm install
cp .env.example .env
npm run dev
```

The server runs at http://localhost:3002. Check it with http://localhost:3002/health.

| Script | What it does |
|---|---|
| `npm run dev` | Start with auto-reload (nodemon) |
| `npm start` | Start once |
| `npm run typecheck` | TypeScript check |

## Project structure

```
app.ts                      Express app: CORS, routes, error handling
server.ts                   Starts the server on PORT
config/env.config.ts        Settings from .env.local / .env
middleware/error.handler.ts JSON 404 and error responses
lib/db.ts                   Connects to Postgres; query() and transaction()
database/schema.sql         The tables; created automatically when the server starts
routes/document.route.ts    The /api/v1/documents routes
controllers/document.controller.ts  What each document route does
lib/upload.ts               Receives uploaded files (multer) and saves them in storage/uploads/
utils/response.ts           sendResponse() for the { success, message, statusCode, data } shape
lib/queue.ts                The background queue (BullMQ + Redis) and the worker
lib/processDocument.ts      The background work for one document: AI service -> save results -> done/failed
lib/aiService.ts            Sends a file to the AI service (POST /extract)
lib/invoiceDetails.ts       Puts an invoice together for the API: fields, line items, problems
lib/duplicates.ts           Finds duplicates among all saved invoices
lib/history.ts              addHistory(): one line in a document's history
routes/invoice.route.ts     The /api/v1/invoices routes
controllers/invoice.controller.ts   Manual corrections
routes/search.route.ts      The /api/v1/search route
controllers/search.controller.ts    Keyword search
utils/positiveNumber.ts     Reads ids and page numbers from the URL
```

## API

| Method | Path | What it does |
|---|---|---|
| POST | `/api/v1/documents` | Upload 1–20 files (form field `files`, max 50 MB each). Answers at once; each file gets the status `pending` |
| GET | `/api/v1/documents` | The list of documents, newest first. Filters: `?status=failed`, `?needs_review=true`, `?page=2`, `?limit=20` (max 100) |
| GET | `/api/v1/documents/:id` | One document: status, error, invoices (fields with status and evidence, line items, problems) and history |
| POST | `/api/v1/documents/:id/reprocess` | Try a document again: one that `failed`, or that is `done` but has invoices the AI could not read. Uses the saved file. Refused (409) while it is still pending/processing, or when nothing failed |
| PATCH | `/api/v1/invoices/:id` | Correct values: `{ "fields": { "total": "1,150.00" } }` (`""` or `null` empties a field). Mark as checked: `{ "reviewed": true }`. The values are cleaned and the invoice is checked again by the AI service (`POST /validate`); the change is saved in the history |
| GET | `/api/v1/search?q=acme` | Keyword search in invoice number, supplier, customer and file name (not case-sensitive; "inv 100" also finds "INV-100"). Exact invoice numbers first, then newest. `?page=` and `?limit=` (max 100) |

## Background processing

An upload only saves the file and answers at once. A worker (running inside the same program) then
processes the documents **one at a time**, so the free Gemini limit is not used up in parallel:

1. status `processing`
2. the file is sent to the AI service (`AI_API_URL`, which must be running)
3. the invoices, line items and problems are saved in one transaction
4. invoices are compared with earlier uploads to find duplicates
5. status `done`, or `failed` with the reason

If the AI service can't be reached, the worker tries again after 10 s and 20 s (3 attempts), then marks the
document `failed`. A broken file is not retried. After a restart, unfinished documents are put back in the queue.
Every step is written to `processing_history`.

## Database tables

| Table | What it holds |
|---|---|
| `documents` | One row per uploaded file, with its status: pending, processing, done or failed |
| `invoices` | One row per invoice found in a file: the values, each field's status and evidence, needs_review |
| `line_items` | The lines of each invoice |
| `validation_errors` | The problems found by the checks (missing fields, totals, duplicates ...) |
| `processing_history` | What happened to a document and when (uploaded, done, corrected ...) |

## Tests

```bash
npm test             # run all tests
npm run test:save    # run them and save an easy-to-read results file in ../test-results/
```

Postgres and Redis must be running (`docker compose up -d`). The tests never touch your real data:
they use their own database (`docintel_test`), their own queue and upload folder (`storage/test-uploads/`),
and a **fake AI service** (in `tests/task4/helpers.ts`), so no Gemini requests are used.

| Test file | What it checks |
|---|---|
| `tests/task4/upload.test.ts` | Uploads: good, wrong, empty, too big and too many files, safe file names |
| `tests/task4/processing.test.ts` | Background processing, retries when the AI service is down, restarts, duplicates |
| `tests/task4/documents.test.ts` | The document list (filters, pages) and one document with its results |
| `tests/task4/corrections.test.ts` | Manual corrections, marking as checked, wrong requests |
| `tests/task4/reprocess.test.ts` | Trying failed documents again, and when that is refused |
| `tests/task4/search.test.ts` | Keyword search |
