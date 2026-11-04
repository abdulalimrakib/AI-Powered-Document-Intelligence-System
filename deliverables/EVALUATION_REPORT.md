# Evaluation report

- **Run:** 2026-11-04 09:57 to 10:02 (4.7 minutes), real run
- **Dataset:** 29 made-up documents with 30 invoices (22 read with Gemini), with a labeled answer sheet (`AI/evaluation/`)
- **Method:** every file was uploaded through the backend API, like the website does, and the result was compared with the answer sheet
- Every number below is measured and written by `AI/evaluation/write_report.py`; none is typed by hand.

## 1. Summary

| Measure | Result |
|---|---|
| Document success rate (files that should work) | 23 of 23 = 100.0% |
| Document failure rate (files that should work) | 0 of 23 = 0.0% |
| Broken or unsupported files handled as expected | 6 of 6 = 100.0% |
| **Extraction accuracy (fields right)** | **229 of 240 = 95.4%** |
| Values made up (not in the document) | 0 |
| Invoices with every field right | 26 of 30 |
| Line items fully right | 39 of 43 = 90.7% |
| Problems put in on purpose that were caught | 7 of 7 = 100.0% |
| Invoices with a mistake that were sent to review | 4 of 4 |
| Processing time per document (average / median) | 10.41 s / 5.26 s |

## 2. Documents: success and failure

Files that should work: 23, succeeded: 23. Invoices were split correctly (e.g. 3 invoices in one PDF, 1 invoice over 2 pages) in 23 of 23 documents.

Broken and unsupported files must fail or be refused with a clear reason:

| File | Expected | Result | Reason given |
|---|---|---|---|
| `f01_damaged.pdf` | failed | failed | No text was found to read (blank or unreadable pages) |
| `f02_password.pdf` | failed | failed | The PDF is password-protected |
| `f03_blank.pdf` | failed | failed | No text was found to read (blank or unreadable pages) |
| `f04_picture_without_text.png` | failed | failed | No text was found to read (blank or unreadable pages) |
| `f05_letter.docx` | refused | refused | This file type is not supported. Use PDF, JPG, PNG, TIFF, XLSX, XLS or CSV. |
| `f06_empty.csv` | refused | refused | The file is empty. |

## 3. Extraction accuracy

A field is right when it matches the answer sheet: money to the cent, dates as the same day, names ignoring capital letters. A field that is not on the invoice must come back empty.

| Kind of file | Documents | Invoices | Fields right | Accuracy |
|---|---|---|---|---|
| digital PDF | 14 | 16 | 128 of 128 | 100.0% |
| scanned PDF | 2 | 2 | 13 of 16 | 81.2% |
| image | 4 | 4 | 24 of 32 | 75.0% |
| spreadsheet | 3 | 8 | 64 of 64 | 100.0% |
| **all** | 23 | 30 | 229 of 240 | **95.4%** |

| Field | Right | Accuracy |
|---|---|---|
| Invoice number | 29 of 30 | 96.7% |
| Invoice date | 28 of 30 | 93.3% |
| Supplier | 30 of 30 | 100.0% |
| Customer | 30 of 30 | 100.0% |
| Subtotal | 28 of 30 | 93.3% |
| Tax | 28 of 30 | 93.3% |
| Total | 27 of 30 | 90.0% |
| Currency | 29 of 30 | 96.7% |

Wrong values: 8. Missed (written but not given): 3. Made up (not written but given): 0.

### Every field that was not right

| File | Invoice | Field | Result | Expected | Given |
|---|---|---|---|---|---|
| `s02_scanned_dirty.pdf` | SC-3002 | Subtotal | wrong | 36000.00 | 36600.00 |
| `s02_scanned_dirty.pdf` | SC-3002 | Total | wrong | 41400.00 | 41406.00 |
| `s02_scanned_dirty.pdf` | SC-3002 | Currency | missed | BDT | (empty) |
| `i02_phone_photo.jpg` | IMG-4002 | Invoice date | missed | 2026-10-12 | (empty) |
| `i02_phone_photo.jpg` | IMG-4002 | Subtotal | wrong | 192.50 | 192.59 |
| `i03_scan.tiff` | IMG-4003 | Invoice number | wrong | IMG-4003 | IMG-4663 |
| `i03_scan.tiff` | IMG-4003 | Invoice date | missed | 2026-10-13 | (empty) |
| `i03_scan.tiff` | IMG-4003 | Tax | wrong | 19.80 | 19.86 |
| `i03_scan.tiff` | IMG-4003 | Total | wrong | 151.80 | 151.88 |
| `i04_low_resolution.png` | IMG-4004 | Tax | wrong | 96.00 | 96.60 |
| `i04_low_resolution.png` | IMG-4004 | Total | wrong | 736.00 | 736.60 |

