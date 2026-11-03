import time

from clean_values import clean_amount, clean_currency, clean_date, clean_text
from extract_invoice import INVOICE_FIELDS, check_evidence, extract_invoice
from process_file import process_file
from read_image import LOW_CONFIDENCE
from split_invoices import split_into_invoices
from spreadsheet_invoices import invoices_from_spreadsheet
from validate_invoice import find_duplicates, problem, readable, validate_invoice

# Which cleaning function from Step 4 is used for each field.
CLEANERS = {
    "invoice_number": clean_text,
    "invoice_date": clean_date,
    "supplier_name": clean_text,
    "customer_name": clean_text,
    "subtotal": clean_amount,
    "tax": clean_amount,
    "total": clean_amount,
    "currency": clean_currency,
}


def extract_invoices_from_file(filename: str, data: bytes) -> dict:
    """Task 1 + Task 2: read a file, find the invoices in it and extract their fields."""
    start = time.perf_counter()
    reading = process_file(filename, data)  # Task 1
    result = {
        "filename": filename,
        "file_type": reading["file_type"],
        "invoice_count": 0,
        "invoices": [],
        "warnings": reading["warnings"],
        "error": reading["error"],
        "processing_seconds": 0.0,
    }

    if reading["error"] is None:
        if reading["pages"]:
            result["invoices"] = invoices_from_pages(reading["pages"])
        else:
            result["invoices"], sheet_warnings = invoices_from_sheets(reading["sheets"])
            result["warnings"] += sheet_warnings
        result["invoice_count"] = len(result["invoices"])

    result["processing_seconds"] = round(time.perf_counter() - start, 2)
    return result


def invoices_from_pages(pages: list[dict]) -> list[dict]:
    """PDFs and images: split the pages into invoices (Step 1), then ask Gemini about each (Step 2b)."""
    invoices = []
    for group in split_into_invoices(pages):
        source = f"Pages {group['pages'][0]}-{group['pages'][-1]}" if len(group["pages"]) > 1 \
            else f"Page {group['pages'][0]}"
        invoices.append(invoice_with_ai(group["text"], source, group["lowest_ocr_confidence"]))
    return invoices


def invoices_from_sheets(sheets: list[dict]) -> tuple[list[dict], list[str]]:
    """Excel and CSV: read clear columns directly (Step 2a). Sheets we can't understand go to Gemini."""
    raw_invoices, unmatched_sheets, warnings = invoices_from_spreadsheet(sheets)
    invoices = [finish_invoice(raw, raw["source"], "spreadsheet columns", evidence_problems={}, text=raw["source"])
                for raw in raw_invoices]
    for sheet in unmatched_sheets:
        invoices.append(invoice_with_ai(sheet["text"], f"Sheet '{sheet['name']}'", lowest_ocr_confidence=None))
    return invoices, warnings


def invoice_with_ai(text: str, source: str, lowest_ocr_confidence: float | None) -> dict:
    """Ask Gemini (Step 2b) and check its evidence (Step 3). If Gemini fails, only this invoice fails."""
    try:
        raw = extract_invoice(text)
    except ValueError as error:
        return failed_invoice(source, str(error))
    problems = check_evidence(raw, text)
    return finish_invoice(raw, source, "gemini", problems, lowest_ocr_confidence, text)


