"""Step 2a — Reading invoices from spreadsheet columns (no AI)"""

import io

import openpyxl
import pytest

from read_spreadsheet import read_csv, read_xlsx
from spreadsheet_invoices import invoices_from_spreadsheet, match_column_name


def sheet(name: str, rows: list[list[str]]) -> dict:
    """A sheet as Task 1 returns it."""
    return {"name": name, "row_count": len(rows), "rows": rows, "text": ""}


def value(invoice: dict, field: str):
    return invoice["fields"][field]["value"]


@pytest.mark.parametrize("column_name, field", [
    pytest.param("Invoice No", "invoice_number", id="Invoice No"),
    pytest.param("INVOICE #", "invoice_number", id="INVOICE #"),
    pytest.param("Bill Number", "invoice_number", id="Bill Number"),
    pytest.param("  Grand   Total ", "total", id="extra spaces"),
    pytest.param("Total (USD)", "total", id="Total (USD)"),
    pytest.param("VAT", "tax", id="VAT"),
    pytest.param("Vendor Name", "supplier_name", id="Vendor Name"),
    pytest.param("Qty", "quantity", id="Qty"),
])
def test_recognises_common_column_names(column_name, field):
    """Recognises the common names of a column"""
    assert match_column_name(column_name) == field


def test_unknown_column_name():
    """Does not guess the meaning of an unknown column"""
    assert match_column_name("Warehouse shelf") is None


def test_each_row_becomes_an_invoice_with_exact_values():
    """Each row becomes one invoice, with values copied exactly from the cells"""
    rows = [
        ["Invoice No", "Date", "Supplier", "Customer", "Subtotal", "Tax", "Total", "Currency"],
        ["INV-001", "2026-10-15", "Acme Trading Ltd", "Blue Sky Foods", "1,000.00", "150.00", "1,150.00", "USD"],
        ["INV-002", "2026-10-16", "Müller GmbH", "Blue Sky Foods", "99.99", "0", "99.99", "EUR"],
    ]

    invoices, unmatched, warnings = invoices_from_spreadsheet([sheet("Invoices", rows)])

    assert len(invoices) == 2
    first = invoices[0]
    assert value(first, "invoice_number") == "INV-001"
    assert value(first, "supplier_name") == "Acme Trading Ltd"
    assert value(first, "total") == "1,150.00"  # exactly as written; cleaning comes in Step 4
    assert first["fields"]["total"]["evidence"] == "1,150.00"
    assert first["source"] == "Sheet 'Invoices': " + " | ".join(rows[1])
    assert unmatched == [] and warnings == []


def test_missing_column_or_empty_cell_gives_none():
    """A missing column or an empty cell gives no value (null), never a guess"""
    rows = [
        ["Invoice No", "Supplier", "Total"],  # no date, customer, subtotal, tax or currency column
        ["INV-001", "", "50.00"],  # supplier cell is empty
    ]

    invoice = invoices_from_spreadsheet([sheet("Invoices", rows)])[0][0]

    assert value(invoice, "supplier_name") is None
    assert value(invoice, "invoice_date") is None
    assert value(invoice, "currency") is None
    assert value(invoice, "total") == "50.00"


def test_title_rows_above_the_header_are_skipped():
    """Finds the header row even when the sheet starts with a title"""
    rows = [
        ["Monthly invoice report"],
        ["Exported on 2026-11-01"],
        ["Invoice No", "Total"],
        ["INV-001", "10.00"],
    ]

    invoices = invoices_from_spreadsheet([sheet("Report", rows)])[0]

    assert [value(invoice, "invoice_number") for invoice in invoices] == ["INV-001"]


def test_summary_row_is_not_an_invoice():
    """A summary row like 'TOTAL' at the bottom is not treated as an invoice"""
    rows = [["Invoice No", "Total"], ["INV-001", "10.00"], ["INV-002", "20.00"], ["TOTAL", "30.00"]]

    invoices = invoices_from_spreadsheet([sheet("Invoices", rows)])[0]

    assert [value(invoice, "invoice_number") for invoice in invoices] == ["INV-001", "INV-002"]


