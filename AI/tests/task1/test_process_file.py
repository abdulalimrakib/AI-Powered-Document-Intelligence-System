"""Steps 5 and 6 — Handling every file safely, with one result shape"""

from fastapi.testclient import TestClient

from main import app
from make_files import invoice_image, make_pdf, make_xlsx, to_bytes
from process_file import MAX_FILE_SIZE_BYTES, process_file

client = TestClient(app)


def test_result_always_has_the_same_shape():
    """Good and bad files give results in the same shape"""
    good = process_file("invoice.pdf", make_pdf(["digital"]))
    bad = process_file("broken.pdf", b"%PDF broken")

    assert good.keys() == bad.keys()
    assert good["error"] is None
    assert bad["error"] == "The PDF is damaged and can't be opened"


def test_pdf_fills_pages_and_spreadsheet_fills_sheets():
    """PDF results fill 'pages', spreadsheet results fill 'sheets'"""
    pdf = process_file("invoice.pdf", make_pdf(["digital"]))
    excel = process_file("invoices.xlsx", make_xlsx())

    assert pdf["file_type"] == "pdf" and pdf["page_count"] == 1 and pdf["sheets"] == []
    assert excel["file_type"] == "xlsx" and excel["pages"] == [] and len(excel["sheets"]) == 2


def test_renamed_file_is_still_read_with_a_warning():
    """Reads a renamed file by its real type and warns about the wrong name"""
    result = process_file("invoice.pdf", to_bytes(invoice_image(), "PNG"))

    assert result["file_type"] == "png"
    assert result["error"] is None
    assert "really a PNG file" in result["warnings"][0]


def test_empty_unsupported_and_too_big_files():
    """Gives clear messages for empty, unsupported and too-big (over 50 MB) files"""
    assert process_file("empty.csv", b"")["error"] == "The file is empty"
    assert process_file("program.exe", b"MZ\x90\x00 program")["error"].startswith("Unsupported file type")
    too_big = b"%PDF-1.7\n" + b"0" * MAX_FILE_SIZE_BYTES
    assert process_file("big.pdf", too_big)["error"] == "The file is larger than 50 MB"


def test_unexpected_error_does_not_crash(monkeypatch):
    """A bug inside a reader gives a simple message instead of crashing the server"""
    # Pretend the PDF reader has a bug.
    def broken_reader(data):
        raise RuntimeError("bug")

    monkeypatch.setitem(__import__("process_file").READERS, "pdf", broken_reader)

    result = process_file("invoice.pdf", make_pdf(["digital"]))

    assert result["error"] == "Something went wrong while reading this file"


def test_api_processes_many_files_and_one_bad_file_does_not_stop_the_others():
    """The /process API reads many files at once; one broken file does not stop the others"""
    files = [
        ("files", ("invoice.pdf", make_pdf(["digital"]), "application/pdf")),
        ("files", ("broken.pdf", b"%PDF broken", "application/pdf")),
        ("files", ("scan.png", to_bytes(invoice_image()), "image/png")),
    ]

    response = client.post("/process", files=files)

    assert response.status_code == 200
    results = response.json()
    assert [result["filename"] for result in results] == ["invoice.pdf", "broken.pdf", "scan.png"]
    assert [result["error"] is None for result in results] == [True, False, True]


def test_health():
    """The /health check works"""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
