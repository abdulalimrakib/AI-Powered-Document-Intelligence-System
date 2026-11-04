"""Task 7, Step 2: make the labeled dataset for the evaluation.

It makes made-up invoice files (PDF, scanned PDF, images, Excel, CSV, and broken files) AND their answer sheet
(labels.json) from ONE description per invoice, so the files and the answers can never disagree.
The invoices are made up (no real people or companies), so they are safe to send to Gemini.

    uv run python evaluation/make_dataset.py

Writes evaluation/dataset/<files> and evaluation/labels.json. Running it again gives files with the same content
(but PDF and Excel files get new internal dates and IDs, so their bytes differ). To change only the answer sheet
and keep the files of an earlier run exactly as they were, use:

    uv run python evaluation/make_dataset.py --labels-only

What a label means: the value as it is WRITTEN on the invoice, in the system's clean form (e.g. "15 October 2026"
-> "2026-10-15", "1.234,56" -> "1234.56", "€" -> "EUR"). An invoice with a wrong total on purpose is labeled with the
wrong total (that is what is written; reading it correctly is the job), and with the problem the checks should find.
"""

import datetime
import io
import json
import random
import sys
from decimal import Decimal
from pathlib import Path

import openpyxl
import pymupdf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FOLDER = Path(__file__).parent
DATASET = FOLDER / "dataset"
MONO_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"  # falls back to Pillow's own font if missing
CENT = Decimal("0.01")


# ---------- one description per invoice ----------

def invoice(number, date_text, date, supplier, customer, currency_text, currency, lines, tax_rate="15",
            style="us", wording=0, wrong=None, expected_problems=(), title="INVOICE"):
    """Describe one invoice. `lines` is [(description, quantity, unit price)], as written.
    `wrong` writes a wrong value on purpose, e.g. {"total": "1180.00"} or {"line 2 amount": "60.00"}.
    `expected_problems` are the rule names the checks should find (see AI/validate_invoice.py)."""
    items = []
    for description, quantity, unit_price in lines:
        amount = (Decimal(quantity) * Decimal(unit_price)).quantize(CENT)
        items.append({"description": description, "quantity": quantity, "unit_price": Decimal(unit_price).quantize(CENT), "amount": amount})
    wrong = wrong or {}
    for key, value in wrong.items():  # a wrong line amount, e.g. "line 2 amount"
        if key.startswith("line "):
            items[int(key.split()[1]) - 1]["amount"] = Decimal(value)
    subtotal = sum((item["amount"] for item in items), Decimal("0.00"))
    tax = (subtotal * Decimal(tax_rate) / 100).quantize(CENT) if tax_rate is not None else None
    total = Decimal(wrong["total"]) if "total" in wrong else subtotal + (tax or 0)
    return {
        "number": number, "date_text": date_text, "date": date, "supplier": supplier, "customer": customer,
        "currency_text": currency_text, "currency": currency, "items": items, "subtotal": subtotal, "tax": tax,
        "tax_rate": tax_rate, "total": total, "style": style, "wording": wording, "title": title,
        "expected_problems": sorted(expected_problems),
    }


def money(value: Decimal, style: str) -> str:
    """1234.5 -> "1,234.50" (us), "1.234,50" (eu) or "1234.50" (plain)"""
    text = f"{value:,.2f}"
    if style == "eu":
        text = text.replace(",", "_").replace(".", ",").replace("_", ".")
    if style == "plain":
        text = f"{value:.2f}"
    return text


# Different invoices use different words for the same thing
WORDINGS = [
    {"number": "Invoice No:", "date": "Date:", "customer": "Bill to:", "tax": "VAT ({rate}%):", "total": "Total:"},
    {"number": "Invoice Number:", "date": "Invoice date:", "customer": "Customer:", "tax": "Tax {rate}%:", "total": "Amount due:"},
    {"number": "Tax Invoice No.", "date": "Dated:", "customer": "Sold to:", "tax": "GST {rate}%:", "total": "Grand total:"},
]


