"""Step 5 — Putting it together: a status for every field, needs review, and the /extract API"""

import io

import openpyxl
import pymupdf
import pytest
from fastapi.testclient import TestClient

import extract_invoices
from extract_invoices import extract_invoices_from_file, finish_invoice
from main import app

client = TestClient(app)


def field(value, evidence=None):
    return {"value": value, "evidence": value if evidence is None else evidence}


def raw_invoice(**changes) -> dict:
    """A raw answer (as Gemini or the spreadsheet reader give it) for a complete invoice."""
    fields = {
        "invoice_number": field("INV-001", "Invoice No: INV-001"),
        "invoice_date": field("15/10/2026", "Date: 15/10/2026"),
        "supplier_name": field("Acme Trading Ltd"),
        "customer_name": field("Blue Sky Foods"),
        "subtotal": field("1,000.00", "Subtotal: 1,000.00"),
        "tax": field("150.00", "VAT: 150.00"),
        "total": field("1,150.00", "Total: USD 1,150.00"),
        "currency": field("USD", "Total: USD 1,150.00"),
    }
    fields.update(changes)
    return {"fields": fields, "line_items": [], "warnings": []}


def statuses(invoice: dict) -> dict:
    return {name: answer["status"] for name, answer in invoice["fields"].items()}


# ---------- status of each field ----------

def test_complete_invoice_is_found_and_cleaned():
    """A complete invoice: every field is found, values are cleaned, no review needed"""
    invoice = finish_invoice(raw_invoice(), "Page 1", "gemini", evidence_problems={})

    assert set(statuses(invoice).values()) == {"found"}
    assert invoice["fields"]["invoice_date"]["value"] == "2026-10-15"
    assert invoice["fields"]["total"]["value"] == "1150.00"
    assert invoice["fields"]["total"]["evidence"] == "Total: USD 1,150.00"
    assert invoice["needs_review"] is False
    assert invoice["review_reasons"] == []


def test_missing_field_is_null_and_marked_missing():
    """A field that is not in the document is null and marked 'missing'"""
    invoice = finish_invoice(raw_invoice(customer_name=field(None)), "Page 1", "gemini", evidence_problems={})

    assert invoice["fields"]["customer_name"] == {"value": None, "status": "missing", "evidence": None, "note": None}


def test_failed_evidence_check_makes_a_field_uncertain():
    """A value whose evidence was not found in the document is marked 'uncertain' with the reason"""
    problems = {"supplier_name": "the AI's evidence was not found in the document"}

    invoice = finish_invoice(raw_invoice(), "Page 1", "gemini", evidence_problems=problems)

    assert invoice["fields"]["supplier_name"]["status"] == "uncertain"
    assert invoice["fields"]["supplier_name"]["note"] == "the AI's evidence was not found in the document"


def test_unclear_date_is_uncertain_and_not_guessed():
    """An unclear date like 03/04/2026 is marked 'uncertain' and no date is guessed"""
    invoice = finish_invoice(raw_invoice(invoice_date=field("03/04/2026")), "Page 1", "gemini", evidence_problems={})

    date = invoice["fields"]["invoice_date"]
    assert date["status"] == "uncertain"
    assert date["value"] is None
    assert "unclear" in date["note"]
    assert date["evidence"] == "03/04/2026"  # the reviewer can see what was written


def test_values_from_a_poorly_scanned_page_are_uncertain():
    """Values read from a poorly scanned page (low OCR confidence) are marked 'uncertain'"""
    invoice = finish_invoice(raw_invoice(), "Page 1", "gemini", evidence_problems={}, lowest_ocr_confidence=41.0)

    assert set(statuses(invoice).values()) == {"uncertain"}
    assert "poorly scanned page (OCR confidence 41%)" in invoice["fields"]["total"]["note"]


def test_currency_is_taken_from_the_total_when_not_written_separately():
    """When no currency field is found, the currency written next to the total is used"""
    raw = raw_invoice(currency=field(None), total=field("1.150,00", "Total: 1.150,00 EUR"))

    invoice = finish_invoice(raw, "Page 1", "gemini", evidence_problems={})

    assert invoice["fields"]["currency"]["value"] == "EUR"
    assert invoice["fields"]["currency"]["status"] == "found"


