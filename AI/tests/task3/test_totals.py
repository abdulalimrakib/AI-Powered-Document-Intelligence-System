"""Step 3 — Do the totals add up? (line items, subtotal, tax and total)"""

import pytest

from make_files import sample_invoice
from validate_invoice import validate_invoice


def lines(*amounts: str | None) -> list[tuple]:
    """Line items with only an amount (no quantity or unit price)."""
    return [(None, None, amount) for amount in amounts]


def test_correct_invoice_adds_up():
    """Line items, subtotal, tax and total that add up give no problems"""
    invoice = sample_invoice(line_items=lines("100.00", "900.00"))

    assert validate_invoice(invoice) == []


def test_line_items_that_do_not_add_up_to_the_subtotal():
    """Line items that don't add up to the subtotal are reported, with both numbers"""
    invoice = sample_invoice(line_items=lines("100.00", "800.00"))

    assert validate_invoice(invoice) == [{
        "field": "subtotal", "rule": "lines_match_subtotal",
        "message": "the line items add up to 900.00, but the subtotal says 1,000.00",
    }]


def test_total_that_is_not_subtotal_plus_tax():
    """A total that is not subtotal + tax is reported (e.g. OCR read 1,150 as 1,180)"""
    invoice = sample_invoice(total="1180.00")

    assert validate_invoice(invoice) == [{
        "field": "total", "rule": "totals_match",
        "message": "subtotal 1,000.00 + tax 150.00 = 1,150.00, but the total says 1,180.00",
    }]


@pytest.mark.parametrize("line_items, total", [
    pytest.param(lines("333.33", "333.33", "333.33"), "1150.00", id="3 lines add up to 999.99"),
    pytest.param(lines("333.33", "333.33", "333.32"), "1150.00", id="3 lines add up to 999.98"),
    pytest.param(lines("1000.00"), "1150.01", id="total 1 cent off"),
    pytest.param(lines("1000.00"), "1149.99", id="total 1 cent under"),
])
def test_small_rounding_differences_are_accepted(line_items, total):
    """Small rounding differences (1 cent per line) are accepted"""
    assert validate_invoice(sample_invoice(line_items=line_items, total=total)) == []


@pytest.mark.parametrize("line_items, total", [
    pytest.param(lines("333.33", "333.33"), "1150.00", id="2 lines add up to 666.66"),
    pytest.param(lines("1000.00"), "1150.02", id="total 2 cents off"),
])
def test_bigger_differences_are_reported(line_items, total):
    """Differences bigger than the rounding allowance are reported"""
    assert validate_invoice(sample_invoice(line_items=line_items, total=total)) != []


def test_no_subtotal_line_items_plus_tax_must_be_the_total():
    """Without a subtotal, line items + tax must be the total"""
    good = sample_invoice(line_items=lines("100.00", "900.00"), subtotal=None)
    wrong = sample_invoice(line_items=lines("100.00", "800.00"), subtotal=None)

    assert validate_invoice(good) == []
    assert validate_invoice(wrong) == [{
        "field": "total", "rule": "totals_match",
        "message": "line items 900.00 + tax 150.00 = 1,050.00, but the total says 1,150.00",
    }]


def test_no_tax_and_subtotal_equals_total_is_fine():
    """No tax, and subtotal = total, is fine (an invoice without tax)"""
    assert validate_invoice(sample_invoice(tax=None, total="1000.00")) == []


def test_no_tax_and_subtotal_differs_from_total():
    """No tax, but subtotal and total differ: reported, because the tax may have been missed"""
    assert validate_invoice(sample_invoice(tax=None)) == [{
        "field": "total", "rule": "totals_match",
        "message": "subtotal 1,000.00 and total 1,150.00 are different, but no tax was found",
    }]


def test_missing_total_is_reported_only_once():
    """A missing total is reported once (as missing), not again as a wrong sum"""
    problems = validate_invoice(sample_invoice(total=None))

    assert [problem["rule"] for problem in problems] == ["missing_field"]


def test_line_item_without_amount_skips_the_line_sum():
    """A line item without an amount: the lines are not added up (no false alarm)"""
    assert validate_invoice(sample_invoice(line_items=lines("100.00", None))) == []


def test_invoice_without_line_items_checks_only_subtotal_plus_tax():
    """An invoice without line items still checks subtotal + tax = total"""
    assert validate_invoice(sample_invoice(line_items=[])) == []
    assert validate_invoice(sample_invoice(line_items=[], total="1200.00")) != []
