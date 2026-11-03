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
| `main.py` | The API: `GET /health`, `POST /process` |
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

| Test file | What it checks |
|---|---|
| `tests/task1/test_file_type.py` | Every type is recognised; Word, broken and unknown files are rejected |
| `tests/task1/test_read_pdf.py` | Digital, scanned, mixed, blank, 300-page, password-protected and damaged PDFs |
| `tests/task1/test_read_image.py` | PNG/JPG/TIFF, small/blurry/faded/speckled images, rotated pages, phone photos, multi-page TIFF, damaged images |
| `tests/task1/test_read_spreadsheet.py` | XLSX sheets, formulas without results, old XLS, CSV separators and encodings, empty and damaged files |
| `tests/task1/test_process_file.py` | Same result shape, renamed/empty/unsupported/too-big files, unexpected errors, the `/process` API with many files |

Sample files are made in code by `tests/make_files.py`. The only stored file is `tests/files/old_excel.xls`, because no installed library can write the old Excel format.
