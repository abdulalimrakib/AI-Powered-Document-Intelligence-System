import csv
import datetime
import io

import openpyxl
import xlrd


def read_xlsx(data: bytes) -> dict:
    """Read every sheet of a modern Excel file (.xlsx)."""
    try:
        # We open the file twice, both times in read_only mode (row by row, little memory):
        # - values_book gives the saved result of each formula (150), which is what we want.
        # - formulas_book gives the formula itself (=A1+B1), so we can spot formulas whose
        #   result was never saved (files made by some programs, never opened in Excel).
        values_book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        formulas_book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=False)
    except Exception:
        raise ValueError("The Excel file is damaged and can't be opened")

    sheets = {}
    warnings = []
    try:
        for values_sheet, formulas_sheet in zip(values_book.worksheets, formulas_book.worksheets):
            rows = []
            missing_results = 0
            for value_row, formula_row in zip(values_sheet.iter_rows(values_only=True),
                                              formulas_sheet.iter_rows(values_only=True)):
                row = []
                for value, formula in zip(value_row, formula_row):
                    if value is None and isinstance(formula, str) and formula.startswith("="):
                        missing_results += 1  # leave the cell empty: we never calculate or guess values
                    row.append(cell_to_text(value))
                rows.append(row)
            sheets[values_sheet.title] = rows
            if missing_results:
                warnings.append(f"Sheet '{values_sheet.title}': {missing_results} formula cell(s) have no saved "
                                "result. Open the file in Excel, save it, and upload it again.")
    finally:
        values_book.close()
        formulas_book.close()

    result = build_result(sheets)
    result["warnings"] = warnings + result["warnings"]
    return result


def read_xls(data: bytes) -> dict:
    """Read every sheet of an old Excel file (.xls)."""
    try:
        workbook = xlrd.open_workbook(file_contents=data)
    except Exception:
        # Old Word (.doc) files look like .xls from the outside and end up here too.
        raise ValueError("The file is damaged or not a real Excel file")

    sheets = {}
    for sheet in workbook.sheets():
        rows = []
        for row_index in range(sheet.nrows):
            row = []
            for cell in sheet.row(row_index):
                # Old Excel stores dates as numbers (days since 1900), so convert them back.
                if cell.ctype == xlrd.XL_CELL_DATE:
                    row.append(cell_to_text(xlrd.xldate_as_datetime(cell.value, workbook.datemode)))
                else:
                    row.append(cell_to_text(cell.value))
            rows.append(row)
        sheets[sheet.name] = rows
    return build_result(sheets)


def read_csv(data: bytes) -> dict:
    """Read a CSV file. It has one "sheet", which we call "CSV"."""
    text = decode_text(data)

    # CSV files from different countries use different separators (, or ; or tab).
    # The Sniffer looks at the start of the file and guesses which one is used.
    try:
        dialect = csv.Sniffer().sniff(text[:10_000], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel  # the normal comma-separated format

    rows = [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text), dialect)]
    result = build_result({"CSV": rows})

    if all(len(row) == 1 for row in result["sheets"][0]["rows"]):
        result["warnings"].append("Only one column found. Is this really a CSV file?")
    return result


def decode_text(data: bytes) -> str:
    """Turn bytes into text. Try the common encodings, most likely first."""
    for encoding in ("utf-8-sig", "cp1252"):  # utf-8-sig also removes Excel's hidden BOM mark
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1")  # never fails: every byte is a valid latin-1 character


def cell_to_text(value) -> str:
    """Turn one cell into text. We keep everything as text so money stays exact (no floats in JSON)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        # Excel stores 150 as 150.0; show it as "150". Other numbers keep their digits ("1150.5").
        return str(int(value)) if value.is_integer() else str(value)
    if isinstance(value, datetime.datetime):
        # A date without a time becomes "2026-10-15"; otherwise keep the time too.
        return value.date().isoformat() if value.time() == datetime.time(0) else value.isoformat(sep=" ")
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    return str(value).strip()


def build_result(sheets: dict[str, list[list[str]]]) -> dict:
    """Remove empty rows and sheets, and add a plain-text version of each sheet for the AI and search."""
    result_sheets = []
    warnings = []

    for name, rows in sheets.items():
        # Drop empty cells at the end of each row, then drop rows that are completely empty.
        rows = [trim_row(row) for row in rows]
        rows = [row for row in rows if row]
        if not rows:
            warnings.append(f"Sheet '{name}' is empty")
            continue
        text = "\n".join(" | ".join(row) for row in rows)
        result_sheets.append({"name": name, "row_count": len(rows), "rows": rows, "text": text})

    if not result_sheets:
        raise ValueError("The spreadsheet is empty")
    return {"sheets": result_sheets, "warnings": warnings}


def trim_row(row: list[str]) -> list[str]:
    while row and row[-1] == "":
        row.pop()
    return row