def finish_invoice(raw: dict, source: str, method: str, evidence_problems: dict[str, str],
                   lowest_ocr_confidence: float | None = None, text: str = "") -> dict:
    """Clean every value (Task 2), give each field a status (Task 2), check the invoice (Task 3)
    and decide if a person must check it."""
    poor_scan = lowest_ocr_confidence is not None and lowest_ocr_confidence < LOW_CONFIDENCE
    scan_note = f"read from a poorly scanned page (OCR confidence {lowest_ocr_confidence:.0f}%)" if poor_scan else None

    raw_fields = dict(raw["fields"])
    # No currency written next to the amounts? Look for one in the total, e.g. "Total: 1,150.00 EUR".
    if raw_fields["currency"]["value"] is None and raw_fields["total"]["value"] is not None:
        total_text = raw_fields["total"]["evidence"] or raw_fields["total"]["value"]
        if clean_currency(total_text)[0] is not None:
            raw_fields["currency"] = {"value": total_text, "evidence": total_text}

    fields = {}
    for name in INVOICE_FIELDS:
        fields[name] = finish_field(name, raw_fields[name], evidence_problems.get(name), scan_note)

    line_items = [finish_line_item(number, item, evidence_problems)
                  for number, item in enumerate(raw["line_items"], start=1)]

    invoice = {
        "source": source,
        "method": method,
        "ai_model": raw.get("model"),  # which Gemini model read it (None for spreadsheet columns)
        "error": None,
        "fields": fields,
        "line_items": line_items,
        "warnings": raw.get("warnings", []),
    }

    validation_errors = validate_invoice(invoice, text)  # Task 3
    # Line items the AI's evidence or the cleaning (Task 2) was not sure about.
    for number, item in enumerate(line_items, start=1):
        for item_problem in item["problems"]:
            validation_errors.append(problem(f"line item {number}", "uncertain_value",
                                             f"line item {number}: {item_problem}"))
    return set_validation(invoice, validation_errors)


def set_validation(invoice: dict, validation_errors: list[dict]) -> dict:
    """Save the problems in the invoice. Any problem at all means a person has to check it."""
    invoice["validation_errors"] = validation_errors
    invoice["needs_review"] = bool(validation_errors)
    invoice["review_reasons"] = [error["message"] for error in validation_errors]  # the same, as plain sentences
    return invoice


def mark_duplicates(results: list[dict]) -> None:
    """Task 3 Step 4: look for the same invoice twice in one upload, also across different files.
    `results` are the results of extract_invoices_from_file, one per file."""
    invoices = [(f"{result['filename']}, {invoice['source']}", invoice)
                for result in results for invoice in result["invoices"]]
    for (_, invoice), duplicate_problems in zip(invoices, find_duplicates(invoices)):
        if duplicate_problems:
            set_validation(invoice, invoice["validation_errors"] + duplicate_problems)


def finish_field(name: str, raw: dict, evidence_problem: str | None, scan_note: str | None) -> dict:
    """Clean one field and give it a status: "found", "uncertain" or "missing"."""
    value, clean_problem = CLEANERS[name](raw["value"])

    if value is None and clean_problem is None:
        return {"value": None, "status": "missing", "evidence": None, "note": None}

    note = evidence_problem or clean_problem or scan_note  # the most serious reason first
    return {"value": value, "status": "uncertain" if note else "found", "evidence": raw["evidence"], "note": note}


def finish_line_item(number: int, raw: dict, evidence_problems: dict[str, str]) -> dict:
    """Clean one line item and list its problems (from the evidence check and from cleaning)."""
    description = clean_text(raw["description"])[0]
    quantity, quantity_problem = clean_amount(raw["quantity"], money=False)
    unit_price, price_problem = clean_amount(raw["unit_price"])
    amount, amount_problem = clean_amount(raw["amount"])

    problems = []
    for field in ["description", "quantity", "unit_price", "amount"]:
        evidence_problem = evidence_problems.get(f"line item {number} {field}")
        if evidence_problem:
            problems.append(f"{readable(field)}: {evidence_problem}")
    for clean_problem in (quantity_problem, price_problem, amount_problem):
        if clean_problem:
            problems.append(clean_problem)

    return {"description": description, "quantity": quantity, "unit_price": unit_price, "amount": amount,
            "evidence": raw.get("evidence"), "problems": problems}


def failed_invoice(source: str, error: str) -> dict:
    """An invoice the AI could not read: every field is missing and a person has to check it."""
    empty = {"value": None, "status": "missing", "evidence": None, "note": None}
    invoice = {"source": source, "method": "gemini", "ai_model": None, "error": error,
               "fields": {name: dict(empty) for name in INVOICE_FIELDS}, "line_items": [], "warnings": []}
    # field None means the problem is about the whole invoice, not one field
    return set_validation(invoice, [problem(None, "ai_failed", error)])
