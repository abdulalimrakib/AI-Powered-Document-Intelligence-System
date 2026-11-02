"""Step 4 — Reading Excel and CSV files"""

import io
import zipfile

import pytest

from make_files import make_xlsx, make_xlsx_with_formula, old_excel_file
from read_spreadsheet import read_csv, read_xls, read_xlsx


def test_xlsx_reads_every_sheet():
    """Reads every sheet of an Excel file, with dates, numbers and TRUE/FALSE"""
    result = read_xlsx(make_xlsx())

    invoices, items = result["sheets"]
    assert invoices["name"] == "Invoices"
    assert items["name"] == "Line items"
    # The empty row is gone, the date is ISO, 1150.0 is shown as "1150", TRUE/FALSE as text.
    assert invoices["rows"] == [
        ["Invoice No", "Date", "Supplier", "Total", "Paid"],
        ["INV-001", "2026-10-15", "Acme Trading Ltd", "1150", "TRUE"],
        ["INV-002", "2026-10-16", "Müller GmbH", "99.99", "FALSE"],
    ]
    assert items["text"] == "Invoice No | Description | Qty\nINV-001 | Office chairs | 10"
    assert result["warnings"] == ["Sheet 'Empty sheet' is empty"]


def test_formula_without_saved_result_is_left_empty_and_warned():
    """Leaves a formula with no saved result empty and warns (never guesses a value)"""
    result = read_xlsx(make_xlsx_with_formula())

    assert result["sheets"][0]["rows"][1] == ["1000", "150"]  # Total left empty, never calculated by us
    assert "formula cell(s) have no saved result" in result["warnings"][0]


def test_old_xls_file():
    """Reads an old Excel file (.xls), with its dates and accented letters"""
    result = read_xls(old_excel_file())

    invoices, notes = result["sheets"]
    assert invoices["rows"][1] == ["INV-003", "2026-09-30", "Café Österreich", "250.75"]
    assert notes["rows"] == [["Second sheet"]]


@pytest.mark.parametrize("data, expected_row", [
    pytest.param("\ufeffInvoice No,Total\nINV-001,\"1,150.00\"\n".encode("utf-8"), ["INV-001", "1,150.00"],
                 id="comma + Excel UTF-8 BOM"),
    pytest.param("Invoice No;Supplier\nINV-002;Müller € GmbH\n".encode("cp1252"), ["INV-002", "Müller € GmbH"],
                 id="semicolon + Windows encoding"),
    pytest.param(b"Invoice No\tTotal\nINV-003\t250.75\n", ["INV-003", "250.75"], id="tab separated"),
    pytest.param(b"Invoice No, Total \n\n INV-004 , 10.00 \n\n", ["INV-004", "10.00"],
                 id="extra spaces and blank lines"),
])
def test_csv_variants(data, expected_row):
    """Reads a CSV file correctly"""
    result = read_csv(data)

    assert result["sheets"][0]["rows"][1] == expected_row


def test_one_column_csv_gets_a_warning():
    """Warns when a 'CSV' has only one column"""
    result = read_csv(b"just some text\nmore text\n")

    assert "Only one column" in result["warnings"][0]


def test_empty_csv():
    """Gives a clear message for an empty CSV"""
    with pytest.raises(ValueError, match="empty"):
        read_csv(b"\n\n  \n")


def test_damaged_xlsx():
    """Gives a clear message for a damaged Excel file"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zip_file:
        zip_file.writestr("xl/workbook.xml", "not valid xml <<<")

    with pytest.raises(ValueError, match="damaged"):
        read_xlsx(buffer.getvalue())


def test_fake_xls():
    """Gives a clear message for a fake .xls file"""
    with pytest.raises(ValueError, match="not a real Excel file"):
        read_xls(bytes.fromhex("d0cf11e0a1b11ae1") + b"\x00" * 600)
