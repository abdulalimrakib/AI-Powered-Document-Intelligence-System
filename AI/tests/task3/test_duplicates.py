"""Step 4 — Duplicate invoices"""

import pytest

from make_files import sample_invoice
from validate_invoice import find_duplicates


def rules_per_invoice(invoices: list[tuple]) -> list[list[str]]:
    return [[problem["rule"] for problem in problems] for problems in find_duplicates(invoices)]


def test_same_supplier_and_number_is_a_duplicate():
    """Same supplier and same invoice number is a duplicate; both invoices point to each other"""
    invoices = [("a.pdf, Page 1", sample_invoice()), ("b.pdf, Page 1", sample_invoice())]

    first, second = find_duplicates(invoices)

    assert first == [{"field": "invoice_number", "rule": "duplicate_invoice",
                      "message": "duplicate: same supplier and invoice number as b.pdf, Page 1"}]
    assert second == [{"field": "invoice_number", "rule": "duplicate_invoice",
                       "message": "duplicate: same supplier and invoice number as a.pdf, Page 1"}]


@pytest.mark.parametrize("number, supplier", [
    pytest.param("inv-001", "Acme Trading Ltd", id="inv-001 in small letters"),
    pytest.param("INV 001", "Acme Trading Ltd", id="INV 001 with a space"),
    pytest.param("INV001", "Acme Trading Ltd", id="INV001 without a dash"),
    pytest.param("INV-001", "ACME TRADING LTD.", id="supplier in capitals with a dot"),
])
def test_same_invoice_written_differently_is_a_duplicate(number, supplier):
    """The same number or supplier written a little differently is still a duplicate"""
    invoices = [("a", sample_invoice()), ("b", sample_invoice(invoice_number=number, supplier_name=supplier))]

    assert rules_per_invoice(invoices) == [["duplicate_invoice"], ["duplicate_invoice"]]


def test_same_number_from_different_suppliers_is_not_a_duplicate():
    """Two different suppliers may both use the number INV-001"""
    invoices = [("a", sample_invoice()), ("b", sample_invoice(supplier_name="Globex Inc", total="99.00"))]

    assert rules_per_invoice(invoices) == [[], []]


def test_same_number_with_unknown_supplier_is_a_possible_duplicate():
    """Same number, but the supplier is unknown on one: a possible duplicate"""
    invoices = [("a", sample_invoice()), ("b", sample_invoice(supplier_name=None))]

    assert rules_per_invoice(invoices) == [["possible_duplicate"], ["possible_duplicate"]]


def test_misread_number_with_same_supplier_date_and_total_is_a_possible_duplicate():
    """A different number but the same supplier, date and total (e.g. a misread number): a possible duplicate"""
    invoices = [("a", sample_invoice()), ("b", sample_invoice(invoice_number="INV-0O1"))]

    first, _ = find_duplicates(invoices)

    assert first == [{"field": "invoice_number", "rule": "possible_duplicate",
                      "message": "possible duplicate: same supplier, date and total as b"}]


def test_different_invoices_from_the_same_supplier_are_not_duplicates():
    """Different invoices from the same supplier are not duplicates"""
    invoices = [("a", sample_invoice()), ("b", sample_invoice(invoice_number="INV-002", total="99.00"))]

    assert rules_per_invoice(invoices) == [[], []]


def test_invoices_without_numbers_are_not_duplicates():
    """Two invoices with no number and no supplier (e.g. both failed) are not called duplicates"""
    empty = {"invoice_number": None, "supplier_name": None, "invoice_date": None, "total": None}
    invoices = [("a", sample_invoice(**empty)), ("b", sample_invoice(**empty))]

    assert rules_per_invoice(invoices) == [[], []]


def test_three_copies_each_point_to_the_other_two():
    """Three copies of one invoice: each one points to the other two"""
    invoices = [("a", sample_invoice()), ("b", sample_invoice()), ("c", sample_invoice())]

    assert [len(problems) for problems in find_duplicates(invoices)] == [2, 2, 2]


def test_a_single_invoice_has_no_duplicates():
    """An upload with one invoice has no duplicates"""
    assert find_duplicates([("a", sample_invoice())]) == [[]]
