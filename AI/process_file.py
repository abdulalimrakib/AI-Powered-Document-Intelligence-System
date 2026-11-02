import logging
import time

from file_type import detect_file_type
from read_image import read_image
from read_pdf import read_pdf
from read_spreadsheet import read_csv, read_xls, read_xlsx

MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Which reader handles which file type.
READERS = {
    "pdf": read_pdf,
    "png": read_image,
    "jpg": read_image,
    "tiff": read_image,
    "xlsx": read_xlsx,
    "xls": read_xls,
    "csv": read_csv,
}

# File name endings we expect for each type (only used to warn about renamed files).
EXTENSIONS = {
    "pdf": [".pdf"],
    "png": [".png"],
    "jpg": [".jpg", ".jpeg"],
    "tiff": [".tif", ".tiff"],
    "xlsx": [".xlsx"],
    "xls": [".xls"],
    "csv": [".csv", ".txt"],
}

logger = logging.getLogger(__name__)


def process_file(filename: str, data: bytes) -> dict:
    """Read one uploaded file and always return the same shape, even when the file is bad.
    A bad file gets an "error" message; it never crashes the server."""
    start = time.perf_counter()
    result = {
        "filename": filename,
        "file_type": None,
        "page_count": 0,  # pages of a PDF or image
        "pages": [],  # filled for PDF and images
        "sheets": [],  # filled for Excel and CSV
        "warnings": [],
        "error": None,
        "processing_seconds": 0.0,
    }

    try:
        if not data:
            raise ValueError("The file is empty")
        if len(data) > MAX_FILE_SIZE_BYTES:
            raise ValueError(f"The file is larger than {MAX_FILE_SIZE_MB} MB")

        file_type = detect_file_type(data)
        if file_type is None:
            raise ValueError("Unsupported file type. Allowed: PDF, JPG, PNG, TIFF, XLSX, XLS, CSV")
        result["file_type"] = file_type

        if not filename.lower().endswith(tuple(EXTENSIONS[file_type])):
            result["warnings"].append(f"The file name doesn't match its content: it is really a {file_type.upper()} file")

        reader = READERS[file_type]
        output = reader(data)  # gives "pages"/"page_count" or "sheets", plus "warnings"
        result["warnings"] += output.pop("warnings")
        result.update(output)

    except ValueError as error:
        # Our readers raise ValueError with a message meant for the user.
        result["error"] = str(error)
    except Exception:
        # Anything else is a bug or a very strange file. Log the details for us, keep the message simple.
        logger.exception("Unexpected error while reading %s", filename)
        result["error"] = "Something went wrong while reading this file"

    result["processing_seconds"] = round(time.perf_counter() - start, 2)
    return result