# ---------- needs review ----------

@pytest.mark.parametrize("name", [
    pytest.param("invoice_number", id="invoice number"),
    pytest.param("invoice_date", id="invoice date"),
    pytest.param("supplier_name", id="supplier name"),
    pytest.param("total", id="total"),
])
def test_missing_important_field_needs_review(name):
    """An invoice without one of the important fields needs review, and the reason is given"""
    invoice = finish_invoice(raw_invoice(**{name: field(None)}), "Page 1", "gemini", evidence_problems={})

    assert invoice["needs_review"] is True
    assert invoice["review_reasons"] == [f"{name.replace('_', ' ')} is missing"]


def test_missing_customer_alone_does_not_need_review():
    """A missing customer name alone does not send the invoice to review"""
    invoice = finish_invoice(raw_invoice(customer_name=field(None)), "Page 1", "gemini", evidence_problems={})

    assert invoice["needs_review"] is False


def test_line_item_problem_needs_review():
    """A line item with a problem sends the invoice to review"""
    raw = raw_invoice()
    raw["line_items"] = [{"description": "Chairs", "quantity": "10", "unit_price": "100.00",
                          "amount": "1,000.00", "evidence": "Chairs 10 100.00 1,000.00"}]
    problems = {"line item 1 amount": "the value is not in the AI's evidence"}

    invoice = finish_invoice(raw, "Page 1", "gemini", evidence_problems=problems)

    assert invoice["line_items"][0]["amount"] == "1000.00"
    assert invoice["needs_review"] is True
    assert invoice["review_reasons"] == ["line item 1: amount: the value is not in the AI's evidence"]


# ---------- whole files ----------

def make_pdf(page_texts: list[str]) -> bytes:
    pdf = pymupdf.open()
    for text in page_texts:
        pdf.new_page().insert_text((50, 72), text)
    return pdf.tobytes()


@pytest.fixture
def fake_gemini(monkeypatch):
    """A fake Gemini: it answers from the invoice number in the text, and fails for 'INV-999'."""
    asked = []

    def fake_extract_invoice(text):
        asked.append(text)
        if "INV-999" in text:
            raise ValueError("AI extraction failed: the free Gemini limit was reached. Try again later.")
        number = "INV-002" if "INV-002" in text else "INV-001"
        return raw_invoice(invoice_number=field(number, f"Invoice No: {number}"))

    monkeypatch.setattr(extract_invoices, "extract_invoice", fake_extract_invoice)
    monkeypatch.setattr(extract_invoices, "check_evidence", lambda invoice, text: {})
    return asked


def test_pdf_with_two_invoices_gives_two_results(fake_gemini):
    """A PDF with two invoices is split, and each invoice is sent to the AI once"""
    pdf = make_pdf(["Invoice No: INV-001\nTotal: 10.00", "Invoice No: INV-002\nTotal: 20.00"])

    result = extract_invoices_from_file("invoices.pdf", pdf)

    assert result["invoice_count"] == 2
    assert [invoice["source"] for invoice in result["invoices"]] == ["Page 1", "Page 2"]
    assert [invoice["fields"]["invoice_number"]["value"] for invoice in result["invoices"]] == ["INV-001", "INV-002"]
    assert len(fake_gemini) == 2


def test_one_failed_invoice_does_not_stop_the_others(fake_gemini):
    """When the AI fails for one invoice, the other invoices in the file are still extracted"""
    pdf = make_pdf(["Invoice No: INV-999\nTotal: 10.00", "Invoice No: INV-002\nTotal: 20.00"])

    failed, good = extract_invoices_from_file("invoices.pdf", pdf)["invoices"]

    assert failed["error"] == "AI extraction failed: the free Gemini limit was reached. Try again later."
    assert failed["needs_review"] is True
    assert set(statuses(failed).values()) == {"missing"}
    assert good["error"] is None
    assert good["fields"]["invoice_number"]["value"] == "INV-002"


