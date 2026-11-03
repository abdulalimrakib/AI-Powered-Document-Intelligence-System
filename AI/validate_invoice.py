"""Task 3: check that an invoice is complete and that its numbers make sense.

Every problem found is written the same way, so they can all be shown in one list
(and later saved in the validation_errors table):

    {"field": "total", "rule": "missing_field", "message": "total is missing"}
"""

import datetime
from decimal import Decimal

# If one of these is missing or uncertain, a person has to check the invoice.
IMPORTANT_FIELDS = ["invoice_number", "invoice_date", "supplier_name", "total"]

MONEY_FIELDS = ["subtotal", "tax", "total"]

# Invoices round every line to the cent, so a difference of 1 cent is not a mistake.
ROUNDING = Decimal("0.01")

# A date before this is almost surely a reading mistake (e.g. "2026" read as "1926").
OLDEST_DATE = datetime.date(2000, 1, 1)


def validate_invoice(invoice: dict, text: str = "") -> list[dict]:
    """Run all the checks on one finished invoice (from Task 2). An empty list means no problems.
    `text` is the invoice's text; it is only used to see if the invoice is a credit note."""
    credit_note = is_credit_note(text)
    problems = []
    problems += check_missing_fields(invoice["fields"])  # Step 1
    problems += check_numbers(invoice["fields"], credit_note)  # Step 2
    problems += check_line_items(invoice["line_items"], credit_note)  # Step 2
    problems += check_date(invoice["fields"])  # Step 2
    problems += check_totals(invoice["fields"], invoice["line_items"])  # Step 3
    return problems


# ---------- Step 1: missing fields ----------

def check_missing_fields(fields: dict) -> list[dict]:
    """Every important field must be there. A value we are not sure about also needs a person to look."""
    problems = []
    for name in IMPORTANT_FIELDS:
        field = fields[name]
        if field["status"] == "missing":
            problems.append(problem(name, "missing_field", f"{readable(name)} is missing"))
        elif field["status"] == "uncertain":
            problems.append(problem(name, "uncertain_value", f"{readable(name)} is uncertain: {field['note']}"))
    return problems


# ---------- Step 2: wrong numbers ----------

def check_numbers(fields: dict, credit_note: bool) -> list[dict]:
    """Each money value on its own: no negative amounts (except on a credit note),
    a total above zero, and tax not bigger than the subtotal."""
    problems = []
    if not credit_note:
        for name in MONEY_FIELDS:
            amount = number(fields[name]["value"])
            if amount is not None and amount < 0:
                problems.append(problem(name, "negative_amount", f"{readable(name)} is negative ({money(amount)})"))

    total = number(fields["total"]["value"])
    if total == 0:
        problems.append(problem("total", "zero_total", "total is 0.00"))

    subtotal = number(fields["subtotal"]["value"])
    tax = number(fields["tax"]["value"])
    if subtotal is not None and tax is not None and abs(tax) > abs(subtotal):
        problems.append(problem("tax", "tax_too_big",
                                f"tax ({money(tax)}) is bigger than the subtotal ({money(subtotal)})"))
    return problems


def check_line_items(line_items: list[dict], credit_note: bool) -> list[dict]:
    """Each line: quantity above zero, no negative money, and quantity × unit price = amount."""
    problems = []
    for position, item in enumerate(line_items, start=1):
        field = f"line item {position}"
        quantity = number(item["quantity"])
        unit_price = number(item["unit_price"])
        amount = number(item["amount"])

        if quantity is not None and quantity <= 0 and not credit_note:
            problems.append(problem(field, "bad_quantity", f"{field}: quantity is {quantity}"))
        if not credit_note:
            for name, value in [("unit price", unit_price), ("amount", amount)]:
                if value is not None and value < 0:
                    problems.append(problem(field, "negative_amount", f"{field}: {name} is negative ({money(value)})"))

        # Only when all three are there: we can't check a sum with a missing number.
        if quantity is not None and unit_price is not None and amount is not None:
            expected = (quantity * unit_price).quantize(ROUNDING)
            if abs(expected - amount) > ROUNDING:
                problems.append(problem(field, "line_math",
                                        f"{field}: {quantity} × {money(unit_price)} = {money(expected)}, "
                                        f"but the amount says {money(amount)}"))
    return problems


def check_date(fields: dict) -> list[dict]:
    """The invoice date can't be in the future, and a very old date is probably a reading mistake."""
    value = fields["invoice_date"]["value"]
    if value is None:
        return []  # a missing date is already reported in Step 1
    invoice_date = datetime.date.fromisoformat(value)
    if invoice_date > datetime.date.today():
        return [problem("invoice_date", "future_date", f"invoice date {value} is in the future")]
    if invoice_date < OLDEST_DATE:
        return [problem("invoice_date", "very_old_date", f"invoice date {value} is before 2000; is it read correctly?")]
    return []


