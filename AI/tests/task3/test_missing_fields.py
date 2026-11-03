"""Step 1 — Missing fields"""

import pytest

from make_files import sample_invoice
from validate_invoice import validate_invoice


def rules(problems: list[dict]) -> list[str]:
    return [problem["rule"] for problem in problems]


def test_complete_invoice_has_no_problems():
    """A complete, correct invoice has no problems"""
    assert validate_invoice(sample_invoice()) == []


@pytest.mark.parametrize("name", [
    pytest.param("invoice_number", id="invoice number"),
    pytest.param("invoice_date", id="invoice date"),
    pytest.param("supplier_name", id="supplier name"),
    pytest.param("total", id="total"),
])
def test_missing_important_field_is_reported(name):
    """A missing important field is reported with the field name and a plain message"""
    problems = validate_invoice(sample_invoice(**{name: None}))

    assert problems == [{"field": name, "rule": "missing_field", "message": f"{name.replace('_', ' ')} is missing"}]


def test_missing_customer_is_not_a_problem():
    """A missing customer name is not a problem (not every invoice names one)"""
    assert validate_invoice(sample_invoice(customer_name=None)) == []


def test_uncertain_field_is_reported_with_its_reason():
    """A field Task 2 was not sure about is reported, with the reason"""
    invoice = sample_invoice()
    invoice["fields"]["invoice_date"].update(status="uncertain", note="'03/04/2026' is unclear")

    problems = validate_invoice(invoice)

    assert problems == [{"field": "invoice_date", "rule": "uncertain_value",
                         "message": "invoice date is uncertain: '03/04/2026' is unclear"}]


def test_several_missing_fields_are_all_reported():
    """Several missing fields are all reported, not only the first one"""
    problems = validate_invoice(sample_invoice(invoice_number=None, supplier_name=None))

    assert rules(problems) == ["missing_field", "missing_field"]
    assert [problem["field"] for problem in problems] == ["invoice_number", "supplier_name"]