def invoice_text(inv: dict, page: str = "all") -> str:
    """The invoice as text lines (monospace layout). page: "all", "first" (top + lines) or "second" (totals)."""
    words = WORDINGS[inv["wording"]]
    m = lambda value: money(value, inv["style"])  # noqa: E731
    top = [inv["supplier"], "12 Example Road, Sample City", "", inv["title"], f"{words['number']} {inv['number']}",
           f"{words['date']} {inv['date_text']}"]
    if inv["customer"]:
        top.append(f"{words['customer']} {inv['customer']}")
    table = ["", f"{'Description':<30}{'Qty':>6}{'Unit price':>14}{'Amount':>14}"]
    table += [f"{item['description']:<30}{item['quantity']:>6}{m(item['unit_price']):>14}{m(item['amount']):>14}" for item in inv["items"]]
    totals = ["", f"Subtotal: {m(inv['subtotal'])}"]
    if inv["tax"] is not None:
        totals.append(f"{words['tax'].format(rate=inv['tax_rate'])} {m(inv['tax'])}")
    totals += [f"{words['total']} {inv['currency_text']} {m(inv['total'])}", "", "Thank you for your business."]
    if page == "first":
        return "\n".join(top + table + ["", "(continued on the next page)"])
    if page == "second":
        return "\n".join([inv["supplier"], f"{words['number']} {inv['number']} (page 2)"] + totals)
    return "\n".join(top + table + totals)


def label(inv: dict, supplier_written=True) -> dict:
    """The answer sheet for one invoice: the clean values the system should give."""
    text = lambda value: None if value is None else f"{value:.2f}"  # noqa: E731
    return {
        "fields": {
            "invoice_number": inv["number"], "invoice_date": inv["date"],
            "supplier_name": inv["supplier"] if supplier_written else None, "customer_name": inv["customer"],
            "subtotal": text(inv["subtotal"]), "tax": text(inv["tax"]), "total": text(inv["total"]), "currency": inv["currency"],
        },
        "line_items": [{"description": item["description"], "quantity": item["quantity"],
                        "unit_price": text(item["unit_price"]), "amount": text(item["amount"])} for item in inv["items"]],
        "expected_problems": inv["expected_problems"],
    }


# ---------- making the files ----------

def pdf_with_text(pages: list[str]) -> bytes:
    """A normal (digital) PDF: real text in a monospace font, one string per page"""
    pdf = pymupdf.open()
    for text in pages:
        pdf.new_page().insert_text((50, 60), text, fontname="cour", fontsize=10)
    return pdf.tobytes()


def picture(text: str, quality: str = "clean") -> Image.Image:
    """A picture of the invoice, like a scan or a photo. quality: clean, scan (dots, tilt), photo, small"""
    try:
        font = ImageFont.truetype(MONO_FONT, 30)
    except OSError:
        font = ImageFont.load_default(size=30)
    background = 228 if quality == "photo" else 255
    image = Image.new("L", (1700, 2200), background)
    ImageDraw.Draw(image).multiline_text((110, 120), text, fill=20, font=font, spacing=14)
    random.seed(7)  # the same "dirt" every run
    if quality == "scan":
        pixels = image.load()
        for _ in range(int(image.width * image.height * 0.01)):
            pixels[random.randrange(image.width), random.randrange(image.height)] = random.choice([0, 255])
        image = image.rotate(1.5, fillcolor=255, expand=False).filter(ImageFilter.GaussianBlur(0.8))
    if quality == "photo":
        image = image.rotate(-2.5, fillcolor=background, expand=False).filter(ImageFilter.GaussianBlur(1.2))
    if quality == "small":
        image = image.resize((image.width * 45 // 100, image.height * 45 // 100))
    return image


def image_bytes(image: Image.Image, file_format: str, **options) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, file_format, **options)
    return buffer.getvalue()


def scanned_pdf(text: str, quality: str) -> bytes:
    """A PDF that is only a picture of the invoice (like a scanner makes): needs OCR"""
    pdf = pymupdf.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=image_bytes(picture(text, quality), "PNG"))
    return pdf.tobytes(deflate=True)  # compressed, like a real scanner's PDF


def workbook_bytes(workbook: openpyxl.Workbook) -> bytes:
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ---------- the invoices ----------

