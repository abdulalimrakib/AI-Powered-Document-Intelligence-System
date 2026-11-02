import pytesseract
from fastapi import FastAPI, UploadFile

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