def test_excel_with_clear_columns_needs_no_ai(fake_gemini):
    """An Excel file with clear columns is read without the AI"""
    workbook = openpyxl.Workbook()
    workbook.active.append(["Invoice No", "Date", "Supplier", "Total", "Currency"])
    workbook.active.append(["INV-900", "2026-10-20", "Acme Trading Ltd", 115, "USD"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    invoice = extract_invoices_from_file("invoices.xlsx", buffer.getvalue())["invoices"][0]

    assert invoice["method"] == "spreadsheet columns"
    assert invoice["fields"]["total"]["value"] == "115.00"
    assert invoice["needs_review"] is False
    assert fake_gemini == []  # the AI was not asked


def test_sheet_without_clear_columns_goes_to_the_ai(fake_gemini):
    """A sheet laid out like a printed invoice form is sent to the AI"""
    form = "ACME TRADING LTD\nInvoice No: INV-001\nAmount due;1150\n".encode()

    invoice = extract_invoices_from_file("form.csv", form)["invoices"][0]

    assert invoice["method"] == "gemini"
    assert invoice["source"] == "Sheet 'CSV'"
    assert len(fake_gemini) == 1


def test_broken_file_gives_an_error_and_no_invoices(fake_gemini):
    """A broken file gives a clear error and no invoices"""
    result = extract_invoices_from_file("broken.pdf", b"%PDF-1.7 broken")

    assert result["error"] == "The PDF is damaged and can't be opened"
    assert result["invoices"] == []


def test_api_extracts_many_files(fake_gemini):
    """The /extract API reads many files at once and returns their invoices"""
    files = [
        ("files", ("invoice.pdf", make_pdf(["Invoice No: INV-001\nTotal: 10.00"]), "application/pdf")),
        ("files", ("broken.pdf", b"%PDF-1.7 broken", "application/pdf")),
    ]

    response = client.post("/extract", files=files)

    assert response.status_code == 200
    first, second = response.json()
    assert first["invoice_count"] == 1 and first["error"] is None
    assert second["invoice_count"] == 0 and second["error"] is not None


# ---------- the whole chain with the real Gemini (only run with --real-gemini) ----------

@pytest.mark.real_gemini
def test_real_gemini_whole_chain_on_a_two_page_invoice():
    """Real Gemini: a 2-page invoice PDF gives one invoice with cleaned, checked values"""
    pdf = make_pdf([
        "ACME TRADING LTD\nInvoice No: INV-2026-001   Date: 15/10/2026\nBill to: Blue Sky Foods\n"
        "Office chairs   10   100.00   1,000.00",
        "Invoice No: INV-2026-001 (continued)\nSubtotal: 1,000.00\nVAT (15%): 150.00\nTotal: USD 1,150.00",
    ])

    result = extract_invoices_from_file("invoice.pdf", pdf)

    assert result["invoice_count"] == 1
    invoice = result["invoices"][0]
    assert invoice["error"] is None, invoice["error"]
    assert invoice["source"] == "Pages 1-2"
    values = {name: answer["value"] for name, answer in invoice["fields"].items()}
    assert values == {
        "invoice_number": "INV-2026-001", "invoice_date": "2026-10-15", "supplier_name": "ACME TRADING LTD",
        "customer_name": "Blue Sky Foods", "subtotal": "1000.00", "tax": "150.00", "total": "1150.00",
        "currency": "USD",
    }
    assert invoice["needs_review"] is False


def test_blank_pdf_is_not_sent_to_gemini(fake_gemini):
    """A blank PDF is not sent to Gemini (no free request wasted) and fails with a clear reason"""
    result = extract_invoices_from_file("blank.pdf", make_pdf([""]))  # one page without any text

    assert fake_gemini == []  # Gemini was not asked
    assert result["invoices"][0]["error"] == "No text was found to read (blank or unreadable pages)"
    assert result["warnings"] == ["Page 1: no text found (blank page?)"]
