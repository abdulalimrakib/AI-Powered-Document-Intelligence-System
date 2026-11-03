import pytesseract
from fastapi import FastAPI, UploadFile

from extract_invoices import extract_invoices_from_file, mark_duplicates
from process_file import MAX_FILE_SIZE_BYTES, process_file

app = FastAPI(title="AI-Powered Document Intelligence System — AI Service")


@app.get("/health")
def health():
    # Also checks that the Tesseract OCR program is installed
    return {"status": "ok", "tesseract": str(pytesseract.get_tesseract_version())}


@app.post("/process")
def process(files: list[UploadFile]):
    """Upload one or more files (PDF, JPG, PNG, TIFF, XLSX, XLS, CSV) and get their text back.
    Each file is handled on its own, so one bad file never stops the others."""
    results = []
    for file in files:
        # Read at most 1 byte more than the limit: enough to know a file is too big,
        # without loading a huge file into memory.
        data = file.file.read(MAX_FILE_SIZE_BYTES + 1)
        results.append(process_file(file.filename or "unnamed", data))
    return results


@app.post("/extract")
def extract(files: list[UploadFile]):
    """Upload one or more files and get the invoices in them: invoice number, date, supplier, customer,
    subtotal, tax, total, currency and line items. Each field says if it was found, uncertain or missing.
    Each invoice is also checked (Task 3): its problems are in validation_errors, and needs_review is true
    when a person has to look at it."""
    results = []
    for file in files:
        data = file.file.read(MAX_FILE_SIZE_BYTES + 1)
        results.append(extract_invoices_from_file(file.filename or "unnamed", data))
    mark_duplicates(results)  # the same invoice twice in this upload, also across files
    return results