def test_duplicate_invoice_numbers_are_both_kept():
    """Two rows with the same invoice number are both kept (Task 3 reports duplicates)"""
    rows = [["Invoice No", "Total"], ["INV-001", "10.00"], ["INV-001", "10.00"]]

    invoices = invoices_from_spreadsheet([sheet("Invoices", rows)])[0]

    assert len(invoices) == 2


def test_line_items_on_another_sheet_are_joined_to_their_invoice():
    """Line items on a second sheet are joined to their invoice by the invoice number"""
    invoice_sheet = sheet("Invoices", [["Invoice No", "Total"], ["INV-001", "1150"], ["INV-002", "99.99"]])
    item_sheet = sheet("Line items", [
        ["Invoice No", "Description", "Qty", "Unit price", "Amount"],
        ["INV-001", "Office chairs", "10", "100", "1000"],
        ["INV-001", "Delivery", "1", "150", "150"],
        ["INV-002", "Coffee beans", "3", "33.33", "99.99"],
    ])

    invoices = invoices_from_spreadsheet([invoice_sheet, item_sheet])[0]

    assert invoices[0]["line_items"] == [
        {"description": "Office chairs", "quantity": "10", "unit_price": "100", "amount": "1000"},
        {"description": "Delivery", "quantity": "1", "unit_price": "150", "amount": "150"},
    ]
    assert len(invoices[1]["line_items"]) == 1


def test_line_items_for_an_unknown_invoice_give_a_warning():
    """Warns about line items whose invoice number is not in any invoice sheet"""
    invoice_sheet = sheet("Invoices", [["Invoice No", "Total"], ["INV-001", "10"]])
    item_sheet = sheet("Items", [["Invoice No", "Description"], ["INV-999", "Lost item"]])

    warnings = invoices_from_spreadsheet([invoice_sheet, item_sheet])[2]

    assert warnings == ["Sheet 'Items': 1 line item(s) belong to an invoice number that is not in any invoice sheet"]


def test_sheet_without_matching_columns_is_left_for_the_ai():
    """A sheet whose columns are not recognised is passed on to the AI (Gemini) instead"""
    form = sheet("Invoice form", [["ACME TRADING LTD"], ["Bill to:", "Blue Sky Foods"], ["Amount due", "1150"]])

    invoices, unmatched, warnings = invoices_from_spreadsheet([form])

    assert invoices == []
    assert unmatched == [form]


def test_real_excel_file_with_two_sheets():
    """A real Excel file with an invoice sheet and a line-item sheet (read with Task 1)"""
    workbook = openpyxl.Workbook()
    invoice_sheet = workbook.active
    invoice_sheet.title = "Invoices"
    invoice_sheet.append(["Invoice #", "Invoice Date", "Vendor", "Total (USD)"])
    invoice_sheet.append(["INV-001", "2026-10-15", "Acme Trading Ltd", 1150])
    items = workbook.create_sheet("Items")
    items.append(["Invoice #", "Item", "Qty", "Price"])
    items.append(["INV-001", "Office chairs", 10, 115])
    buffer = io.BytesIO()
    workbook.save(buffer)

    invoices = invoices_from_spreadsheet(read_xlsx(buffer.getvalue())["sheets"])[0]

    assert len(invoices) == 1
    assert value(invoices[0], "supplier_name") == "Acme Trading Ltd"
    assert value(invoices[0], "total") == "1150"
    assert invoices[0]["line_items"][0]["description"] == "Office chairs"


def test_real_csv_file():
    """A real CSV file with a semicolon separator (read with Task 1)"""
    csv_file = "Invoice Number;Supplier;Total\nINV-7;Müller GmbH;99,99\n".encode("cp1252")

    invoices = invoices_from_spreadsheet(read_csv(csv_file)["sheets"])[0]

    assert value(invoices[0], "invoice_number") == "INV-7"
    assert value(invoices[0], "total") == "99,99"