# ---------- Step 3: do the totals add up? ----------

def check_totals(fields: dict, line_items: list[dict]) -> list[dict]:
    """Check the two sums on an invoice, like an accountant does by hand:
        line 1 + line 2 + ... = subtotal
        subtotal + tax       = total
    A sum is only checked when all its numbers are there (missing ones are reported in Step 1)."""
    subtotal = number(fields["subtotal"]["value"])
    tax = number(fields["tax"]["value"])
    total = number(fields["total"]["value"])

    amounts = [number(item["amount"]) for item in line_items]
    lines_sum = sum(amounts) if amounts and None not in amounts else None
    # Every line can be rounded by 1 cent, so a sum of 5 lines may be up to 5 cents off.
    lines_rounding = ROUNDING * len(amounts)

    problems = []
    if lines_sum is not None and subtotal is not None and abs(lines_sum - subtotal) > lines_rounding:
        problems.append(problem("subtotal", "lines_match_subtotal",
                                f"the line items add up to {money(lines_sum)}, but the subtotal says {money(subtotal)}"))

    # No subtotal written? Then the line items are the subtotal.
    if subtotal is not None:
        base_name, base, allowed = "subtotal", subtotal, ROUNDING
    else:
        base_name, base, allowed = "line items", lines_sum, lines_rounding
    if total is None or base is None:
        return problems

    if tax is not None:
        expected = base + tax
        if abs(expected - total) > allowed:
            problems.append(problem("total", "totals_match",
                                    f"{base_name} {money(base)} + tax {money(tax)} = {money(expected)}, "
                                    f"but the total says {money(total)}"))
    elif abs(base - total) > allowed:
        problems.append(problem("total", "totals_match",
                                f"{base_name} {money(base)} and total {money(total)} are different, "
                                f"but no tax was found"))
    return problems


# ---------- Step 4: duplicate invoices ----------

def find_duplicates(invoices: list[tuple[str, dict]]) -> list[list[dict]]:
    """Compare every invoice with every other one in the same upload.
    `invoices` is a list of (where it is, invoice), e.g. ("bills.pdf, Page 2", {...}).
    Returns one list of problems per invoice, in the same order."""
    problems = [[] for _ in invoices]
    for first in range(len(invoices)):
        for second in range(first + 1, len(invoices)):
            first_place, first_invoice = invoices[first]
            second_place, second_invoice = invoices[second]
            match = compare_invoices(first_invoice["fields"], second_invoice["fields"])
            if match:
                rule, reason = match
                problems[first].append(problem("invoice_number", rule, f"{reason} as {second_place}"))
                problems[second].append(problem("invoice_number", rule, f"{reason} as {first_place}"))
    return problems


def compare_invoices(first: dict, second: dict) -> tuple[str, str] | None:
    """Are these two the same invoice? Returns (rule, reason), or None when they are different."""
    first_number, second_number = simple_key(first["invoice_number"]), simple_key(second["invoice_number"])
    first_supplier, second_supplier = simple_key(first["supplier_name"]), simple_key(second["supplier_name"])

    if first_number and first_number == second_number:
        if first_supplier and first_supplier == second_supplier:
            return "duplicate_invoice", "duplicate: same supplier and invoice number"
        if not first_supplier or not second_supplier:
            return "possible_duplicate", "possible duplicate: same invoice number (supplier unknown)"
        return None  # two suppliers can both use "INV-001"

    # A different number, but everything else is the same: often the same paper scanned twice,
    # with the number misread once.
    same_values = all(first[name]["value"] is not None and first[name]["value"] == second[name]["value"]
                      for name in ["invoice_date", "total"])
    if same_values and first_supplier and first_supplier == second_supplier:
        return "possible_duplicate", "possible duplicate: same supplier, date and total"
    return None


def simple_key(field: dict) -> str:
    """Only letters and digits, in capitals, so "inv-001", "INV 001" and "INV001" are the same."""
    return "".join(letter for letter in (field["value"] or "").upper() if letter.isalnum())


def is_credit_note(text: str) -> bool:
    """A credit note (money given back) is allowed to have negative amounts."""
    simple = " ".join(text.lower().split())
    return "credit note" in simple or "credit memo" in simple


# ---------- small helpers ----------

def problem(field: str, rule: str, message: str) -> dict:
    return {"field": field, "rule": rule, "message": message}


def number(value: str | None) -> Decimal | None:
    """Task 2 keeps amounts as exact text ("1150.00"). Turn it into a Decimal to calculate with it."""
    return None if value is None else Decimal(value)


def money(amount: Decimal) -> str:
    return f"{amount:,.2f}"  # Decimal("1150") -> "1,150.00"


def readable(field: str) -> str:
    return field.replace("_", " ")  # "invoice_date" -> "invoice date"