def make_documents() -> list[dict]:
    """Every document of the dataset: its file, what kind it is, what should happen, and its invoices."""
    documents = []

    def add(file, kind, data, invoices=(), expected="done", note="", supplier_written=True):
        documents.append({"file": file, "kind": kind, "data": data, "expected": expected, "note": note,
                          "invoices": [label(inv, supplier_written) for inv in invoices]})

    # Digital PDFs: one invoice each, in different styles
    clean = invoice("INV-2026-101", "2026-10-01", "2026-10-01", "Acme Office Supplies Ltd", "Blue Sky Foods", "USD", "USD",
                    [("Office chairs", "10", "100.00"), ("Desk lamps", "4", "25.00")],
                    expected_problems=["duplicate_invoice"])  # d13 is a copy of it, so both are duplicates
    add("d01_clean_usd.pdf", "digital PDF", pdf_with_text([invoice_text(clean)]), [clean],
        note="a clean invoice; d13 is a copy of it, so it should be marked as a duplicate")
    inv = invoice("INV-2026-102", "15 October 2026", "2026-10-15", "Northwind Traders GmbH", "Blue Sky Foods", "EUR", "EUR",
                  [("Printer paper A4, box", "20", "18.50"), ("Toner cartridge", "3", "64.90")], tax_rate="19", wording=1)
    add("d02_eur_written_date.pdf", "digital PDF", pdf_with_text([invoice_text(inv)]), [inv], note="EUR, date written in words")
    inv = invoice("BD-5531", "21/10/2026", "2026-10-21", "Dhaka Digital Services", "Blue Sky Foods", "BDT", "BDT",
                  [("Website maintenance, October", "1", "45000.00"), ("Domain renewal", "2", "1500.00")], wording=2)
    add("d03_bdt.pdf", "digital PDF", pdf_with_text([invoice_text(inv)]), [inv], note="BDT, day/month/year date")
    # The PDF's built-in Courier font can't draw "€": the file shows "Total: · 3.399,24". So no currency is written,
    # and the right answer is "no currency" (corrected after the first real run, which showed it).
    inv = invoice("2026/0457", "22.10.2026", "2026-10-22", "Müller & Söhne KG", "Blue Sky Foods", "€", None,
                  [("Industrial shelving unit", "6", "412.75"), ("Assembly service", "1", "380.00")], tax_rate="19", style="eu")
    add("d04_european_numbers.pdf", "digital PDF", pdf_with_text([invoice_text(inv)]), [inv],
        note="European numbers (1.234,56), accented letters; the € sign could not be drawn by the PDF font, so no currency is written")
    inv = invoice("UK-88213", "Oct 20, 2026", "2026-10-20", "Brightside Cleaning Co", "Blue Sky Foods", "£", "GBP",
                  [("Office cleaning, weekly", "4", "180.00"), ("Window washing", "1", "95.00")], tax_rate="20", wording=1)
    add("d05_gbp.pdf", "digital PDF", pdf_with_text([invoice_text(inv)]), [inv], note="£ sign, US-style written date")
    inv = invoice("INV-2026-106", "2026-10-24", "2026-10-24", "Cloudline Software Inc", None, "USD", "USD",
                  [("Accounting software, annual licence", "1", "1200.00")])
    add("d06_no_customer.pdf", "digital PDF", pdf_with_text([invoice_text(inv)]), [inv],
        note="no customer written: the system must leave it empty, not invent one")
    inv = invoice("R-7710", "2026-10-25", "2026-10-25", "Corner Coffee Roasters", "Blue Sky Foods", "$", "USD",
                  [("Arabica coffee beans 1kg", "5", "16.00"), ("Oat milk 1L", "12", "2.25")], tax_rate=None)
    # The currency is marked "uncertain" (a "$" alone could be another dollar), but by design (Task 3) only the important
    # fields (number, date, supplier, total) send an invoice to review. So no problem is expected (corrected after the
    # first real run).
    add("d07_no_tax_dollar_sign.pdf", "digital PDF", pdf_with_text([invoice_text(inv)]), [inv],
        note="no tax line, and only a '$' sign (USD; the currency field is marked uncertain, but that alone needs no review)")
    inv = invoice("INV-2026-108", "2026-10-26", "2026-10-26", "FastNet Broadband", "Blue Sky Foods", "USD", "USD",
                  [("Broadband internet, October", "1", "1000.00")], wrong={"total": "1180.00"},
                  expected_problems=["totals_match"])
    add("d08_wrong_total.pdf", "digital PDF", pdf_with_text([invoice_text(inv)]), [inv],
        note="the total is wrong on purpose: subtotal + tax = 1150.00, but 1180.00 is written")
    inv = invoice("INV-2026-109", "2026-10-27", "2026-10-27", "Lumen Lighting Ltd", "Blue Sky Foods", "USD", "USD",
                  [("LED panel light", "8", "45.00"), ("Desk lamp", "2", "25.00")], wrong={"line 2 amount": "60.00"},
                  wording=2, expected_problems=["line_math"])
    add("d09_wrong_line.pdf", "digital PDF", pdf_with_text([invoice_text(inv)]), [inv],
        note="line 2 is wrong on purpose: 2 x 25.00 = 50.00, but 60.00 is written")
    inv = invoice("CN-0042", "2026-10-28", "2026-10-28", "Acme Office Supplies Ltd", "Blue Sky Foods", "USD", "USD",
                  [("Return: office chair", "1", "-100.00")], title="CREDIT NOTE")
    add("d10_credit_note.pdf", "digital PDF", pdf_with_text([invoice_text(inv)]), [inv],
        note="a credit note: negative amounts are correct here")

    # One PDF with three invoices, and one invoice over two pages
    three = [
        invoice("INV-2026-111", "2026-10-02", "2026-10-02", "Greenleaf Catering", "Blue Sky Foods", "USD", "USD", [("Lunch for 12 people", "12", "14.50")]),
        invoice("INV-2026-112", "2026-10-09", "2026-10-09", "Greenleaf Catering", "Blue Sky Foods", "USD", "USD", [("Lunch for 15 people", "15", "14.50")]),
        invoice("INV-2026-113", "2026-10-16", "2026-10-16", "Greenleaf Catering", "Blue Sky Foods", "USD", "USD", [("Lunch for 9 people", "9", "14.50"), ("Coffee service", "1", "35.00")]),
    ]
    add("d11_three_invoices.pdf", "digital PDF", pdf_with_text([invoice_text(inv) for inv in three]), three,
        note="three invoices in one PDF, one per page: must become three invoices")
    inv = invoice("INV-2026-114", "2026-10-29", "2026-10-29", "Atlas Furniture Co", "Blue Sky Foods", "USD", "USD",
                  [("Meeting table", "1", "640.00"), ("Meeting chairs", "8", "95.00"), ("Whiteboard", "2", "120.00"),
                   ("Delivery and assembly", "1", "150.00")], wording=1)
    add("d12_two_pages.pdf", "digital PDF", pdf_with_text([invoice_text(inv, "first"), invoice_text(inv, "second")]), [inv],
        note="one invoice over two pages (the number is repeated on page 2): must stay one invoice")
    add("d13_resent_copy.pdf", "digital PDF", pdf_with_text([invoice_text(clean)]), [clean],
        note="the same invoice as d01, sent again: should be marked as a duplicate")
    inv = invoice("INV-2036-115", "2036-10-30", "2036-10-30", "Typo Printing Ltd", "Blue Sky Foods", "USD", "USD",
                  [("Business cards, 500", "2", "45.00")], expected_problems=["future_date"])
    add("d14_future_date.pdf", "digital PDF", pdf_with_text([invoice_text(inv)]), [inv],
        note="dated 2036 by mistake: should be flagged as a date in the future")

    # Scanned PDFs and images: read with OCR first
    inv = invoice("SC-3001", "2026-10-05", "2026-10-05", "Harbor Logistics Ltd", "Blue Sky Foods", "USD", "USD",
                  [("Freight Chittagong to Dhaka", "1", "850.00"), ("Insurance", "1", "42.50")])
    add("s01_scanned_clean.pdf", "scanned PDF", scanned_pdf(invoice_text(inv), "clean"), [inv], note="a clean scan")
    inv = invoice("SC-3002", "02 Nov 2026", "2026-11-02", "Pioneer Security Services", "Blue Sky Foods", "BDT", "BDT",
                  [("Security guard, night shift", "30", "1200.00")], wording=2)
    add("s02_scanned_dirty.pdf", "scanned PDF", scanned_pdf(invoice_text(inv), "scan"), [inv],
        note="a dirty scan: dots, slightly tilted and blurred")
    inv = invoice("IMG-4001", "2026-10-11", "2026-10-11", "Swift Couriers", "Blue Sky Foods", "USD", "USD",
                  [("Same-day delivery", "6", "12.00"), ("Packaging", "6", "2.50")])
    add("i01_clean.png", "image", image_bytes(picture(invoice_text(inv)), "PNG"), [inv], note="a clean PNG")
    inv = invoice("IMG-4002", "2026-10-12", "2026-10-12", "Metro Taxi Ltd", "Blue Sky Foods", "USD", "USD",
                  [("Airport transfer", "2", "35.00"), ("City rides, October", "14", "8.75")], wording=1)
    add("i02_phone_photo.jpg", "image", image_bytes(picture(invoice_text(inv), "photo"), "JPEG", quality=60), [inv],
        note="like a phone photo: grey, tilted, a little blurred, strong JPEG compression")
    inv = invoice("IMG-4003", "2026-10-13", "2026-10-13", "Sunrise Stationers", "Blue Sky Foods", "USD", "USD",
                  [("Notebooks A5", "50", "1.80"), ("Ballpoint pens, box", "10", "4.20")])
    add("i03_scan.tiff", "image", image_bytes(picture(invoice_text(inv), "scan"), "TIFF", compression="tiff_deflate"), [inv], note="a TIFF scan")
    inv = invoice("IMG-4004", "2026-10-14", "2026-10-14", "Vista Travel Agency", "Blue Sky Foods", "USD", "USD",
                  [("Flight Dhaka to Singapore", "1", "420.00"), ("Hotel, 2 nights", "2", "110.00")])
    add("i04_low_resolution.png", "image", image_bytes(picture(invoice_text(inv), "small"), "PNG"), [inv],
        note="a low-resolution picture (45% of the normal size)")

    # Spreadsheets: read by their columns, without the AI
    sheet_invoices = [
        invoice("XL-501", "2026-10-03", "2026-10-03", "Acme Office Supplies Ltd", "Blue Sky Foods", "USD", "USD", [("Office chairs", "4", "100.00")]),
        invoice("XL-502", "2026-10-10", "2026-10-10", "FastNet Broadband", "Blue Sky Foods", "USD", "USD", [("Broadband internet, September", "1", "1000.00")]),
        invoice("XL-503", "2026-10-17", "2026-10-17", "Corner Coffee Roasters", "Blue Sky Foods", "EUR", "EUR", [("Coffee beans", "10", "16.00"), ("Oat milk", "24", "2.25")], tax_rate="19"),
    ]
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Invoices"
    sheet.append(["Invoice No", "Date", "Supplier", "Customer", "Subtotal", "Tax", "Total", "Currency"])
    for inv in sheet_invoices:
        sheet.append([inv["number"], datetime.datetime.fromisoformat(inv["date"]), inv["supplier"], inv["customer"],
                      float(inv["subtotal"]), float(inv["tax"]), float(inv["total"]), inv["currency"]])
    items = workbook.create_sheet("Line items")
    items.append(["Invoice No", "Description", "Qty", "Unit Price", "Amount"])
    for inv in sheet_invoices:
        for item in inv["items"]:
            items.append([inv["number"], item["description"], float(item["quantity"]), float(item["unit_price"]), float(item["amount"])])
    add("x01_invoices.xlsx", "spreadsheet", workbook_bytes(workbook), sheet_invoices,
        note="Excel: invoices on one sheet, their line items on another")

    csv_invoices = [
        invoice("B-9001", "2026-10-04", "2026-10-04", "Harbor Logistics Ltd", "Blue Sky Foods", "USD", "USD", [("x", "1", "500.00")]),
        invoice("B-9002", "2026-10-11", "2026-10-11", "Swift Couriers", "Blue Sky Foods", "USD", "USD", [("x", "1", "220.00")], wrong={"total": "263.00"}, expected_problems=["totals_match"]),
        invoice("B-9003", "2026-10-18", "2026-10-18", "", "Blue Sky Foods", "USD", "USD", [("x", "1", "80.00")], expected_problems=["missing_field"]),
        invoice("B-9004", "2026-10-25", "2026-10-25", "Metro Taxi Ltd", "Blue Sky Foods", "BDT", "BDT", [("x", "1", "3500.00")]),
    ]
    rows = ["Bill No,Bill Date,Vendor,Client,Net Amount,VAT,Grand Total,Currency Code"]
    for inv in csv_invoices:
        rows.append(f"{inv['number']},{inv['date']},{inv['supplier']},{inv['customer']},{inv['subtotal']},{inv['tax']},{inv['total']},{inv['currency']}")
    labels = [label(inv) for inv in csv_invoices]
    for one in labels:
        one["line_items"] = []  # the CSV has no line items
        one["fields"]["supplier_name"] = one["fields"]["supplier_name"] or None
    documents.append({"file": "x02_other_column_names.csv", "kind": "spreadsheet", "data": "\n".join(rows).encode(), "expected": "done",
                      "note": "CSV with other column names (Bill No, Vendor, Grand Total); one wrong total, one supplier missing",
                      "invoices": labels})
    eu = invoice("EU-77", "2026-10-19", "2026-10-19", "Müller & Söhne KG", "Blue Sky Foods", "EUR", "EUR", [("x", "1", "1234.56")], tax_rate="19")
    csv = ("Invoice Number;Invoice Date;Supplier;Customer;Subtotal;Tax;Total;Currency\n"
           f"EU-77;19.10.2026;{eu['supplier']};{eu['customer']};{money(eu['subtotal'], 'eu')};{money(eu['tax'], 'eu')};{money(eu['total'], 'eu')};EUR\n")
    eu_label = label(eu)
    eu_label["line_items"] = []
    documents.append({"file": "x03_semicolons_european.csv", "kind": "spreadsheet", "data": csv.encode("cp1252"), "expected": "done",
                      "note": "CSV as European Excel saves it: semicolons, 1.234,56, dd.mm.yyyy, Windows encoding", "invoices": [eu_label]})

    # Files that must fail (or be refused) with a clear message
    good_pdf = pdf_with_text([invoice_text(clean)])
    add("f01_damaged.pdf", "broken", good_pdf[: len(good_pdf) // 2], expected="failed", note="a PDF cut off in the middle")
    pdf = pymupdf.open()
    pdf.new_page().insert_text((50, 60), invoice_text(clean), fontname="cour", fontsize=10)
    add("f02_password.pdf", "broken", pdf.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="secret"),
        expected="failed", note="a password-protected PDF")
    blank = pymupdf.open()
    blank.new_page()
    add("f03_blank.pdf", "broken", blank.tobytes(), expected="failed", note="a PDF with only a blank page")
    no_text = Image.new("RGB", (800, 600), (90, 140, 200))
    ImageDraw.Draw(no_text).ellipse((250, 150, 550, 450), fill=(240, 200, 60))
    add("f04_picture_without_text.png", "broken", image_bytes(no_text, "PNG"), expected="failed", note="a picture with no text at all")
    add("f05_letter.docx", "unsupported", b"PK\x03\x04 a Word file", expected="refused", note="a Word file: not supported")
    add("f06_empty.csv", "unsupported", b"", expected="refused", note="an empty file")
    return documents


def main():
    labels_only = "--labels-only" in sys.argv
    documents = make_documents()
    if not labels_only:
        DATASET.mkdir(exist_ok=True)
        for old in DATASET.iterdir():  # start clean, so no old file stays behind
            old.unlink()
    for document in documents:
        data = document.pop("data")
        if not labels_only:
            (DATASET / document["file"]).write_bytes(data)
    gemini = sum(len(d["invoices"]) for d in documents if d["kind"] in ("digital PDF", "scanned PDF", "image"))
    labels = {
        "about": "The answer sheet for the evaluation. Made by make_dataset.py together with the files in dataset/.",
        "made_on": datetime.date.today().isoformat(),
        "documents": documents,
    }
    (FOLDER / "labels.json").write_text(json.dumps(labels, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    invoices = sum(len(d["invoices"]) for d in documents)
    print(f"{len(documents)} documents, {invoices} invoices ({gemini} need Gemini: one request each)")
    for kind in ["digital PDF", "scanned PDF", "image", "spreadsheet", "broken", "unsupported"]:
        group = [d for d in documents if d["kind"] == kind]
        print(f"  {kind:12} {len(group):2} documents, {sum(len(d['invoices']) for d in group):2} invoices")


if __name__ == "__main__":
    main()
