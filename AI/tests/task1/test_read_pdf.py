"""Step 2 — Reading PDF files"""

import pytest

from make_files import INVOICE_TEXT, make_password_pdf, make_pdf, word_accuracy
from read_pdf import read_pdf


def test_digital_page_text_is_read_directly():
    """Reads the text of a normal (digital) PDF exactly"""
    result = read_pdf(make_pdf(["digital"]))

    page = result["pages"][0]
    assert page["method"] == "text"
    assert page["text"] == INVOICE_TEXT
    assert result["warnings"] == []


def test_scanned_page_is_read_with_ocr():
    """Reads a scanned PDF page with OCR, every word correct"""
    page = read_pdf(make_pdf(["scanned"]))["pages"][0]

    assert page["method"] == "ocr"
    assert word_accuracy(page["text"]) == 100
    assert page["ocr_confidence"] > 80


def test_mixed_pdf_uses_ocr_only_where_needed():
    """In a PDF with digital and scanned pages, uses OCR only for the scanned page"""
    result = read_pdf(make_pdf(["digital", "scanned", "digital"]))

    assert result["page_count"] == 3
    assert [page["method"] for page in result["pages"]] == ["text", "ocr", "text"]


def test_blank_page_gives_a_warning():
    """Warns about a blank page"""
    result = read_pdf(make_pdf(["digital", "blank"]))

    assert result["warnings"] == ["Page 2: no text found (blank page?)"]


def test_many_pages_are_all_read():
    """Reads every page of a 300-page PDF"""
    result = read_pdf(make_pdf(["digital"] * 300))

    assert result["page_count"] == 300
    assert len(result["pages"]) == 300


def test_password_protected_pdf():
    """Gives a clear message for a password-protected PDF"""
    with pytest.raises(ValueError, match="password-protected"):
        read_pdf(make_password_pdf())


@pytest.mark.parametrize("broken_file", [
    pytest.param(b"%PDF-1.7 this is not really a pdf", id="garbage after the PDF start"),
    pytest.param(make_pdf(["digital"] * 3)[:400], id="PDF cut off in the middle, like a failed download"),
])
def test_damaged_pdf(broken_file):
    """Gives a clear message for a damaged PDF"""
    with pytest.raises(ValueError, match="damaged"):
        read_pdf(broken_file)
