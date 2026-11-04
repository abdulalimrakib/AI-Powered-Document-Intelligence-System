# Deliverables

**AI-Powered Document Intelligence System**, Senior AI Engineer assignment.

| # | Deliverable | Where |
|---|---|---|
| 1 | Git repository with the source code | https://github.com/abdulalimrakib/AI-Powered-Document-Intelligence-System |
| 2 | README and setup instructions | [`../README.md`](../README.md) |
| 3 | Architecture diagram | [`architecture.png`](architecture.png) (source: [`architecture.drawio`](architecture.drawio)) |
| 3 | Database schema | [`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md) |
| 4 | Working backend API and frontend | [`../backend/`](../backend/README.md) (API routes listed there) and [`../client/`](../client/README.md) |
| 5 | PDF, image, Excel and CSV processing | [`../AI/`](../AI/README.md) |
| 6 | Automated tests and test results | [`TEST_RESULTS.md`](TEST_RESULTS.md): 574 tests, 0 failed |
| 7 | Evaluation report with measured metrics | [`EVALUATION_REPORT.md`](EVALUATION_REPORT.md) |
| 8 | Recorded walkthrough | *Video link: to be added* |
| 9 | AI prompts and AI-use disclosure | [`AI_PROMPTS_AND_AI_USE.md`](AI_PROMPTS_AND_AI_USE.md) |

## Results at a glance

Measured on 29 labeled documents (30 invoices) through the real system:

| Measure | Result |
|---|---|
| Fields extracted correctly (digital PDFs) | 100% |
| Fields extracted correctly (all files, including scans and photos) | 95.4% |
| Valid documents processed successfully (failure rate) | 100% (0%) |
| Broken or unsupported files rejected with a clear error | 6 of 6 |
| Processing time per document (average / median) | 10.41 s / 5.26 s |
| Made-up values | 0 |
| Invoices with a mistake that were flagged for review | 4 of 4 |

## Main design choices

- **Three parts:** a Next.js website, an Express API (PostgreSQL + Redis/BullMQ for background jobs) and a Python
  AI service (PyMuPDF, Tesseract OCR, openpyxl, Google Gemini).
- **No made-up values:** every AI value must come with evidence that is checked against the document; anything
  missing or doubtful is left empty and flagged for review.
- **Exact money:** `Decimal` in Python, `numeric` in PostgreSQL, strings in JSON.
- **Semantic search** uses pgvector inside PostgreSQL, so no separate vector database is needed.
- **Free-tier friendly:** one Gemini request per invoice, text instead of images, retries, and switching to the next
  free model when one model's daily limit is used up.
