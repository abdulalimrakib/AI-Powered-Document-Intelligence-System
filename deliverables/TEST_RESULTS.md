# Test results

**575 automated tests: 571 passed, 0 failed, 4 skipped.** Last run: 2026-11-05.

The 4 skipped tests call the real Gemini API. They are switched off by default to save the free daily limit and only
run with `--real-gemini`; all 4 passed when run.

| Part | Tool | Tests | Result |
|---|---|---|---|
| AI service (`AI/`) | pytest | 359 | 355 passed, 4 skipped |
| Backend API (`backend/`) | vitest + supertest | 160 | 160 passed |
| Website (`client/`) | vitest + Testing Library | 56 | 56 passed |

## What is tested

| Area (from the brief) | Tests | What is checked |
|---|---|---|
| Document processing and OCR (Task 1) | 45 | Real file type detected from content; digital and scanned PDFs (including 300 pages); OCR on PNG, JPG and TIFF, including blurry, faded, rotated and low-resolution images and phone photos |
| Spreadsheet parsing (Task 1–2) | part of the above | XLSX with several sheets, old XLS, CSV with other separators and encodings, invoices read from columns with different names |
| AI extraction (Task 2) | 149 | Splitting a file into invoices; strict JSON output; every value checked against its evidence in the document; cleaning dates, amounts and currencies; retries and model switching on Gemini limits |
| Validation (Task 3) | 61 | Missing fields, wrong numbers, line maths, subtotal + tax = total, duplicates, future dates, "needs review" |
| Backend API and background jobs (Task 4) | 79 + 15 | Upload, status, results, manual corrections, reprocessing failed jobs, retries when the AI service is down |
| Database and search (Task 5) | 74 + 26 | Keyword search, filters (date, amount, currency, supplier), semantic search with pgvector |
| Website (Task 6) | 56 | Every page used like a real user would: upload rules, live progress, fields with evidence, corrections, search |
| Integration and evaluation tools (Task 7) | 7 + 63 | The backend with the real AI service; the labeled dataset and the scoring that produce the [evaluation report](EVALUATION_REPORT.md) |

## Failure scenarios

| What goes wrong | What the system does |
|---|---|
| Damaged, password-protected, empty, unsupported or too-big file | Fails with a clear message; the server keeps running |
| File with the wrong extension | Read by its real type, with a warning |
| Blank page or unreadable scan | Warning; nothing is made up, and no Gemini request is spent |
| Gemini busy (503) or rate-limited (429) | Waits and tries again |
| Gemini daily limit used up | Switches to the next free model, then stops with a clear "try again at" message |
| Gemini returns a value that is not in the document | Value marked "uncertain" and the invoice sent to review |
| AI service down during processing | Job retried 3 times, then marked failed with the reason |
| Server restarts during processing | Unfinished documents are queued again |
| Invalid manual correction | Refused with the reason; nothing changes |
| Backend not reachable from the website | Clear message to the user |

## How the tests were checked

- To prove the tests catch bugs, the code was broken on purpose (in memory only) and the tests had to fail.
- The tests never touch real data: a separate database (`docintel_test`), and a fake Gemini, a fake AI service or a
  fake backend, so they use no Gemini requests.

## Run the tests

```bash
cd AI      && uv run pytest
cd backend && npm run typecheck && npm test     # needs: docker compose up -d
cd client  && npm run lint && npm run build && npm test
```
