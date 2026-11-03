-- The database tables. The backend runs this file every time it starts.
-- "IF NOT EXISTS" means: create it the first time, and leave it alone after that (no data is lost).
--
-- documents ──< invoices ──< line_items
--     │             └──────< validation_errors
--     └──< processing_history
-- (──< means "one has many". Deleting a document also deletes everything that belongs to it.)
--
-- Money is "numeric": exact, never rounded like a float. Postgres sends it to the backend as text ("1150.00").

CREATE EXTENSION IF NOT EXISTS vector; -- for meaning search in Task 5

/*--One row per uploaded file--*/
CREATE TABLE IF NOT EXISTS documents (
  id                 serial PRIMARY KEY,
  filename           text NOT NULL,                 -- the name the user uploaded, e.g. "october.pdf"
  file_path          text NOT NULL,                 -- where the backend saved it (needed to process it again)
  file_size          integer NOT NULL,              -- in bytes
  file_type          text,                          -- pdf, png, xlsx ... (found by the AI service)
  status             text NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'processing', 'done', 'failed')),
  error              text,                          -- why it failed, in plain words
  warnings           jsonb NOT NULL DEFAULT '[]',   -- e.g. ["Page 3: no text found (blank page?)"]
  invoice_count      integer NOT NULL DEFAULT 0,
  processing_seconds numeric(10, 2),
  created_at         timestamptz NOT NULL DEFAULT now(), -- when it was uploaded
  started_at         timestamptz,                   -- when the worker started on it
  finished_at        timestamptz                    -- when it became done or failed
);

/*--One row per invoice found in a document (a PDF can hold many invoices)--*/
CREATE TABLE IF NOT EXISTS invoices (
  id             serial PRIMARY KEY,
  document_id    integer NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
  source         text NOT NULL,                     -- where in the file, e.g. "Pages 1-2"
  method         text NOT NULL,                     -- "gemini" or "spreadsheet columns"
  ai_model       text,                              -- which Gemini model read it
  error          text,                              -- set when the AI could not read this invoice

  -- The values, in columns, so they can be searched, filtered and sorted.
  invoice_number text,
  invoice_date   date,
  supplier_name  text,
  customer_name  text,
  subtotal       numeric(14, 2),
  tax            numeric(14, 2),
  total          numeric(14, 2),
  currency       text,

  -- For every field: its status (found / uncertain / missing / corrected), evidence and note.
  -- e.g. {"total": {"status": "found", "evidence": "Total: USD 1,150.00", "note": null}, ...}
  field_details  jsonb NOT NULL DEFAULT '{}',

  needs_review   boolean NOT NULL DEFAULT false,
  reviewed_at    timestamptz,                       -- when a person marked it as checked
  warnings       jsonb NOT NULL DEFAULT '[]',
  text           text,                              -- the invoice's text, as read from the file
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),

  -- Only letters and digits, in capitals ("inv-001" and "INV 001" both become "INV001").
  -- Postgres keeps these up to date by itself. Used to find duplicates of earlier uploads.
  invoice_number_key text GENERATED ALWAYS AS (upper(regexp_replace(invoice_number, '[^[:alnum:]]', '', 'g'))) STORED,
  supplier_key       text GENERATED ALWAYS AS (upper(regexp_replace(supplier_name, '[^[:alnum:]]', '', 'g'))) STORED
);

/*--The lines of an invoice--*/
CREATE TABLE IF NOT EXISTS line_items (
  id          serial PRIMARY KEY,
  invoice_id  integer NOT NULL REFERENCES invoices (id) ON DELETE CASCADE,
  position    integer NOT NULL,                     -- 1 for the first line, 2 for the second ...
  description text,
  quantity    numeric,                              -- no fixed decimals: 2, 1.5, 0.333
  unit_price  numeric(14, 2),
  amount      numeric(14, 2),
  evidence    text,
  problems    jsonb NOT NULL DEFAULT '[]'
);

/*--The problems found by the checks of Task 3--*/
CREATE TABLE IF NOT EXISTS validation_errors (
  id         serial PRIMARY KEY,
  invoice_id integer NOT NULL REFERENCES invoices (id) ON DELETE CASCADE,
  field      text,                                  -- e.g. "total" or "line item 2"; empty = the whole invoice
  rule       text NOT NULL,                         -- e.g. "totals_match", "duplicate_invoice"
  message    text NOT NULL,                         -- in plain words, shown to the reviewer
  -- For a duplicate: the other invoice. When either one is changed or deleted, this problem goes away.
  related_invoice_id integer REFERENCES invoices (id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now()
);

/*--What happened to a document, and when--*/
CREATE TABLE IF NOT EXISTS processing_history (
  id          serial PRIMARY KEY,
  document_id integer NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
  invoice_id  integer REFERENCES invoices (id) ON DELETE SET NULL, -- set for corrections of one invoice
  step        text NOT NULL,                        -- uploaded, processing, retry, done, failed, duplicate, corrected, reprocess
  message     text NOT NULL,                        -- e.g. "Done in 4.2 seconds: 2 invoices found"
  details     jsonb,                                -- e.g. {"field": "total", "old": "1180.00", "new": "1150.00"}
  created_at  timestamptz NOT NULL DEFAULT now()
);

/*--Indexes: they make the common look-ups fast (like the index at the back of a book)--*/
CREATE INDEX IF NOT EXISTS documents_status_idx ON documents (status);
CREATE INDEX IF NOT EXISTS invoices_document_idx ON invoices (document_id);
CREATE INDEX IF NOT EXISTS invoices_duplicate_idx ON invoices (invoice_number_key, supplier_key);
CREATE INDEX IF NOT EXISTS invoices_needs_review_idx ON invoices (needs_review);
CREATE INDEX IF NOT EXISTS line_items_invoice_idx ON line_items (invoice_id);
CREATE INDEX IF NOT EXISTS validation_errors_invoice_idx ON validation_errors (invoice_id);
CREATE INDEX IF NOT EXISTS validation_errors_related_idx ON validation_errors (related_invoice_id);
CREATE INDEX IF NOT EXISTS processing_history_document_idx ON processing_history (document_id);
