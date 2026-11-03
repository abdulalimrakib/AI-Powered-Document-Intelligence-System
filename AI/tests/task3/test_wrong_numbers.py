"""Step 2 — Wrong numbers"""

import datetime

import pytest

from make_files import sample_invoice
from validate_invoice import validate_invoice


def rules(problems: list[dict]) -> list[str]:
    return [problem["rule"] for problem in problems]


@pytest.mark.parametrize("values, expected", [
    pytest.param({"subtotal": "-1000.00", "total": "-850.00"}, "subtotal is negative (-1,000.00)", id="subtotal"),
    pytest.param({"tax": "-150.00", "total": "850.00"}, "tax is negative (-150.00)", id="tax"),
    pytest.param({"subtotal": None, "tax": None, "total": "-1150.00"}, "total is negative (-1,150.00)", id="total"),
])
def test_negative_money_is_reported(values, expected):
    """A negative amount on a normal invoice is reported"""
    problems = validate_invoice(sample_invoice(**values))

    assert expected in [problem["message"] for problem in problems]
    assert "negative_amount" in rules(problems)


def test_credit_note_may_have_negative_amounts():
    """A credit note (money given back) may have negative amounts"""
    invoice = sample_invoice(line_items=[("1", "-100.00", "-100.00")],
                             subtotal="-100.00", tax="-15.00", total="-115.00")

    assert validate_invoice(invoice, text="CREDIT NOTE No: CN-1") == []


def test_same_negative_amounts_without_credit_note_are_reported():
    """The same negative amounts are reported when the document is not a credit note"""
    invoice = sample_invoice(line_items=[("1", "-100.00", "-100.00")],
                             subtotal="-100.00", tax="-15.00", total="-115.00")

    assert rules(validate_invoice(invoice, text="INVOICE No: INV-1")) == ["negative_amount"] * 5


def test_zero_total_is_reported():
    """A total of 0.00 is reported"""
    problems = validate_invoice(sample_invoice(subtotal=None, tax=None, total="0.00"))

    assert problems == [{"field": "total", "rule": "zero_total", "message": "total is 0.00"}]


def test_tax_bigger_than_subtotal_is_reported():
    """Tax bigger than the subtotal is reported"""
    problems = validate_invoice(sample_invoice(subtotal="100.00", tax="150.00", total="250.00"))

    assert problems == [{"field": "tax", "rule": "tax_too_big",
                         "message": "tax (150.00) is bigger than the subtotal (100.00)"}]


@pytest.mark.parametrize("quantity", [pytest.param("0", id="0"), pytest.param("-2", id="-2")])
def test_quantity_must_be_above_zero(quantity):
    """A line with a quantity of zero or less is reported"""
    invoice = sample_invoice(line_items=[(quantity, "50.00", None)], subtotal=None)

    assert rules(validate_invoice(invoice)) == ["bad_quantity"]


def test_wrong_line_amount_is_reported_with_the_numbers():
    """A line where quantity × unit price is not the amount is reported, with the numbers"""
    invoice = sample_invoice(line_items=[("2", "50.00", "120.00")], subtotal="120.00", tax="0.00", total="120.00")

    problems = validate_invoice(invoice)

    assert problems == [{"field": "line item 1", "rule": "line_math",
                         "message": "line item 1: 2 × 50.00 = 100.00, but the amount says 120.00"}]


@pytest.mark.parametrize("quantity, unit_price, amount", [
    pytest.param("2", "50.00", "100.00", id="2 x 50.00 = 100.00"),
    pytest.param("3", "33.33", "100.00", id="3 x 33.33 = 99.99, rounded to 100.00"),
    pytest.param("1.5", "10.00", "15.00", id="1.5 x 10.00 = 15.00"),
    pytest.param("0.333", "30.00", "9.99", id="0.333 x 30.00 = 9.99"),
])
def test_correct_line_amount_is_accepted(quantity, unit_price, amount):
    """A correct line amount, also with rounding by 1 cent, is accepted"""
    invoice = sample_invoice(line_items=[(quantity, unit_price, amount)], subtotal=None, tax=None, total=amount)

    assert validate_invoice(invoice) == []


def test_line_with_a_missing_number_is_not_calculated():
    """A line with a missing number is not calculated (no false alarm)"""
    invoice = sample_invoice(line_items=[("2", None, "100.00")], subtotal=None, tax=None, total="100.00")

    assert validate_invoice(invoice) == []


def test_future_date_is_reported():
    """An invoice date in the future is reported"""
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

    problems = validate_invoice(sample_invoice(invoice_date=tomorrow))

    assert problems == [{"field": "invoice_date", "rule": "future_date",
                         "message": f"invoice date {tomorrow} is in the future"}]


def test_todays_date_is_accepted():
    """An invoice dated today is accepted"""
    assert validate_invoice(sample_invoice(invoice_date=datetime.date.today().isoformat())) == []


def test_very_old_date_is_reported():
    """A date before 2000 is reported as a probable reading mistake"""
    assert rules(validate_invoice(sample_invoice(invoice_date="1926-10-15"))) == ["very_old_date"]
