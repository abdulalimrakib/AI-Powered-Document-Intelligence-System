# Test results

Every file in this folder is written by the tests themselves: a plain-language PASS/FAIL checklist, grouped by
Step. Nothing in here is typed by hand.

**Totals (last run):** 574 automatic checks: 571 passed and 3 skipped (real-Gemini checks, see below), none failed.

**The evaluation with real measured numbers** (accuracy, processing time, success and failure rate) is in
[`evaluation_report.txt`](evaluation_report.txt).

| Part | Checks | How to run them again |
|---|---|---|
| AI service (Python, pytest) | 359 (4 of them call the real Gemini and only run with `--real-gemini`; in the saved Task 2 file those 3 show as SKIP) | `cd AI && uv run pytest tests/task<N> --save-results` |
| Backend (TypeScript, vitest + supertest) | 160 | `cd backend && npm run test:save` |
| Website (TypeScript, vitest + Testing Library) | 55 | `cd client && npm run test:save` |
| Measurement of meaning search (real Gemini) | 12 searches | `cd AI && uv run python measure_meaning_search.py` |
| Evaluation (real system, real Gemini, labeled dataset) | 29 documents, 30 invoices | see "How to repeat" in `evaluation_report.txt` |

## What the brief asks to test, and where it is tested

| The brief asks for tests of | What is checked (examples) | Results file |
|---|---|---|
| **Document processing** | The real file type is found from its content (a renamed file is noticed); PDFs are read page by page; every file gets the same result shape; one bad file never stops the others | `task1_document_processing.txt` (Steps 1, 2, 5–6) |
| **OCR** | Scanned PDF pages and PNG/JPG/TIFF images are read; small, blurry, faded, speckled, rotated pages and phone photos; multi-page TIFF; damaged images | `task1_document_processing.txt` (Steps 2–3) |
| **Spreadsheet parsing** | XLSX with several sheets, formulas without saved results, old XLS, CSV with other separators and encodings; invoices read from columns with different names, with line items on another sheet | `task1_document_processing.txt` (Step 4), `task2_ai_extraction.txt` (Step 2a) |
| **AI extraction** | Splitting a document into invoices; the instructions and strict settings sent to Gemini; retries when Gemini is busy; switching models when a daily limit is used up; every value checked against its evidence in the document; cleaning amounts, dates and currencies; "found / uncertain / missing" per field. 4 checks call the real Gemini | `task2_ai_extraction.txt` |
| **Validation** | Missing and uncertain fields; negative amounts, credit notes, zero totals, too much tax, quantities, line maths, dates in the future; line items = subtotal, subtotal + tax = total; duplicates; checking again after a manual correction | `task3_validation.txt`, `task4_ai_service.txt` |
| **API endpoints** | Upload, document list and details, background processing, corrections, re-processing, keyword search, filters, meaning search (backend); `/process`, `/extract`, `/validate`, `/embed` (AI service) | `task4_backend_api.txt`, `task5_database_search.txt`, `task5_ai_service.txt`, and the API steps in `task1`–`task3` |
| **Failure scenarios** | See the list below | spread over all files |
| The website (Task 6) | Every page used like a person would, with a fake backend: upload rules, live progress, fields with evidence, corrections, search | `task6_frontend.txt` |
| The parts working together | The backend with the **real** AI service (no fake): a CSV read and saved, a wrong total flagged, a correction checked again, a damaged PDF, Gemini not available | `task7_integration.txt` |
| The evaluation tools | The labeled dataset matches its files and the checks; running, scoring and the report (with fakes, no Gemini) | `task7_evaluation_tools.txt` |

### Failure scenarios that are tested

| What goes wrong | What the system does | Where |
|---|---|---|
| Damaged, password-protected, empty, unsupported or too-big file | Fails with a clear message; the server keeps running | `task1`, `task4_backend_api`, `task7_integration` |
| A file renamed to the wrong extension | Read by its real type, with a warning | `task1`, `task7_integration` |
| A blank page, an unreadable scan | Warning per page; nothing is made up | `task1` |
| Gemini busy (503) or the per-minute limit (429) | Waits and tries again | `task2`, `task5_ai_service` |
| The daily Gemini limit used up | Switches to the next model, then stops and says when to try again | `task2`, `task5_ai_service` |
| Gemini gives a value that is not in the document | The value is not trusted: marked 'uncertain', with the reason | `task2` |
| A broken answer from Gemini | Asked once more, then a clear error | `task2`, `task5_ai_service` |
| The AI service is down while processing | The job is tried again (3 times), then the document fails with the reason | `task4_backend_api` |
| The server restarts during processing | Unfinished documents are put back in the queue | `task4_backend_api` |
| A wrong value typed in a correction | Refused with the reason, nothing changes | `task4_backend_api`, `task4_ai_service`, `task6_frontend` |
| Meaning search not available | Documents are still saved; search says why and keyword search still works | `task5_database_search`, `task7_integration`, `task6_frontend` |
| The backend is not running | The website says so in plain words | `task6_frontend` |

## How we know the tests themselves work

For every Task, the code was broken on purpose **in memory only** (for example "the last cent is not included in
a filter", "document text shown as HTML", "the AI answer has another shape"), and we checked that the tests then
fail. The files on disk were never changed (checked with checksums). Where a broken version slipped through, a
test was added or made stricter.

## Safety of the tests

- The backend tests use their own database (`docintel_test`), queue and upload folder, never the real ones.
- The tests use a fake Gemini, a fake AI service or a fake backend, so they cost no free Gemini requests.
  The few real-Gemini checks are switched off unless asked for, and use made-up invoices only.
- `task7_integration` starts the real AI service **without** a Gemini key, so it can never spend a request.
