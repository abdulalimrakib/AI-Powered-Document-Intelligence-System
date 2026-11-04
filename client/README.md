# AI-Powered Document Intelligence System — Client

Next.js 15 (App Router) website for the AI-Powered Document Intelligence System: upload documents, follow their
processing, review and correct what was found, and search.

The website talks **only to the backend** (`NEXT_PUBLIC_API_URL`). It never calls the AI service, Gemini or the
database, and holds no secrets.

## Run locally

The backend must be running (see `../backend/README.md`).

```bash
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL = backend URL (default http://localhost:3002)
npm run dev                  # http://localhost:3000
```

| Script | What it does |
|---|---|
| `npm run dev` | Start with auto-reload |
| `npm run build` / `npm start` | Build and start the production version |
| `npm run lint` | ESLint check |
| `npm test` | Run the page tests |
| `npm run test:save` | Run them and save an easy-to-read results file in `../test-results/task6_frontend.txt` |

Stack: React 19, TypeScript, Tailwind CSS 4, shadcn/ui, next-themes, sonner.

## Pages

| Address | What it does |
|---|---|
| `/upload` | Drop or choose up to 20 files (PDF, JPG, PNG, TIFF, XLSX, XLS, CSV, up to 50 MB each). Files are checked before upload, and the server's reasons are shown for refused files |
| `/documents` | All documents with their status (Waiting, Processing, Done, Failed), invoices found and how many need review. Updates by itself every 2 seconds while something is unfinished. Filters: status, needs review |
| `/documents/[id]` | One document: each invoice's fields with status (found / uncertain / missing / corrected) and **evidence** from the document, problems found, line items, history. **Edit** a field (checked again by the backend), **Mark as checked**, **Process again** for failed documents |
| `/search` | Keyword or meaning search with filters (date, total, currency, supplier, needs review). Keyword results say where the words were found; meaning results show their closeness (0 to 1). The search is kept in the page address, so Back and bookmarks work |

## Project structure

```
src/app/<route>/page.tsx          The pages (upload, documents, documents/[id], search)
src/lib/api.ts                    All calls to the backend, the shapes of its answers, clear error messages
src/lib/checkFiles.ts             The upload rules (the same as the backend's)
src/lib/format.ts                 Readable sizes, dates, durations and field names
src/components/uploadForm.tsx     The upload form
src/components/documentList.tsx   The documents list with live progress
src/components/documentDetails.tsx One document: header, warnings, Process again, history
src/components/invoiceCard.tsx    One invoice: problems, fields with evidence, line items, corrections
src/components/searchPanel.tsx    The search form and results
src/components/statusBadge.tsx    The coloured status label
src/components/ui/                shadcn components (add more with npx shadcn add <name>)
```

Rules the pages follow:
- Money is shown exactly as the backend sends it (`"1150.00"`); the website never calculates with it.
- Text from documents is always shown as plain text, never as HTML.
- Every error becomes a message on the screen.
- Correcting a value never decides anything in the website: the backend and AI service clean it and run the same checks again.

## Tests

```bash
npm test             # run all tests
npm run test:save    # run them and save the results in ../test-results/task6_frontend.txt
```

Each page is shown in a pretend browser (jsdom) and used like a person would (Testing Library), with a
**fake backend** (`tests/task6/fakeBackend.ts`), so no backend, database or Gemini is needed.

| Test file | What it checks |
|---|---|
| `tests/task6/api.test.ts` | Talking to the backend: data, error messages, backend not running, empty filters left out |
| `tests/task6/upload.test.tsx` | The upload rules, choosing, dropping and removing files, uploading, the server's reasons |
| `tests/task6/documentList.test.tsx` | The list, live progress every 2 seconds (and stopping), filters, pages, empty and error states |
| `tests/task6/documentDetails.test.tsx` | Fields with status and evidence, problems, line items, history, text never as HTML, Process again |
| `tests/task6/corrections.test.tsx` | Correcting a value, refused values, emptying a field, Mark as checked and Undo |
| `tests/task6/search.test.tsx` | The search in the page address, keyword and meaning results, keyword fallback, pages |
