# AI prompts and AI-assisted development

Deliverable 9: the prompts the system sends to an AI model, and an open note on how AI tools were used to build it.

## 1. The prompts inside the system

The system calls Google Gemini (free tier) in two places, both in the AI service (`AI/`), the only part that holds
the API key.

| What | Code | Model |
|---|---|---|
| Reading an invoice (one request per invoice; spreadsheets with clear columns need none) | `AI/extract_invoice.py` | `gemini-3.5-flash`, then the next free model when its daily limit is used up |
| Meaning search (a short summary of each invoice, and each search) | `AI/embed_text.py` | `gemini-embedding-001` |

### The invoice prompt

Gemini only ever gets **text** (PDF text or OCR output), never images. The full system instruction
([`AI/extract_prompt.txt`](../AI/extract_prompt.txt)):

```text
You read the text of ONE business document (an invoice or a receipt) and fill in the invoice fields.
The text may come from OCR (a scanned page), so it can contain small reading mistakes.

Rules:
1. Use only what is written in the text. Never guess, never use outside knowledge, never fill in a "likely" value.
2. If a field is not in the text, set its value and its evidence to null.
3. Copy every value exactly as it is written. Keep the original date format, number format and currency sign.
   Do not convert, round, translate or reformat anything.
4. Do not calculate anything. If the total is not written, the total is null, even if you could add up the lines.
5. "evidence" must be copied word for word from the text: the shortest piece of text that shows the value,
   normally one line or part of a line, including its label. Example: "Total: $1,150.00".
6. supplier_name is the company that sends the invoice and receives the money (seller, vendor, "From").
   customer_name is the company or person who has to pay ("Bill to", "Customer", "Sold to").
7. subtotal is the amount before tax. tax is the tax amount (VAT, GST, sales tax), not the tax percentage.
   total is the final amount to pay.
8. currency: copy the currency code or sign as written, for example "USD", "$", "€" or "Tk". If none is written, null.
9. line_items: one entry for each product or service line, in the order they appear. Copy the description,
   quantity, unit price and line amount exactly; use null for anything that is not written.
   The evidence of a line item is the whole line as written. If there are no line items, return an empty list.
```

The document text is sent as the message, between `<<<` and `>>>` markers, so it can't be mixed up with the rules.

**Why it is written this way**

- **Never guess, missing = null (rules 1–2):** a missing value stays empty, and the invoice is marked *needs review*.
- **Copy, don't convert or calculate (rules 3–4):** our own code cleans dates, amounts and currencies with fixed,
  tested rules and exact `Decimal` money. If the AI added up the lines itself, a wrong total would look right.
- **Evidence for every value (rule 5):** lets the code prove each value is really in the document.

**Settings:** `temperature=0` (same text, same answer), JSON output with a fixed schema (`response_schema`), and every
value is a string or null, so no amount is rounded. An answer in the wrong shape is asked once more, then fails clearly.

### The answer is checked, not trusted

1. **Evidence check:** a value is accepted only if its evidence is found in the document and the value is in its
   evidence. Otherwise the field is marked *uncertain*, with the reason.
2. **Cleaning:** a value that can't be cleaned safely (e.g. a lone `$`, which could be any dollar) is marked *uncertain*.
3. **Validation:** missing fields, subtotal + tax = total, line maths, odd dates and duplicates. Any problem marks
   the invoice *needs review*.
4. **Blank pages are never sent** to Gemini, so no request is wasted.

### Meaning search

No written prompt: the embedding model turns text into 768 numbers. Invoices are stored as a short summary
(`From: Acme Ltd. Bought: Office chairs; Desk lamps`, task type `RETRIEVAL_DOCUMENT`), and searches use the typed
words (`RETRIEVAL_QUERY`). The cut-off for which results are shown was chosen from real measured scores
(section 9 of the [evaluation report](EVALUATION_REPORT.md)).

## 2. How the prompt was tested

- **Fake Gemini (every test run):** the normal tests use a fake Gemini, so they use no free requests
  ([test results](TEST_RESULTS.md)).
- **Real Gemini (by hand):** 4 tests run only with `--real-gemini`. All passed, including "a receipt without a written
  total gives `total = null`, not the sum of the lines".
- **Evaluation** on 29 labeled documents through the real system
  ([evaluation report](EVALUATION_REPORT.md)): **100%** of fields right on digital
  PDFs, **95.4%** on all files, **0** made-up values. All 11 wrong fields came from OCR misreading digits in
  scans; every affected invoice was sent to review.
- The prompt was **not changed** after it was first written, because no mistake was caused by it.

## 3. How AI was used to build this project

This project was built with heavy help from **Claude Code** (Anthropic's coding assistant, model Claude Opus 5.5),
from 2026-11-02 to 2026-11-04.

| Who | What |
|---|---|
| **Me (the candidate)** | Set the rules (simple code a junior developer can read, free AI model only, one task at a time); made the main choices (Gemini free tier, switching models when a daily limit is used up); reviewed and approved every step; installed Tesseract and set the API key (never shared in the chat); tested the website by hand; arranged the architecture diagram; made all commits. |
| **Claude Code** | Proposed the plan for each task; wrote most of the code, tests, evaluation tools, documentation and the Gemini prompt; ran the tests and the evaluation. |

**How the AI's work was checked**

- Tests for every task: 574 in total, all passing ([test results](TEST_RESULTS.md)).
- The tests were tested: the code was broken on purpose (in memory only) and the tests had to fail. Weak tests were
  made stronger.
- No number is typed by hand: the evaluation report is written by a script from the saved results.
- Only made-up invoices were sent to Gemini; secrets live only in `.env` files.

Mistakes by the AI that were caught this way include wrong labels in the evaluation answer sheet (corrected openly in
the report), blank PDFs still being sent to Gemini (fixed, with a test), and some tests that passed on broken code
(made stronger).

**Example prompts I gave Claude Code** (word for word):

```text
Make everything in simple don't make anything complecated for the fresher ... keep default one which naming style
exist from the begenning ... when we need to add any thing that we will create folder.
```

```text
We will complete the assignment Task by Task. ... lets start the TASK 1 which is document processing. first You have
to explain How we gonna do this step by step because doing I have to understand what is going on and why this is
currect and make everything in simple and easy to understand and use essay and common words
```

After each explanation, every step was started separately (`start with step 1`, `go on to step 2`, ...).
