import pytesseract
from fastapi import FastAPI

app = FastAPI(title="AI-Powered Document Intelligence System — AI Service")


@app.get("/health")
def health():
    # Also checks that the Tesseract OCR program is installed
    return {"status": "ok", "tesseract": str(pytesseract.get_tesseract_version())}
