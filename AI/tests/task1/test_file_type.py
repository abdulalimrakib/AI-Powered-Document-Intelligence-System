"""Step 1 — Finding the real type of a file"""

import io
import zipfile

from file_type import detect_file_type
from make_files import invoice_image, make_pdf, make_xlsx, old_excel_file, to_bytes


def test_finds_every_supported_type():
    """Recognises PDF, PNG, JPG, TIFF, XLSX, XLS and CSV files from their content"""
    assert detect_file_type(make_pdf(["digital"])) == "pdf"
    assert detect_file_type(to_bytes(invoice_image(), "PNG")) == "png"
    assert detect_file_type(to_bytes(invoice_image(), "JPEG")) == "jpg"
    assert detect_file_type(to_bytes(invoice_image(), "TIFF")) == "tiff"
    assert detect_file_type(make_xlsx()) == "xlsx"
    assert detect_file_type(old_excel_file()) == "xls"
    assert detect_file_type(b"Invoice No,Total\nINV-001,150.00\n") == "csv"


def test_word_file_is_not_excel():
    """Does not mistake a Word file (.docx) for an Excel file"""
    # .docx is a zip file too, but it has no "xl/workbook.xml" inside
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zip_file:
        zip_file.writestr("word/document.xml", "<document/>")
    assert detect_file_type(buffer.getvalue()) is None


def test_rejects_empty_broken_and_unknown_files():
    """Rejects empty files, broken files and programs (.exe)"""
    assert detect_file_type(b"") is None
    assert detect_file_type(b"PK\x03\x04 broken zip") is None
    assert detect_file_type(b"MZ\x90\x00 program file") is None  # a Windows .exe
