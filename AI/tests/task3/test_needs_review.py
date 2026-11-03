"""Step 5 — Flag for review, and the checks in the /extract API"""

import io

import openpyxl
from fastapi.testclient import TestClient

from extract_invoices import failed_invoice, finish_invoice
from main import app

client = TestClient(app)


def field(value):
    return {"value": value, "evidence": value}


def raw_invoice(**changes) -> dict:
    """A raw answer (as Gemini or the spreadsheet reader give it)."""
    fields = {
        "invoice_number": field("INV-001"), "invoice_date": field("2026-10-15"),
        "supplier_name": field("Acme Trading Ltd"), "customer_name": field("Blue Sky Foods"),
        "subtotal": field("1,000.00"), "tax": field("150.00"), "total": field("1,150.00"), "currency": field("USD"),
    }
    fields.update({name: field(value) for name, value in changes.items()})
    return {"fields": fields, "line_items": [], "warnings": []}


def excel_file(*rows) -> bytes:
    workbook = openpyxl.Workbook()
    workbook.active.append(["Invoice No", "Date", "Supplier", "Subtotal", "Tax", "Total", "Currency"])
    for row in rows:
        workbook.active.append(list(row))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_correct_invoice_does_not_need_review():
    """A correct invoice has no validation errors and does not need review"""
    invoice = finish_invoice(raw_invoice(), "Page 1", "gemini", evidence_problems={})

    assert invoice["validation_errors"] == []
    assert invoice["needs_review"] is False
    assert invoice["review_reasons"] == []


def test_wrong_total_needs_review_with_the_reason():
    """An invoice whose total doesn't add up needs review, and the reason is given in plain words"""
    invoice = finish_invoice(raw_invoice(total="1,180.00"), "Page 1", "gemini", evidence_problems={})

    assert invoice["needs_review"] is True
    assert [error["rule"] for error in invoice["validation_errors"]] == ["totals_match"]
    assert invoice["review_reasons"] == ["subtotal 1,000.00 + tax 150.00 = 1,150.00, but the total says 1,180.00"]


def test_credit_note_text_is_used():
    """The document text is passed on, so a credit note's negative amounts are accepted"""
    raw = raw_invoice(subtotal="-100.00", tax="-15.00", total="-115.00")

    credit_note = finish_invoice(raw, "Page 1", "gemini", evidence_problems={}, text="CREDIT NOTE No: CN-1")
    normal = finish_invoice(raw, "Page 1", "gemini", evidence_problems={}, text="INVOICE No: INV-001")

    assert credit_note["needs_review"] is False
    assert normal["needs_review"] is True


def test_line_item_doubts_from_task_2_are_validation_errors_too():
    """A line item Task 2 was not sure about is also listed in the validation errors"""
    raw = raw_invoice()
    raw["line_items"] = [{"description": "Chairs", "quantity": "10", "unit_price": "100.00",
                          "amount": "1,000.00", "evidence": "Chairs 10 100.00 1,000.00"}]
    problems = {"line item 1 amount": "the value is not in the AI's evidence"}

    invoice = finish_invoice(raw, "Page 1", "gemini", evidence_problems=problems)

    assert invoice["validation_errors"] == [{
        "field": "line item 1", "rule": "uncertain_value",
        "message": "line item 1: amount: the value is not in the AI's evidence",
    }]


def test_failed_invoice_has_one_clear_error():
    """An invoice the AI could not read has one clear 'ai_failed' error and needs review"""
    invoice = failed_invoice("Page 1", "AI extraction failed: Gemini is busy or unavailable. Try again later.")

    assert invoice["validation_errors"] == [{
        "field": None, "rule": "ai_failed",
        "message": "AI extraction failed: Gemini is busy or unavailable. Try again later.",
    }]
    assert invoice["needs_review"] is True


def test_api_returns_validation_errors_for_each_invoice():
    """The /extract API returns validation errors for each invoice"""
    excel = excel_file(["INV-100", "2026-10-01", "Acme Ltd", 1000, 150, 1150, "USD"],
                       ["INV-101", "2026-10-02", "Acme Ltd", 1000, 150, 1180, "USD"])

    response = client.post("/extract", files=[("files", ("october.xlsx", excel))])

    assert response.status_code == 200
    good, wrong = response.json()[0]["invoices"]
    assert good["needs_review"] is False and good["validation_errors"] == []
    assert wrong["needs_review"] is True
    assert [error["rule"] for error in wrong["validation_errors"]] == ["totals_match"]


def test_api_finds_duplicates_across_files():
    """The /extract API finds the same invoice in two different files of one upload"""
    excel = excel_file(["INV-100", "2026-10-01", "Acme Ltd", 1000, 150, 1150, "USD"])
    csv = b"Invoice No,Date,Supplier,Total,Currency\ninv 100,2026-10-01,ACME LTD.,1150,USD\n"

    response = client.post("/extract", files=[("files", ("october.xlsx", excel)), ("files", ("copy.csv", csv))])

    from_excel = response.json()[0]["invoices"][0]
    from_csv = response.json()[1]["invoices"][0]
    assert from_excel["needs_review"] is True and from_csv["needs_review"] is True
    assert from_excel["validation_errors"][0]["rule"] == "duplicate_invoice"
    assert from_excel["validation_errors"][0]["message"].endswith("as copy.csv, Sheet 'CSV': "
                                                                  "inv 100 | 2026-10-01 | ACME LTD. | 1150 | USD")
    assert "october.xlsx" in from_csv["validation_errors"][0]["message"]


def test_one_file_alone_has_no_duplicate_errors():
    """An invoice that appears only once in the upload gets no duplicate error"""
    excel = excel_file(["INV-100", "2026-10-01", "Acme Ltd", 1000, 150, 1150, "USD"],
                       ["INV-200", "2026-10-03", "Acme Ltd", 100, 15, 115, "USD"])

    invoices = client.post("/extract", files=[("files", ("october.xlsx", excel))]).json()[0]["invoices"]

    assert [invoice["needs_review"] for invoice in invoices] == [False, False]
