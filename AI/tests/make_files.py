"""Helpers that create sample files for the tests, so every test shows exactly what it reads."""

import io
import random
from pathlib import Path

import openpyxl
import pymupdf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FILES_FOLDER = Path(__file__).parent / "files"

INVOICE_TEXT = (
    "INVOICE No: INV-2026-001\n"
    "Date: 2026-10-15\n"
    "Supplier: Acme Trading Ltd\n"
    "Customer: Blue Sky Foods\n"
    "Subtotal: 1,000.00\n"
    "Tax (15%): 150.00\n"
    "Total: 1,150.00 USD"
)


def word_accuracy(text: str) -> float:
    """Percentage of the invoice words that appear in the text (100 = every word read correctly)."""
    found = text.split()
    words = INVOICE_TEXT.split()
    return sum(word in found for word in words) / len(words) * 100


# ---------- images ----------

def invoice_image(text_color: int = 0, background: int = 255) -> Image.Image:
    """A clean picture of an invoice, like a good scan."""
    image = Image.new("L", (1700, 1100), background)
    font = ImageFont.load_default(size=44)
    ImageDraw.Draw(image).multiline_text((120, 120), INVOICE_TEXT, fill=text_color, font=font, spacing=28)
    return image


def add_speckles(image: Image.Image, amount: float = 0.06) -> Image.Image:
    """Scanner noise: random black and white dots over the picture."""
    image = image.copy()
    pixels = image.load()
    random.seed(1)  # same dots every run, so the test always behaves the same
    for _ in range(int(image.width * image.height * amount)):
        pixels[random.randrange(image.width), random.randrange(image.height)] = random.choice([0, 255])
    return image


def blur(image: Image.Image) -> Image.Image:
    return image.filter(ImageFilter.GaussianBlur(3))


def to_bytes(image: Image.Image, file_format: str = "PNG", **options) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, file_format, **options)
    return buffer.getvalue()


# ---------- PDFs ----------

def make_pdf(pages: list[str]) -> bytes:
    """A PDF where each page is "digital" (real text), "scanned" (only a picture) or "blank"."""
    pdf = pymupdf.open()
    for kind in pages:
        page = pdf.new_page()
        if kind == "digital":
            page.insert_text((72, 72), INVOICE_TEXT, fontsize=12)
        elif kind == "scanned":
            page.insert_image(page.rect, stream=to_bytes(invoice_image()))
    return pdf.tobytes()


def make_password_pdf() -> bytes:
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), INVOICE_TEXT)
    return pdf.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")


# ---------- spreadsheets ----------

def make_xlsx() -> bytes:
    """An Excel file with 3 sheets: invoices (with a date and an empty row), line items, and an empty sheet."""
    import datetime

    workbook = openpyxl.Workbook()
    invoices = workbook.active
    invoices.title = "Invoices"
    invoices.append(["Invoice No", "Date", "Supplier", "Total", "Paid"])
    invoices.append(["INV-001", datetime.datetime(2026, 10, 15), "Acme Trading Ltd", 1150.0, True])
    invoices.append([])
    invoices.append(["INV-002", datetime.datetime(2026, 10, 16), "Müller GmbH", 99.99, False])

    items = workbook.create_sheet("Line items")
    items.append(["Invoice No", "Description", "Qty"])
    items.append(["INV-001", "Office chairs", 10])

    workbook.create_sheet("Empty sheet")
    return save_workbook(workbook)


def make_xlsx_with_formula() -> bytes:
    """A formula made by a script: Excel never calculated it, so the file has no saved result."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Subtotal", "Tax", "Total"])
    sheet.append([1000, 150, "=A2+B2"])
    return save_workbook(workbook)


def save_workbook(workbook: openpyxl.Workbook) -> bytes:
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def old_excel_file() -> bytes:
    """A real old-format Excel file (.xls), stored in tests/files because no installed library can write .xls."""
    return (FILES_FOLDER / "old_excel.xls").read_bytes()


def sample_invoice(line_items=(), **values) -> dict:
    """A finished invoice (as Task 2 gives it) with clean values, for the Task 3 checks.
    Change any value with a keyword, e.g. sample_invoice(total="1180.00") or sample_invoice(tax=None).
    line_items is a list of (quantity, unit price, amount)."""
    clean = {
        "invoice_number": "INV-001", "invoice_date": "2026-10-15", "supplier_name": "Acme Trading Ltd",
        "customer_name": "Blue Sky Foods", "subtotal": "1000.00", "tax": "150.00", "total": "1150.00",
        "currency": "USD",
    }
    clean.update(values)
    fields = {name: {"value": value, "status": "missing" if value is None else "found", "evidence": value, "note": None}
              for name, value in clean.items()}
    items = [{"description": "Item", "quantity": quantity, "unit_price": unit_price, "amount": amount,
              "evidence": None, "problems": []} for quantity, unit_price, amount in line_items]
    return {"source": "Page 1", "fields": fields, "line_items": items}
