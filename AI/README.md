# AI-Powered Document Intelligence System — AI Service

Python (FastAPI) service that reads documents and extracts invoice data. The backend calls it.

## Run locally

Needs [uv](https://docs.astral.sh/uv/) and Tesseract OCR (`sudo apt install tesseract-ocr`).

```bash
uv sync
cp .env.example .env    # then add your free Gemini key from https://aistudio.google.com
uv run uvicorn main:app --reload --port 8000
```

Check it with http://localhost:8000/health.

## Try it

Open http://localhost:8000/docs, choose **POST /process**, click **Try it out**, add one or more files and click **Execute**.

Or from the terminal:

```bash
curl -F files=@invoice.pdf -F files=@prices.xlsx http://localhost:8000/process
```

## Files

| File | What it does |
|---|---|
| `main.py` | The API: `GET /health`, `POST /process` (text of each file), `POST /extract` (checked invoices), `POST /validate` (check again after a correction), `POST /embed` (meaning numbers for meaning search) |
| `process_file.py` | Checks size and type, picks the right reader, turns errors into clear messages |
| `file_type.py` | Finds the real file type from the file's first bytes |
| `read_pdf.py` | Reads PDFs page by page; scanned pages go to OCR |
| `read_image.py` | Cleans up images and reads them with OCR (also used for scanned PDF pages) |
| `read_spreadsheet.py` | Reads XLSX, XLS and CSV files, every sheet |
| `split_invoices.py` | Splits a document's pages into separate invoices by their invoice number |
| `spreadsheet_invoices.py` | Turns spreadsheet rows into invoices by matching column names (no AI) |
| `extract_prompt.txt` | The instructions given to Gemini |
| `extract_invoice.py` | Asks Gemini for the invoice fields, retries on errors, checks the AI's evidence |
| `clean_values.py` | Turns amounts, dates and currencies into one standard form |
| `extract_invoices.py` | Puts it all together: read the file, find the invoices, extract, clean and check them |
| `validate_invoice.py` | Checks each invoice: missing fields, wrong numbers, totals that don't add up, duplicates |
| `embed_text.py` | Turns texts into embeddings (768 numbers each) with Gemini's embedding model, for meaning search |
| `measure_meaning_search.py` | Measures meaning search with the real Gemini (12 sample invoices, 12 searches); the meaning-search cut-off was chosen from its results (`../test-results/task5_meaning_search_scores.txt`) |

## Tests

Tests are kept in one folder per Task of the assignment (`tests/task1/`, `tests/task2/`, ...).

```bash
uv run pytest                  # all tests
uv run pytest tests/task1 -v   # only Task 1
```

To save an easy-to-read results file (a PASS/FAIL checklist in plain words) into `../test-results/`:

```bash
uv run pytest tests/task1 --save-results
```

A few Task 2 and Task 5 tests call the real Gemini and use the free daily limit, so they are skipped unless you add `--real-gemini`.

| Test file | What it checks |
|---|---|
| `tests/task1/test_file_type.py` | Every type is recognised; Word, broken and unknown files are rejected |
| `tests/task1/test_read_pdf.py` | Digital, scanned, mixed, blank, 300-page, password-protected and damaged PDFs |
| `tests/task1/test_read_image.py` | PNG/JPG/TIFF, small/blurry/faded/speckled images, rotated pages, phone photos, multi-page TIFF, damaged images |
| `tests/task1/test_read_spreadsheet.py` | XLSX sheets, formulas without results, old XLS, CSV separators and encodings, empty and damaged files |
| `tests/task1/test_process_file.py` | Same result shape, renamed/empty/unsupported/too-big files, unexpected errors, the `/process` API with many files |
| `tests/task2/test_split_invoices.py` | Splitting pages into invoices by invoice number |
| `tests/task2/test_spreadsheet_invoices.py` | Reading invoices from spreadsheet columns without the AI |
| `tests/task2/test_extract_invoice.py` | Asking Gemini (with a fake Gemini), retries, model rotation, the evidence check |
| `tests/task2/test_clean_values.py` | Cleaning amounts, dates and currencies |
| `tests/task2/test_extract_invoices.py` | Field statuses, needs review, the `/extract` API |
| `tests/task3/test_missing_fields.py` | Missing and uncertain important fields |
| `tests/task3/test_wrong_numbers.py` | Negative amounts, credit notes, zero totals, tax, quantities, line math, dates |
| `tests/task3/test_totals.py` | Line items = subtotal, subtotal + tax = total, rounding allowance |
| `tests/task3/test_duplicates.py` | Duplicates and possible duplicates in one upload |
| `tests/task3/test_needs_review.py` | Validation errors on each invoice, and in the `/extract` API |
| `tests/task4/test_correct_invoice.py` | Checking an invoice again after a manual correction (`/validate`) |
| `tests/task5/test_embed_text.py` | Making embeddings (`/embed`): one request for many texts, retries, daily limit, broken answers, wrong input |
| `tests/task7/test_dataset.py` | The evaluation dataset: every file labeled, labels match the checks and can be read in the files, spreadsheets and broken files behave as labeled (no Gemini) |
| `tests/task7/test_run_evaluation.py` | The evaluation runner with a fake backend: waiting, failed, refused, stopping at the daily Gemini limit, continuing later |
| `tests/task7/test_score.py` | The scoring: right / wrong / missed / made up, success and failure rates, problems caught, times |
| `tests/task7/test_write_report.py` | The report shows the measured numbers and every mistake, and the saved report is up to date |

Sample files are made in code by `tests/make_files.py`. The only stored file is `tests/files/old_excel.xls`, because no installed library can write the old Excel format.

## Evaluation (Task 7)

The system was measured on a labeled dataset: made-up invoice files and an answer sheet with the right values.
The result, with real measured numbers, is in [`../test-results/evaluation_report.txt`](../test-results/evaluation_report.txt).

| File | What it does |
|---|---|
| `evaluation/make_dataset.py` | Makes the 29 sample documents (`evaluation/dataset/`) and their answer sheet (`evaluation/labels.json`) from one description per invoice. `--labels-only` changes only the answer sheet |
| `evaluation/run_evaluation.py` | Starts its own AI service (port 8100) and backend (port 3100) with their own database (`docintel_eval`), uploads every file through the backend API, and saves the results in `evaluation/results/raw_results.json`. Stops at the daily Gemini limit and continues later. `--no-gemini` is a free practice run |
| `evaluation/score.py` | Compares the results with the answer sheet: accuracy, success and failure rate, problems caught, times (`evaluation/results/real_run_scores.json`) |
| `evaluation/write_report.py` | Writes `test-results/evaluation_report.txt` from the scores (no number is typed by hand) |

```bash
uv run python evaluation/run_evaluation.py    # the real run: about 22 Gemini requests (Postgres and Redis must run)
uv run python evaluation/score.py             # no Gemini
uv run python evaluation/write_report.py      # no Gemini
```
