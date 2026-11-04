"""Step 4 — Scoring the evaluation: comparing the system's answers with the answer sheet"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "evaluation"))
from score import judge, same_line, score  # noqa: E402

RIGHT = {"invoice_number": "INV-1", "invoice_date": "2026-10-15", "supplier_name": "Acme Ltd", "customer_name": "Blue Sky Foods",
         "subtotal": "1000.00", "tax": "150.00", "total": "1150.00", "currency": "USD"}
LINE = {"description": "Office chairs", "quantity": "10", "unit_price": "100.00", "amount": "1000.00"}


def label(file="a.pdf", kind="digital PDF", expected="done", fields=None, lines=(LINE,), problems=()):
    invoices = [] if expected != "done" else [{"fields": {**RIGHT, **(fields or {})}, "line_items": list(lines), "expected_problems": list(problems)}]
    return {"file": file, "kind": kind, "expected": expected, "note": "", "invoices": invoices}


def system_invoice(fields=None, lines=(LINE,), rules=(), error=None, model="gemini-test"):
    values = {**RIGHT, **(fields or {})}
    return {"fields": {name: {"value": value} for name, value in values.items()}, "line_items": list(lines),
            "validation_errors": [{"rule": rule} for rule in rules], "needs_review": bool(rules), "error": error, "ai_model": model}


def outcome(status="done", invoices=None, seconds=4.0, reason=None):
    result = {"status": status, "wall_seconds": seconds, "processing_seconds": str(seconds)}
    if status == "refused":
        return {**result, "reason": reason, "document_id": None}
    return {**result, "document_id": 1, "final": {"error": reason, "invoices": invoices if invoices is not None else [system_invoice()]}}


def run(labels: list[dict], outcomes: dict) -> dict:
    return score({"documents": labels}, {"mode": "test", "documents": outcomes})


# ---------- one value ----------

@pytest.mark.parametrize("field, expected, got, result", [
    pytest.param("total", "1150.00", "1150.00", "right", id="the same amount"),
    pytest.param("total", "1150.00", "1150.0", "right", id="the same amount written differently"),
    pytest.param("total", "1150.00", "1150.01", "wrong", id="one cent off"),
    pytest.param("supplier_name", "Acme Ltd", "  ACME   LTD. ", "right", id="name with other capitals and spaces"),
    pytest.param("supplier_name", "Müller & Söhne KG", "Muller & Sohne KG", "wrong", id="name without its accents"),
    pytest.param("invoice_number", "INV-1", "inv-1", "right", id="number in small letters"),
    pytest.param("invoice_number", "INV-1", "INV-7", "wrong", id="another number"),
    pytest.param("invoice_date", "2026-10-15", None, "missed", id="written but not given"),
    pytest.param("customer_name", None, "Blue Sky Foods", "made up", id="not written but given"),
    pytest.param("customer_name", None, None, "right", id="not written and not given"),
])
def test_judges_one_value(field, expected, got, result):
    """Judges one value as right, wrong, missed or made up"""
    assert judge(field, expected, got) == result


def test_a_line_item_is_right_only_when_all_its_parts_are_right():
    """A line item is right only when its description, quantity, unit price and amount are all right"""
    assert same_line(LINE, {**LINE, "quantity": "10.0"})
    assert not same_line(LINE, {**LINE, "amount": "1100.00"})
    assert not same_line(LINE, {**LINE, "description": "Office tables"})


# ---------- a whole run ----------

def test_a_perfect_run_scores_100_percent():
    """When every answer is right, every score is 100% and nothing is listed as a mistake"""
    scores = run([label()], {"a.pdf": outcome()})

    assert scores["fields"]["accuracy"] == 100.0
    assert scores["line_items"]["accuracy"] == 100.0
    assert scores["outcomes"]["success_rate"] == 100.0
    assert scores["outcomes"]["failure_rate"] == 0.0
    assert scores["mistakes"] == []


def test_counts_wrong_missed_and_made_up_fields():
    """Counts wrong, missed and made-up fields, and lists each mistake with what was expected"""
    scores = run([label(fields={"customer_name": None})],
                 {"a.pdf": outcome(invoices=[system_invoice(fields={"total": "1180.00", "tax": None, "customer_name": "Someone"})])})

    fields = scores["fields"]
    assert (fields["right"], fields["wrong"], fields["missed"], fields["made up"]) == (5, 1, 1, 1)
    assert fields["accuracy"] == 62.5  # 5 of 8
    assert fields["per_field"]["total"] == {"right": 0, "of": 1, "accuracy": 0.0}
    total = next(mistake for mistake in scores["mistakes"] if mistake["field"] == "total")
    assert (total["file"], total["result"], total["expected"], total["got"]) == ("a.pdf", "wrong", "1150.00", "1180.00")
    assert len(scores["mistakes"]) == 3


def test_a_document_with_a_failed_invoice_does_not_count_as_a_success():
    """A document counts as a success only when it is done and none of its invoices failed"""
    two = label(file="two.pdf")
    two["invoices"] *= 2
    scores = run([two], {"two.pdf": outcome(invoices=[system_invoice(), system_invoice(fields=dict.fromkeys(RIGHT), error="Gemini is busy")])})

    assert scores["outcomes"]["success_rate"] == 0.0
    assert scores["outcomes"]["valid_not_succeeded"] == [{"file": "two.pdf", "status": "done", "reason": "Gemini is busy"}]
    assert scores["fields"]["missed"] == 8  # the failed invoice's fields


def test_broken_files_are_counted_apart_from_the_files_that_should_work():
    """Broken and unsupported files are counted apart: failing them correctly is not a failure of the system"""
    labels = [label(), label(file="bad.pdf", kind="broken", expected="failed"), label(file="x.docx", kind="unsupported", expected="refused")]
    scores = run(labels, {"a.pdf": outcome(), "bad.pdf": outcome(status="failed", invoices=[], reason="damaged"),
                          "x.docx": outcome(status="refused", reason="not supported")})

    o = scores["outcomes"]
    assert (o["valid_documents"], o["success_rate"]) == (1, 100.0)
    assert (o["invalid_documents"], o["invalid_handled"]) == (2, 2)
    assert o["all_as_expected_rate"] == 100.0


def test_a_broken_file_that_is_accepted_is_not_handled_as_expected():
    """A broken file that the system 'reads' anyway is not counted as handled correctly"""
    scores = run([label(file="bad.pdf", kind="broken", expected="failed")], {"bad.pdf": outcome(invoices=[])})

    assert scores["outcomes"]["invalid_handled"] == 0


def test_counts_problems_caught_and_clean_invoices_flagged_by_mistake():
    """Counts the problems that were caught, and the clean invoices that were flagged by mistake"""
    labels = [label(file="wrong.pdf", problems=["totals_match"]), label(file="clean.pdf"), label(file="missed.pdf", problems=["line_math"])]
    scores = run(labels, {"wrong.pdf": outcome(invoices=[system_invoice(rules=["totals_match"])]),
                          "clean.pdf": outcome(invoices=[system_invoice(rules=["missing_field"])]),
                          "missed.pdf": outcome(invoices=[system_invoice()])})

    problems = scores["problems"]
    assert (problems["problems_caught"], problems["problems_expected"]) == (1, 2)
    assert (problems["clean_invoices_flagged"], problems["clean_invoices"]) == (1, 1)
    assert problems["unexpected_problems"] == [{"invoice": "INV-1", "rules": ["missing_field"]}]


def test_problems_are_only_judged_on_invoices_the_system_read():
    """An invoice that failed has nothing to check, so it doesn't count for the problems caught"""
    scores = run([label(problems=["totals_match"])], {"a.pdf": outcome(status="failed", invoices=[], reason="Gemini is busy")})

    assert scores["problems"]["invoices_read"] == 0
    assert scores["problems"]["problems_expected"] == 0


