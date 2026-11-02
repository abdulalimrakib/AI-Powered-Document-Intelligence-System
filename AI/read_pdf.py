import pymupdf
from PIL import Image

from read_image import ocr_image, quality_warnings

# A page with fewer letters/digits than this is treated as a scanned picture and sent to OCR.
MIN_TEXT_CHARACTERS = 20

# 300 DPI is the usual quality for OCR: sharp enough to read, not too slow.
OCR_DPI = 300


def read_pdf(data: bytes) -> dict:
    """Read every page of a PDF.
    Digital pages: take the text directly (fast and exact).
    Scanned pages: turn the page into a picture and read it with OCR."""
    try:
        pdf = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise ValueError("The PDF is damaged and can't be opened")

    with pdf:
        if pdf.needs_pass:
            raise ValueError("The PDF is password-protected")
        if pdf.page_count == 0:
            raise ValueError("The PDF has no pages")

        pages = []
        warnings = []

        # One page at a time, so even a 1000-page PDF uses little memory.
        for page in pdf:
            page_number = page.number + 1
            try:
                result = read_page(page, page_number)
                pages.append(result)
                warnings.extend(quality_warnings(page_number, result["text"], result["ocr_confidence"]))
            except Exception:
                # A bad page should not stop the rest of the document.
                warnings.append(f"Page {page_number}: could not be read")

        return {"page_count": pdf.page_count, "pages": pages, "warnings": warnings}


def read_page(page: pymupdf.Page, page_number: int) -> dict:
    # sort=True gives the text top-to-bottom, left-to-right, like a person reads it.
    text = page.get_text(sort=True).strip()

    if count_letters_and_digits(text) >= MIN_TEXT_CHARACTERS:
        return {"page_number": page_number, "text": text, "method": "text", "ocr_confidence": None}

    # Almost no text: this page is a scanned picture. Render it in grayscale and OCR it.
    picture = page.get_pixmap(dpi=OCR_DPI, colorspace=pymupdf.csGRAY)
    image = Image.frombytes("L", (picture.width, picture.height), picture.samples)
    text, confidence = ocr_image(image)
    return {"page_number": page_number, "text": text, "method": "ocr", "ocr_confidence": confidence}


def count_letters_and_digits(text: str) -> int:
    return sum(character.isalnum() for character in text)
