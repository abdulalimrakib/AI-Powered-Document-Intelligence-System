"""Step 3 — Reading images with OCR"""

import io

import pytest
from PIL import Image

from make_files import add_speckles, blur, invoice_image, to_bytes, word_accuracy
from read_image import read_image


def read_first_page(data: bytes) -> dict:
    return read_image(data)["pages"][0]


@pytest.mark.parametrize("file_format", ["PNG", "JPEG", "TIFF"])
def test_reads_each_image_format(file_format):
    """Reads the text of an image file, every word correct"""
    page = read_first_page(to_bytes(invoice_image(), file_format))

    assert page["method"] == "ocr"
    assert word_accuracy(page["text"]) == 100


# Poor quality images: the clean-up steps should still get (almost) every word.
@pytest.mark.parametrize("image, min_accuracy", [
    pytest.param(invoice_image().resize((566, 366)), 95, id="small"),
    pytest.param(blur(invoice_image()), 90, id="blurry"),
    pytest.param(invoice_image(text_color=175, background=215), 95, id="faded"),
    pytest.param(add_speckles(invoice_image()), 95, id="speckled"),
    pytest.param(invoice_image().convert("RGB"), 95, id="colour"),
])
def test_poor_quality_images(image, min_accuracy):
    """Reads a poor-quality image correctly"""
    page = read_first_page(to_bytes(image))

    assert word_accuracy(page["text"]) >= min_accuracy


@pytest.mark.parametrize("angle", [
    pytest.param(90, id="turned 90 degrees"),
    pytest.param(180, id="upside down"),
    pytest.param(270, id="turned 270 degrees"),
])
def test_sideways_and_upside_down_pages_are_turned(angle):
    """Turns a sideways or upside-down page and reads it, every word correct"""
    page = read_first_page(to_bytes(invoice_image().rotate(angle, expand=True)))

    assert word_accuracy(page["text"]) == 100


def test_phone_photo_rotation_is_applied():
    """Uses the rotation saved inside a phone photo"""
    # Phones save the picture sideways plus a note (EXIF orientation 6) saying "turn me 90°".
    exif = Image.Exif()
    exif[0x0112] = 6
    photo = to_bytes(invoice_image().convert("RGB").rotate(90, expand=True), "JPEG", exif=exif)

    assert word_accuracy(read_first_page(photo)["text"]) == 100


def test_every_page_of_a_tiff_is_read():
    """Reads every page of a 3-page TIFF and warns about the blank page"""
    buffer = io.BytesIO()
    blank_page = Image.new("L", (1700, 1100), 255)
    invoice_image().save(buffer, "TIFF", save_all=True, append_images=[blank_page, invoice_image()])

    result = read_image(buffer.getvalue())

    assert result["page_count"] == 3
    assert word_accuracy(result["pages"][0]["text"]) == 100
    assert word_accuracy(result["pages"][2]["text"]) == 100
    assert result["warnings"] == ["Page 2: no text found (blank page?)"]


def test_unreadable_picture_gives_a_poor_quality_warning():
    """Warns when a picture has no readable text"""
    # Pure noise: there is no text to find, but OCR may "see" a few letters in the dots.
    noise = add_speckles(Image.new("L", (1200, 800), 255), amount=0.5)

    result = read_image(to_bytes(noise))

    assert result["warnings"], "a picture of pure noise must not pass without a warning"


@pytest.mark.parametrize("broken_file", [
    pytest.param(to_bytes(invoice_image())[:300], id="image cut off in the middle"),
    pytest.param(b"\x89PNG\r\n\x1a\n not an image", id="right start, garbage after"),
])
def test_damaged_image(broken_file):
    """Gives a clear message for a damaged image"""
    with pytest.raises(ValueError, match="damaged"):
        read_image(broken_file)
