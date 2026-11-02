import io

import pytesseract
from PIL import Image, ImageFilter, ImageOps, ImageSequence

# Below this OCR confidence (0-100) we warn about poor quality and try to fix the rotation.
LOW_CONFIDENCE = 60

# Images narrower than this are enlarged; small text is hard for OCR to read.
MIN_WIDTH = 1500

# Stronger speckle filters, tried only when the normal clean-up gives low confidence.
STRONGER_SPECKLE_FILTERS = [5, 7]


def read_image(data: bytes) -> dict:
    """Read a JPG, PNG or TIFF with OCR. A TIFF can hold many pages; each one is read."""
    try:
        picture = Image.open(io.BytesIO(data))
    except Image.DecompressionBombError:
        raise ValueError("The image is too large to process")
    except Exception:
        raise ValueError("The image is damaged and can't be opened")

    pages = []
    warnings = []
    page_count = 0

    with picture:
        for frame in ImageSequence.Iterator(picture):
            page_count += 1
            try:
                # Phone photos store "rotate me" in their EXIF data; apply it first.
                image = ImageOps.exif_transpose(frame)
                text, confidence = ocr_image(image)
            except Exception:
                warnings.append(f"Page {page_count}: could not be read")
                continue
            pages.append({"page_number": page_count, "text": text, "method": "ocr", "ocr_confidence": confidence})
            warnings.extend(quality_warnings(page_count, text, confidence))

    if not pages:
        raise ValueError("The image is damaged and can't be opened")
    return {"page_count": page_count, "pages": pages, "warnings": warnings}


def ocr_image(image: Image.Image) -> tuple[str, float]:
    """Clean up a picture and read its text with Tesseract OCR.
    Returns (text, confidence), where confidence is 0-100."""
    text, confidence = run_tesseract(clean_image(image))

    # Most pages are fine at this point (confidence around 95), so the extra tries below
    # only run for bad pages. Each try keeps whichever result Tesseract is more sure about.

    # Try 1: the page may be sideways or upside down (quick to check, so it goes first).
    if confidence < LOW_CONFIDENCE:
        turned_image = turn_upright(image)
        if turned_image is not None:
            new_text, new_confidence = run_tesseract(clean_image(turned_image))
            if new_confidence > confidence:
                image, text, confidence = turned_image, new_text, new_confidence

    # Try 2: heavy scanner noise needs a stronger speckle filter.
    if confidence < LOW_CONFIDENCE:
        for filter_size in STRONGER_SPECKLE_FILTERS:
            new_text, new_confidence = run_tesseract(clean_image(image, speckle_filter_size=filter_size))
            if new_confidence > confidence:
                text, confidence = new_text, new_confidence

    return text, confidence


def clean_image(image: Image.Image, speckle_filter_size: int = 3) -> Image.Image:
    """Make the picture easier for OCR to read. The order of these steps matters (we measured it)."""
    image = image.convert("L")  # grayscale: colour only confuses OCR

    if image.width < MIN_WIDTH:  # 1. enlarge small images
        scale = MIN_WIDTH / image.width
        image = image.resize((MIN_WIDTH, round(image.height * scale)), Image.LANCZOS)

    image = image.filter(ImageFilter.MedianFilter(speckle_filter_size))  # 2. remove speckles (scanner noise)
    image = ImageOps.autocontrast(image, cutoff=1)  # 3. make faded text darker
    image = image.filter(ImageFilter.SHARPEN)  # 4. make blurry edges crisper
    return image


def run_tesseract(image: Image.Image) -> tuple[str, float]:
    """Run OCR once. Tesseract gives every word with a confidence; we rebuild the lines
    and average the word confidences."""
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

    lines = {}
    confidences = []
    for i, word in enumerate(data["text"]):
        word = word.strip()
        if not word:
            continue
        line_key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(line_key, []).append(word)
        confidences.append(float(data["conf"][i]))

    text = "\n".join(" ".join(words) for words in lines.values())
    confidence = round(sum(confidences) / len(confidences), 1) if confidences else 0.0
    return text, confidence


def turn_upright(image: Image.Image) -> Image.Image | None:
    """Ask Tesseract which way the page faces and turn it upright.
    Returns None if there isn't enough text to tell, or the page is already upright."""
    try:
        orientation = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractError:
        return None
    if orientation["rotate"] == 0:
        return None
    # Tesseract says how far to turn clockwise; Pillow turns anti-clockwise, hence the minus.
    return image.rotate(-orientation["rotate"], expand=True)


def quality_warnings(page_number: int, text: str, confidence: float | None) -> list[str]:
    """Warnings shown to the user for a page that may be unreliable."""
    if not text:
        return [f"Page {page_number}: no text found (blank page?)"]
    if confidence is not None and confidence < LOW_CONFIDENCE:
        return [f"Page {page_number}: poor image quality (OCR confidence {confidence:.0f}%)"]
    return []