def test_measures_the_time_per_document():
    """Measures the time per document: average, median, slowest, and per kind of file"""
    labels = [label(file=f"{n}.pdf") for n in range(3)] + [label(file="s.csv", kind="spreadsheet")]
    scores = run(labels, {"0.pdf": outcome(seconds=2.0), "1.pdf": outcome(seconds=4.0), "2.pdf": outcome(seconds=9.0), "s.csv": outcome(seconds=0.2)})

    time = scores["time"]
    assert time["by_kind"]["digital PDF"] == {"documents": 3, "average": 5.0, "median": 4.0, "fastest": 2.0, "slowest": 9.0}
    assert time["slowest"][0] == {"file": "2.pdf", "seconds": 9.0}
    assert time["seconds_per_invoice_read_with_ai"] == 5.0


def test_a_document_not_run_yet_is_left_out():
    """A document that was not run yet (e.g. the daily limit) is left out of every number, not counted as failed"""
    scores = run([label(), label(file="later.pdf")], {"a.pdf": outcome()})

    assert (scores["documents_run"], scores["documents_in_dataset"]) == (1, 2)
    assert scores["outcomes"]["success_rate"] == 100.0


def test_a_split_into_too_few_invoices_counts_the_missing_ones_as_missed():
    """When a PDF with 2 invoices is read as 1, the second one's fields count as missed"""
    two = label(file="two.pdf")
    two["invoices"] = [two["invoices"][0], {**two["invoices"][0], "fields": {**RIGHT, "invoice_number": "INV-2"}}]
    scores = run([two], {"two.pdf": outcome(invoices=[system_invoice()])})

    assert scores["outcomes"]["invoices_split_right"] == 0
    assert scores["fields"]["missed"] == 8


def test_counts_the_invoices_with_mistakes_that_were_sent_to_review():
    """Counts how many invoices with a wrong or missing value were sent to review (the safety net)"""
    labels = [label(file="flagged.pdf"), label(file="silent.pdf"), label(file="right.pdf")]
    scores = run(labels, {"flagged.pdf": outcome(invoices=[system_invoice(fields={"total": "1180.00"}, rules=["totals_match"])]),
                          "silent.pdf": outcome(invoices=[system_invoice(fields={"customer_name": "Someone Else"})]),
                          "right.pdf": outcome()})

    problems = scores["problems"]
    assert (problems["invoices_with_mistakes_flagged"], problems["invoices_with_mistakes"]) == (1, 2)
    assert problems["invoices_with_mistakes_not_flagged"] == [{"invoice": "INV-1", "fields": ["customer_name"]}]


def test_a_review_flag_is_only_counted_as_not_needed_when_everything_was_read_right():
    """A flag on a clean invoice that was misread is right; only a flag on a clean, correctly read invoice was not needed"""
    labels = [label(file="misread.pdf"), label(file="read-right.pdf")]
    scores = run(labels, {"misread.pdf": outcome(invoices=[system_invoice(fields={"total": "1180.00"}, rules=["totals_match"])]),
                          "read-right.pdf": outcome(invoices=[system_invoice(rules=["uncertain_value"])])})

    problems = scores["problems"]
    assert (problems["clean_invoices_flagged"], problems["clean_invoices"]) == (1, 1)
    assert problems["clean_invoices_flagged_list"] == [{"invoice": "INV-1", "rules": ["uncertain_value"]}]
    assert problems["needs_review_right"] == 1  # the misread one rightly needs review; the other did not need it
