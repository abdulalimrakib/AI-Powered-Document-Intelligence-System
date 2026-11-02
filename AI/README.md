# AI-Powered Document Intelligence System — AI Service

Python (FastAPI) service that reads documents and extracts invoice data. The backend calls it.

## Run locally

Needs [uv](https://docs.astral.sh/uv/) and Tesseract OCR (`sudo apt install tesseract-ocr`).

```bash
uv sync
uv run uvicorn main:app --reload --port 8000
```

Check it with http://localhost:8000/health.