## 4. Validation

| Measure | Result |
|---|---|
| Problems put in on purpose that were caught | 7 of 7 |
| Invoices with a wrong or missing value sent to review | 4 of 4 |
| Clean invoices, read right, flagged anyway | 2 of 19 |
| 'Needs review' right | 28 of 30 = 93.3% |

## 5. Processing time

Seconds from upload until the document is done or failed, one document at a time.

| Kind of file | Documents | Average | Median | Fastest | Slowest |
|---|---|---|---|---|---|
| digital PDF | 14 | 18.13 s | 15.16 s | 3.04 s | 45.46 s |
| scanned PDF | 2 | 4.35 s | 4.35 s | 3.44 s | 5.26 s |
| image | 4 | 3.14 s | 3.13 s | 2.44 s | 3.84 s |
| spreadsheet | 3 | 0.69 s | 0.62 s | 0.62 s | 0.82 s |
| broken | 4 | 1.02 s | 1.02 s | 0.21 s | 1.83 s |
| **all** | 27 | 10.41 s | 5.26 s | 0.21 s | 45.46 s |

- Per invoice read with Gemini (average): 12.24 s. Most of the time is the Gemini request; spreadsheets are read without AI.
- Gemini models used: gemini-3.5-flash (15 invoices), gemini-3.5-flash-lite (7 invoices).
- Meaning search: every document was added.

## 6. What the results show

- **Digital PDFs and spreadsheets:** 100.0% and 100.0% of fields right.
- **11 of the 11 mistakes come from OCR, not from Gemini.** They are all in scans and photos, where Tesseract read the dotted zeros of the font as 6 or 9 (e.g. `IMG-4003` became `IMG-4663`). Gemini copied the OCR text exactly, as instructed.
- **The safety net worked:** a misread date with month 16 was left empty instead of guessed, misread amounts no longer added up and were flagged, every invoice with a mistake was sent to review (4 of 4), and no value was made up (0).
- Low-certainty pictures are sent to review even when read right (2 of 19 clean invoices): a quick human check is preferred over trusting a doubtful value.
- Free-tier model rotation worked: when the first model's daily limit was used up, the next model took over.

## 7. Corrections made after the run

The answer sheet had two mistakes, both proven from the files themselves, and was corrected openly:

- `d04_european_numbers.pdf`: the PDF font could not draw the € sign, so no currency is written; the system's empty answer is right.
- `d07_no_tax_dollar_sign.pdf`: a lone `$` is correctly marked 'uncertain', but by design only the important fields send an invoice to review.

Two measures were also made fairer after seeing the first numbers: problems are only judged on invoices the system read, and a review flag only counts as 'not needed' when the invoice was clean and read right. The files used in the run were not changed (checked byte for byte).

## 8. Limits of this evaluation

- The dataset is small (29 documents) and made up, with one layout and printed text. Real invoices, especially photos, will score lower.
- It is one run; Gemini can answer slightly differently between runs, even at temperature 0.
- Times were measured on one laptop, one document at a time, including the free tier's waits and retries.

## 9. Meaning search

Measured separately with the real Gemini embedding model on 12 sample invoices. The right invoice was first in 12 of 12 searches.
The search cut-off was chosen from these scores (`AI/evaluation/results/meaning_search_scores.txt`).

## How to repeat

```bash
cd AI
uv run python evaluation/run_evaluation.py   # the real run (about 22 Gemini requests)
uv run python evaluation/score.py            # the numbers (no Gemini)
uv run python evaluation/write_report.py     # this report
```
