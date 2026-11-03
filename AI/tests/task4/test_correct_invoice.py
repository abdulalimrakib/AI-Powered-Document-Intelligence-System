"""Step 6 — Checking an invoice again after a manual correction (POST /validate)"""

import pytest
from fastapi.testclient import TestClient

from extract_invoices import correct_invoice, failed_invoice, finish_invoice
from main import app

client = TestClient(app)


def field(value, status="found"):
    return {"value": value, "status": status, "evidence": value, "note": None}


def saved_invoice(**changes) -> dict:
    """An invoice as the backend saved it (cleaned values), with a wrong total."""
    fields = {
        "invoice_number": field("INV-101"), "invoice_date": field("2026-10-02"), "supplier_name": field("Acme Ltd"),
        "customer_name": field(None, "missing"), "subtotal": field("1000.00"), "tax": field("150.00"),
        "total": field("1180.00"), "currency": field("USD"),
    }
    fields.update(changes)
    return {"fields": fields, "line_items": [], "text": "INVOICE INV-101"}


def rules(invoice: dict) -> list[str]:
    return [error["rule"] for error in invoice["validation_errors"]]


def test_corrected_value_is_cleaned_and_marked_corrected():
    """A corrected value is cleaned like an extracted one, and marked 'corrected'"""
    invoice = correct_invoice(saved_invoice(), {"total": "1,150.00"})

    assert invoice["fields"]["total"] == {"value": "1150.00", "status": "corrected", "evidence": "1,150.00",
                                          "note": "corrected by hand"}


def test_invoice_is_checked_again_after_the_correction():
    """The invoice is checked again: fixing the total removes the 'totals don't add up' problem"""
    before = correct_invoice(saved_invoice(), {})
    after = correct_invoice(saved_invoice(), {"total": "1,150.00"})

    assert rules(before) == ["totals_match"]
    assert rules(after) == []
    assert after["needs_review"] is False


def test_a_correction_can_also_cause_a_new_problem():
    """A correction that makes the numbers wrong is reported"""
    invoice = correct_invoice(saved_invoice(total=field("1150.00")), {"tax": "200.00"})

    assert rules(invoice) == ["totals_match"]
    assert invoice["needs_review"] is True


def test_emptying_a_field_makes_it_missing():
    """Emptying a field makes it 'missing', and a missing important field needs review"""
    invoice = correct_invoice(saved_invoice(total=field("1150.00")), {"supplier_name": ""})

    assert invoice["fields"]["supplier_name"]["status"] == "missing"
    assert invoice["review_reasons"] == ["supplier name is missing"]


@pytest.mark.parametrize("corrections, message", [
    pytest.param({"total": "abc"}, "total: 'abc' is not an amount", id="abc as total"),
    pytest.param({"invoice_date": "03/04/2026"},
                 "invoice date: '03/04/2026' is unclear: the day and month could be either way round",
                 id="unclear date"),
    pytest.param({"invoice_date": "31/02/2026"}, "invoice date: '31/02/2026' is not a real date", id="31 February"),
    pytest.param({"currency": "xyz"}, "currency: 'xyz' is not a value we can read", id="unknown currency"),
    pytest.param({"total": "1150 or 1180"},
                 "total: '1150 or 1180' has more than one number; the first one was used", id="two numbers"),
    pytest.param({"colour": "red"},
                 "'colour' is not an invoice field. Fields: invoice_number, invoice_date, supplier_name, "
                 "customer_name, subtotal, tax, total, currency", id="unknown field"),
])
def test_a_value_that_cant_be_understood_is_refused(corrections, message):
    """A typed value that can't be understood is refused with a clear reason (nothing is guessed)"""
    with pytest.raises(ValueError) as error:
        correct_invoice(saved_invoice(), corrections)

    assert str(error.value) == message


def test_a_credit_note_stays_a_credit_note_after_a_correction():
    """The invoice's text is used again, so a credit note's negative amounts are still accepted"""
    credit_note = saved_invoice(subtotal=field("-100.00"), tax=field("-15.00"), total=field("-115.00"))
    credit_note["text"] = "CREDIT NOTE No: CN-1"

    invoice = correct_invoice(credit_note, {"supplier_name": "Acme Trading Ltd"})

    assert rules(invoice) == []


def test_extracted_invoices_keep_their_text():
    """Extracted invoices (also failed ones) keep their text, for checking again later and for search"""
    raw = {"fields": {name: {"value": None, "evidence": None} for name in saved_invoice()["fields"]},
           "line_items": [], "warnings": []}

    assert finish_invoice(raw, "Page 1", "gemini", {}, text="INVOICE No: INV-1")["text"] == "INVOICE No: INV-1"
    assert failed_invoice("Page 1", "AI extraction failed", "INVOICE No: INV-2")["text"] == "INVOICE No: INV-2"


def test_api_checks_a_corrected_invoice():
    """The /validate API cleans the correction and gives back the checked invoice"""
    response = client.post("/validate", json={"invoice": saved_invoice(), "corrections": {"total": "1,150.00"}})

    assert response.status_code == 200
    assert response.json()["fields"]["total"]["value"] == "1150.00"
    assert response.json()["needs_review"] is False


def test_api_refuses_a_value_it_cant_understand():
    """The /validate API answers 400 with the reason when a value can't be understood"""
    response = client.post("/validate", json={"invoice": saved_invoice(), "corrections": {"total": "abc"}})

    assert response.status_code == 400
    assert response.json() == {"detail": "total: 'abc' is not an amount"}


def test_api_refuses_an_invoice_in_the_wrong_shape():
    """The /validate API answers 400 (not a crash) for an invoice in the wrong shape"""
    response = client.post("/validate", json={"invoice": {"something": 1}, "corrections": {}})

    assert response.status_code == 400
    assert response.json() == {"detail": "The invoice is not in the expected shape"}
