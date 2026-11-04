"""Step 2 — The labeled dataset for the evaluation (the files and their answer sheet)"""

import json
import sys
from pathlib import Path

import pytest

import extract_invoices
from extract_invoices import extract_invoices_from_file
from validate_invoice import validate_invoice

EVALUATION = Path(__file__).parents[2] / "evaluation"
sys.path.insert(0, str(EVALUATION))
import make_dataset  # noqa: E402

LABELS = json.loads((EVALUATION / "labels.json").read_text(encoding="utf-8"))
DOCUMENTS = {document["file"]: document for document in LABELS["documents"]}
SPREADSHEETS = [name for name, document in DOCUMENTS.items() if document["kind"] == "spreadsheet"]
BROKEN = [name for name, document in DOCUMENTS.items() if document["kind"] == "broken"]
# Duplicates are not found by validate_invoice (they are found across documents)
FOUND_ELSEWHERE = {"duplicate_invoice"}
CURRENCY_WRITTEN_AS = {"USD": ["USD", "$"], "EUR": ["EUR", "€"], "GBP": ["GBP", "£"], "BDT": ["BDT", "Tk", "৳"]}


@pytest.fixture
def no_gemini(monkeypatch):
    """Make sure these checks never use a free Gemini request"""
    def refuse(text):
        raise AssertionError("Gemini must not be asked in this test")
    monkeypatch.setattr(extract_invoices, "extract_invoice", refuse)


def read(name: str) -> dict:
    return extract_invoices_from_file(name, (EVALUATION / "dataset" / name).read_bytes())


def test_every_labeled_file_exists_and_every_file_is_labeled():
    """Every file in the answer sheet exists, and every file in the dataset is in the answer sheet"""
    files = {path.name for path in (EVALUATION / "dataset").iterdir()}
    assert files == set(DOCUMENTS)


def test_making_the_dataset_again_gives_the_same_answer_sheet():
    """Making the dataset again gives exactly the same answer sheet (nothing random)"""
    again = make_dataset.make_documents()
    for document in again:
        document.pop("data")
    assert again == LABELS["documents"]


def test_dataset_has_every_kind_of_file():
    """The dataset has digital and scanned PDFs, images, spreadsheets, broken and unsupported files"""
    kinds = {document["kind"] for document in DOCUMENTS.values()}
    assert kinds == {"digital PDF", "scanned PDF", "image", "spreadsheet", "broken", "unsupported"}
    types = {name.rsplit(".", 1)[1] for name in DOCUMENTS}
    assert {"pdf", "png", "jpg", "tiff", "xlsx", "csv"} <= types


def test_dataset_fits_in_the_free_gemini_limit():
    """The invoices that need Gemini fit in one day of the free limit (one request each, at most 30)"""
    needs_gemini = sum(len(d["invoices"]) for d in DOCUMENTS.values() if d["kind"] in ("digital PDF", "scanned PDF", "image"))
    assert 0 < needs_gemini <= 30


def test_expected_problems_are_what_the_checks_find_on_the_right_values():
    """If every value were read correctly, the checks would find exactly the problems in the answer sheet"""
    for name, document in DOCUMENTS.items():
        for invoice in document["invoices"]:
            fields = {field: {"value": value, "status": "found" if value else "missing"} for field, value in invoice["fields"].items()}
            text = "CREDIT NOTE" if "credit" in name else ""
            found = {problem["rule"] for problem in validate_invoice({"fields": fields, "line_items": invoice["line_items"]}, text)}
            assert found == set(invoice["expected_problems"]) - FOUND_ELSEWHERE, name


@pytest.mark.parametrize("name", [pytest.param(name, id=name) for name, d in DOCUMENTS.items() if d["kind"] == "digital PDF"])
def test_labeled_values_can_really_be_read_in_the_digital_pdfs(name):
    """In every digital PDF, the labeled invoice number and currency can really be read in the file's text"""
    import pymupdf
    text = "".join(page.get_text() for page in pymupdf.open(EVALUATION / "dataset" / name))
    for invoice in DOCUMENTS[name]["invoices"]:
        assert invoice["fields"]["invoice_number"] in text
        currency = invoice["fields"]["currency"]
        written = [sign for signs in CURRENCY_WRITTEN_AS.values() for sign in signs if f"{sign} " in text]
        if currency:
            assert any(sign in written for sign in CURRENCY_WRITTEN_AS[currency]), f"{currency} is not written in {name}"
        else:
            assert written == [], f"no currency is labeled, but {written} is written in {name}"


@pytest.mark.parametrize("name", [pytest.param(name, id=name) for name in SPREADSHEETS])
def test_spreadsheets_are_read_exactly_as_labeled(no_gemini, name):
    """Spreadsheets (read without the AI) give exactly the labeled values, lines and problems"""
    result = read(name)

    assert result["error"] is None
    for got, want in zip(result["invoices"], DOCUMENTS[name]["invoices"], strict=True):
        assert {field: value["value"] for field, value in got["fields"].items()} == want["fields"]
        assert [{key: item[key] for key in ("description", "quantity", "unit_price", "amount")} for item in got["line_items"]] == want["line_items"]
        assert sorted({error["rule"] for error in got["validation_errors"]}) == want["expected_problems"]


@pytest.mark.parametrize("name", [pytest.param(name, id=name) for name in BROKEN])
def test_broken_files_fail_without_asking_gemini(no_gemini, name):
    """Broken files fail with a reason (as the answer sheet says), without spending a Gemini request"""
    result = read(name)

    reasons = [result["error"]] if result["error"] else [invoice["error"] for invoice in result["invoices"]]
    assert DOCUMENTS[name]["expected"] == "failed"
    assert reasons and all(reasons)
