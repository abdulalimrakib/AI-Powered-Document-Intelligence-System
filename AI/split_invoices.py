import re

# Finds an invoice-number label and the number after it, for example:
#   "Invoice No: INV-2026-001", "INVOICE #: 1234", "Invoice Number 55/A", "Tax Invoice No. 7", "Inv. No: 88"
# The label and the number may be on different lines (common in OCR text of tables).
INVOICE_NUMBER = re.compile(
    r"\b(?:invoice|inv\.?)\s*(?:no\.?|number|num\.?|#)\s*[:#.]?\s*([A-Za-z0-9][A-Za-z0-9\-/.]*)",
    re.IGNORECASE,
)


def split_into_invoices(pages: list[dict]) -> list[dict]:
    """Split the pages of one document (from Task 1) into separate invoices.

    A page starts a new invoice when it shows an invoice number that is different from the
    current invoice's number. Pages without a number, or with the same number (a heading
    repeated on every page), belong to the invoice before them. A document without any
    invoice number is treated as one invoice."""
    invoices = []

    for page in pages:
        number = find_invoice_number(page["text"])
        current = invoices[-1] if invoices else None

        starts_new_invoice = number is not None and (current is None or current["number_seen"] not in (None, number))
        if current is None or starts_new_invoice:
            current = {"number_seen": number, "pages": []}
            invoices.append(current)
        elif current["number_seen"] is None:
            # Pages before the first invoice number (e.g. a cover page) join the first invoice.
            current["number_seen"] = number

        current["pages"].append(page)

    return [build_invoice(invoice["pages"]) for invoice in invoices]


def find_invoice_number(text: str) -> str | None:
    """Return the first invoice number on the page, written in one standard way (upper case),
    or None. A real invoice number always contains at least one digit."""
    for match in INVOICE_NUMBER.finditer(text):
        number = match.group(1).rstrip(".").upper()
        if any(character.isdigit() for character in number):
            return number
    return None


def build_invoice(pages: list[dict]) -> dict:
    """Join the text of an invoice's pages. Page markers tell the AI (and the user) where each page starts."""
    text = "\n\n".join(f"--- Page {page['page_number']} ---\n{page['text']}" for page in pages)

    # The worst OCR confidence of these pages: later, values from badly scanned pages are marked uncertain.
    confidences = [page["ocr_confidence"] for page in pages if page["ocr_confidence"] is not None]

    return {
        "pages": [page["page_number"] for page in pages],
        "text": text,
        "lowest_ocr_confidence": min(confidences) if confidences else None,
    }
