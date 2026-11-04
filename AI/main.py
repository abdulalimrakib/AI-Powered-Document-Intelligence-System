import pytesseract
from fastapi import Body, FastAPI, HTTPException, UploadFile

from embed_text import EmbeddingNotAvailable, embed_texts
from extract_invoices import correct_invoice, extract_invoices_from_file, mark_duplicates
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


@app.post("/validate")
def validate(invoice: dict = Body(...), corrections: dict = Body(...)):
    """Check an invoice again after a person corrected some of its values (used by the backend).
    `invoice` is {"fields", "line_items", "text"}; `corrections` is e.g. {"total": "1,150.00"}.
    Returns the invoice with the cleaned values, its validation_errors and needs_review."""
    try:
        return correct_invoice(invoice, corrections)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except (KeyError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail="The invoice is not in the expected shape")


@app.post("/embed")
def embed(texts: list = Body(...), purpose: str = Body("document")):
    """Turn texts into embeddings (768 numbers each) for meaning search (used by the backend).
    `texts` is e.g. ["Acme Ltd, office chairs"]; `purpose` is "document" (an invoice to store) or
    "search" (the words a person searches for). Returns {"model", "embeddings": [[...], ...]}."""
    try:
        return embed_texts(texts, purpose)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except EmbeddingNotAvailable as error:  # not our fault, and trying later can work
        raise HTTPException(status_code=503, detail=str(error))
