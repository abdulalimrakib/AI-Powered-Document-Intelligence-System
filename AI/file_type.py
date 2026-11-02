import io
import zipfile

# The first bytes ("signature") of each supported file type.
# We trust these instead of the file name, because a name can be changed by anyone.
SIGNATURES = [
    (b"%PDF", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"II*\x00", "tiff"),  # TIFF saved on Intel-style computers
    (b"MM\x00*", "tiff"),  # TIFF saved on Motorola-style computers
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "xls"),  # old Office format
]


def detect_file_type(data: bytes) -> str | None:
    """Return the real file type ("pdf", "png", "jpg", "tiff", "xlsx", "xls", "csv"),
    or None if the file is empty or not a type we support."""
    if not data:
        return None

    for signature, file_type in SIGNATURES:
        if data.startswith(signature):
            return file_type

    # An XLSX file is really a zip file. Word (.docx) files are zips too,
    # so we look inside: only Excel files have "xl/workbook.xml".
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zip_file:
                if "xl/workbook.xml" in zip_file.namelist():
                    return "xlsx"
        except zipfile.BadZipFile:
            return None
        return None

    # A CSV is plain text. Binary files almost always contain zero bytes; text never does.
    if b"\x00" not in data[:4096]:
        return "csv"

    return None
