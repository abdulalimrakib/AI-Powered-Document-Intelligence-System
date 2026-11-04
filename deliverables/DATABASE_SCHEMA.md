# Database schema

PostgreSQL 17 with the pgvector extension. The tables are defined in [`backend/database/schema.sql`](../backend/database/schema.sql)
and are created automatically when the backend starts.

```mermaid
erDiagram
    documents ||--o{ invoices : "has"
    documents ||--o{ processing_history : "has"
    invoices ||--o{ line_items : "has"
    invoices ||--o{ validation_errors : "has"
    invoices ||--o| invoice_embeddings : "has"
    invoices ||--o{ validation_errors : "is the duplicate in"

    documents {
        serial id PK
        text filename
        text file_path
        int file_size
        text file_type
        text status "pending, processing, done, failed"
        text error
        jsonb warnings
        int invoice_count
        numeric processing_seconds
        timestamptz created_at
        timestamptz started_at
        timestamptz finished_at
    }
    invoices {
        serial id PK
        int document_id FK
        text source "e.g. Pages 1-2"
        text method "gemini or spreadsheet columns"
        text ai_model
        text error
        text invoice_number
        date invoice_date
        text supplier_name
        text customer_name
        numeric subtotal
        numeric tax
        numeric total
        text currency
        jsonb field_details "status, evidence, note per field"
        boolean needs_review
        timestamptz reviewed_at
        jsonb warnings
        text text "the extracted text"
        text invoice_number_key "generated, for duplicates"
        text supplier_key "generated, for duplicates"
        timestamptz created_at
        timestamptz updated_at
    }
    line_items {
        serial id PK
        int invoice_id FK
        int position
        text description
        numeric quantity
        numeric unit_price
        numeric amount
        text evidence
        jsonb problems
    }
    validation_errors {
        serial id PK
        int invoice_id FK
        text field
        text rule "e.g. totals_match"
        text message
        int related_invoice_id FK "the other invoice of a duplicate"
        timestamptz created_at
    }
    processing_history {
        serial id PK
        int document_id FK
        int invoice_id FK
        text step "uploaded, processing, done, corrected ..."
        text message
        jsonb details
        timestamptz created_at
    }
    invoice_embeddings {
        int invoice_id PK, FK
        vector embedding "768 numbers"
        text model
        timestamptz created_at
    }
```

| Table | What it holds |
|---|---|
| `documents` | One row per uploaded file (metadata), with its status: pending, processing, done or failed |
| `invoices` | One row per invoice found in a file: the values, each field's status and evidence, needs_review, and the **extracted text** |
| `line_items` | The lines of each invoice |
| `validation_errors` | The problems found by the checks (missing fields, totals, duplicates ...) |
| `processing_history` | What happened to a document and when (uploaded, done, corrected ...) |
| `invoice_embeddings` | The meaning of each invoice (768 numbers), for meaning search. In its own table so the API never sends these numbers to the website |

- Money is `numeric` (exact, never rounded like a float) and is sent as text, e.g. `"1150.00"`.
- Deleting a document also deletes everything that belongs to it (`ON DELETE CASCADE`).
- Indexes make the common look-ups fast: status, document, duplicates, needs review, and an **HNSW** index
  on the embeddings so finding the closest ones stays fast with many invoices.
