import re

# Column names we recognise for each field. Names are compared in a simple form:
# small letters, only letters/digits/spaces, text in brackets removed ("Total (USD)" -> "total").
COLUMN_NAMES = {
    "invoice_number": ["invoice", "invoice no", "invoice number", "invoice num", "invoice id", "inv no",
                       "inv number", "bill no", "bill number"],
    "invoice_date": ["date", "invoice date", "inv date", "bill date", "issue date"],
    "supplier_name": ["supplier", "supplier name", "vendor", "vendor name", "seller"],
    "customer_name": ["customer", "customer name", "client", "client name", "buyer", "bill to"],
    "subtotal": ["subtotal", "sub total", "net", "net amount", "amount before tax"],
    "tax": ["tax", "vat", "gst", "tax amount", "vat amount"],
    "total": ["total", "total amount", "grand total", "invoice total", "amount due", "gross amount"],
    "currency": ["currency", "currency code"],
    # line item columns
    "description": ["description", "item", "item description", "product", "service", "details"],
    "quantity": ["quantity", "qty", "units"],
    "unit_price": ["unit price", "price", "rate", "unit cost"],
    "amount": ["amount", "line total", "line amount"],
}

INVOICE_FIELDS = ["invoice_number", "invoice_date", "supplier_name", "customer_name",
                  "subtotal", "tax", "total", "currency"]
LINE_ITEM_FIELDS = ["description", "quantity", "unit_price", "amount"]
MONEY_FIELDS = ["subtotal", "tax", "total"]

# The header row must be within the first rows of a sheet (some sheets start with a title).
HEADER_SEARCH_ROWS = 10


def invoices_from_spreadsheet(sheets: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    """Turn spreadsheet sheets (from Task 1) into invoices by matching column names. No AI is used:
    values are copied exactly from the cells.

    Returns (invoices, sheets we could not understand, warnings).
    Sheets we could not understand are sent to Gemini instead."""
    invoices = []
    # invoice number -> invoice, so line items can find their invoice. If a number appears twice,
    # both invoices are kept (Task 3 reports duplicates) and line items go to the first one.
    invoices_by_number = {}
    line_item_sheets = []
    unmatched_sheets = []
    warnings = []

    for sheet in sheets:
        header_index, columns = find_header(sheet["rows"])
        if header_index is None:
            unmatched_sheets.append(sheet)
        elif "description" in columns:  # one row per item, linked to an invoice by its number
            line_item_sheets.append((sheet, header_index, columns))
        else:  # one row per invoice
            for row in sheet["rows"][header_index + 1:]:
                invoice = invoice_from_row(sheet["name"], row, columns)
                if invoice is not None:
                    invoices.append(invoice)
                    invoices_by_number.setdefault(invoice["fields"]["invoice_number"]["value"], invoice)

    for sheet, header_index, columns in line_item_sheets:
        unknown = 0
        for row in sheet["rows"][header_index + 1:]:
            number = cell(row, columns, "invoice_number")
            if number in invoices_by_number:
                line_item = {field: cell(row, columns, field) for field in LINE_ITEM_FIELDS}
                invoices_by_number[number]["line_items"].append(line_item)
            elif number is not None:
                unknown += 1
        if unknown:
            warnings.append(f"Sheet '{sheet['name']}': {unknown} line item(s) belong to an invoice number "
                            "that is not in any invoice sheet")

    return invoices, unmatched_sheets, warnings


def find_header(rows: list[list[str]]) -> tuple[int | None, dict[str, int]]:
    """Find the header row: the first row that has an invoice-number column and either a money
    column (an invoice sheet) or a description column (a line-item sheet).
    Returns (row index, {field: column index}), or (None, {}) if there is no such row."""
    for index, row in enumerate(rows[:HEADER_SEARCH_ROWS]):
        columns = {}
        for column_index, name in enumerate(row):
            field = match_column_name(name)
            if field is not None and field not in columns:  # if a name appears twice, the first one wins
                columns[field] = column_index
        has_money = any(field in columns for field in MONEY_FIELDS)
        if "invoice_number" in columns and (has_money or "description" in columns):
            return index, columns
    return None, {}


def match_column_name(name: str) -> str | None:
    simple = re.sub(r"\(.*?\)", " ", name.lower())  # "Total (USD)" -> "total "
    simple = re.sub(r"[^a-z0-9 ]", " ", simple)  # "Invoice #" -> "invoice "
    simple = " ".join(simple.split())  # remove extra spaces
    for field, names in COLUMN_NAMES.items():
        if simple in names:
            return field
    return None


def invoice_from_row(sheet_name: str, row: list[str], columns: dict[str, int]) -> dict | None:
    """One row becomes one invoice. Rows without a real invoice number (e.g. a "TOTAL" row) are skipped."""
    number = cell(row, columns, "invoice_number")
    if number is None or not any(character.isdigit() for character in number):
        return None

    # Same shape as Gemini's answer will have: each field has a value and the text it came from.
    fields = {}
    for field in INVOICE_FIELDS:
        value = cell(row, columns, field)
        fields[field] = {"value": value, "evidence": value}
    return {"source": f"Sheet '{sheet_name}': {' | '.join(row)}", "fields": fields, "line_items": []}


def cell(row: list[str], columns: dict[str, int], field: str) -> str | None:
    """The text in this field's column, or None if the column or the cell is missing/empty."""
    index = columns.get(field)
    if index is None or index >= len(row) or row[index] == "":
        return None
    return row[index]
