"""Step 1 — Splitting a document into separate invoices"""

import pymupdf
import pytest

from read_pdf import read_pdf
from split_invoices import find_invoice_number, split_into_invoices


def page(number: int, text: str, ocr_confidence: float | None = None) -> dict:
    """A page as Task 1 returns it."""
    return {"page_number": number, "text": text, "method": "text", "ocr_confidence": ocr_confidence}


@pytest.mark.parametrize("text, expected", [
    pytest.param("INVOICE No: INV-2026-001", "INV-2026-001", id="Invoice No:"),
    pytest.param("Invoice #: 1234", "1234", id="Invoice #:"),
    pytest.param("Invoice #A-77", "A-77", id="Invoice # without space"),
    pytest.param("Invoice Number 55/B", "55/B", id="Invoice Number"),
    pytest.param("TAX INVOICE NO. 7.", "7", id="Tax Invoice No."),
    pytest.param("Inv. No: inv-88", "INV-88", id="Inv. No, small letters"),
    pytest.param("Invoice No:\nINV-9", "INV-9", id="number on the next line"),
])
def test_finds_the_invoice_number(text, expected):
    """Finds the invoice number in the different ways invoices write it"""
    assert find_invoice_number(text) == expected


@pytest.mark.parametrize("text", [
    pytest.param("Invoice Date: 2026-10-15", id="invoice date is not a number label"),
    pytest.param("Please quote the invoice number when paying", id="label without a number"),
    pytest.param("Thank you for your business", id="no label at all"),
])
def test_ignores_text_that_is_not_an_invoice_number(text):
    """Does not mistake other text for an invoice number"""
    assert find_invoice_number(text) is None


def test_each_new_invoice_number_starts_a_new_invoice():
    """Three pages with three different invoice numbers become three invoices"""
    pages = [page(1, "Invoice No: A-1"), page(2, "Invoice No: A-2"), page(3, "Invoice No: A-3")]

    invoices = split_into_invoices(pages)

    assert [invoice["pages"] for invoice in invoices] == [[1], [2], [3]]


def test_pages_without_a_number_belong_to_the_invoice_before():
    """A page without an invoice number (e.g. more line items) stays with the invoice before it"""
    pages = [page(1, "Invoice No: A-1"), page(2, "more items, page 2 of 2"), page(3, "Invoice No: A-2")]

    invoices = split_into_invoices(pages)

    assert [invoice["pages"] for invoice in invoices] == [[1, 2], [3]]


def test_heading_repeated_on_every_page_is_one_invoice():
    """The same invoice number on every page means one invoice, not many"""
    pages = [page(1, "Invoice No: A-1 page 1"), page(2, "Invoice No: A-1 (continued)"), page(3, "Invoice No: A-1")]

    invoices = split_into_invoices(pages)

    assert [invoice["pages"] for invoice in invoices] == [[1, 2, 3]]


def test_cover_page_joins_the_first_invoice():
    """A cover page before the first invoice number joins the first invoice"""
    pages = [page(1, "Cover letter: please find our invoices attached"), page(2, "Invoice No: A-1"),
             page(3, "Invoice No: A-2")]

    invoices = split_into_invoices(pages)

    assert [invoice["pages"] for invoice in invoices] == [[1, 2], [3]]


def test_document_without_any_invoice_number_is_one_invoice():
    """A document without any invoice number is treated as one invoice"""
    pages = [page(1, "Receipt from the corner shop"), page(2, "Total 12.50")]

    invoices = split_into_invoices(pages)

    assert [invoice["pages"] for invoice in invoices] == [[1, 2]]


def test_invoice_text_has_page_markers_and_lowest_ocr_confidence():
    """Joins the invoice's pages with page markers and keeps the worst OCR confidence"""
    pages = [page(1, "Invoice No: A-1", ocr_confidence=91.0), page(2, "Total: 50.00", ocr_confidence=55.5)]

    invoice = split_into_invoices(pages)[0]

    assert invoice["text"] == "--- Page 1 ---\nInvoice No: A-1\n\n--- Page 2 ---\nTotal: 50.00"
    assert invoice["lowest_ocr_confidence"] == 55.5


def test_digital_pages_have_no_ocr_confidence():
    """Pages read without OCR have no OCR confidence to report"""
    invoice = split_into_invoices([page(1, "Invoice No: A-1")])[0]

    assert invoice["lowest_ocr_confidence"] is None


def test_real_pdf_with_three_invoices_on_five_pages():
    """A real 5-page PDF holding 3 invoices is split correctly (read with Task 1)"""
    page_texts = [
        "INVOICE No: INV-001\nSupplier: Acme Trading Ltd",
        "Invoice No: INV-001 (continued)\nItem 31: Desk lamp",
        "INVOICE No: INV-002\nSupplier: Blue Sky Foods",
        "INVOICE No: INV-003\nSupplier: Müller GmbH",
        "Total: 99.99 EUR\nThank you",
    ]
    pdf = pymupdf.open()
    for text in page_texts:
        pdf.new_page().insert_text((72, 72), text)

    invoices = split_into_invoices(read_pdf(pdf.tobytes())["pages"])

    assert [invoice["pages"] for invoice in invoices] == [[1, 2], [3], [4, 5]]


def test_a_thousand_pages_is_fast():
    """Splits a 1000-page document (500 two-page invoices) correctly"""
    pages = []
    for number in range(1, 1001):
        invoice_number = (number + 1) // 2  # pages 1-2 -> invoice 1, pages 3-4 -> invoice 2, ...
        text = f"Invoice No: INV-{invoice_number}" if number % 2 == 1 else "continued..."
        pages.append(page(number, text))

    invoices = split_into_invoices(pages)

    assert len(invoices) == 500
    assert invoices[-1]["pages"] == [999, 1000]
