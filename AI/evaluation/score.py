"""Task 7, Step 4: turn the saved results of the evaluation into numbers.

    uv run python evaluation/score.py                            # scores the real run (results/raw_results.json)
    uv run python evaluation/score.py results/practice_run.json  # scores the practice run

Compares what the system gave (saved by run_evaluation.py) with the answer sheet (labels.json) and writes
results/<name>_scores.json, plus a short summary on the screen. It never calls Gemini or the system, so it can be
run as often as you like.

How a field is judged:
- right:    the same value (money to the cent; names ignoring capital letters, extra spaces and a final dot)
- wrong:    a different value
- missed:   the value is written on the invoice, but the system gave nothing
- made up:  nothing is written on the invoice, but the system gave a value (must stay 0)
"""

import json
import statistics
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

EVALUATION = Path(__file__).parent
FIELDS = ["invoice_number", "invoice_date", "supplier_name", "customer_name", "subtotal", "tax", "total", "currency"]
MONEY = {"subtotal", "tax", "total"}
NAMES = {"supplier_name", "customer_name"}
READ_WITH_AI = {"digital PDF", "scanned PDF", "image"}


# ---------- comparing one value ----------

def same_value(field: str, expected: str | None, got: str | None) -> bool:
    if expected is None or got is None:
        return expected is None and got is None
    if field in MONEY:
        return as_number(expected) == as_number(got)
    if field in NAMES:
        return simple_name(expected) == simple_name(got)
    if field == "invoice_number":
        return expected.strip().upper() == got.strip().upper()
    return expected == got


def as_number(text: str) -> Decimal | None:
    try:
        return Decimal(text)
    except (InvalidOperation, TypeError):
        return None


def simple_name(text: str) -> str:
    """ "  ACME  Ltd." -> "acme ltd" """
    return " ".join(text.split()).rstrip(".").lower()


def judge(field: str, expected: str | None, got: str | None) -> str:
    """right, wrong, missed or made up"""
    if same_value(field, expected, got):
        return "right"
    if got is None:
        return "missed"
    if expected is None:
        return "made up"
    return "wrong"


def same_line(expected: dict, got: dict) -> bool:
    """A line item is right when its description, quantity, unit price and amount are all right"""
    return (simple_name(expected["description"] or "") == simple_name(got.get("description") or "")
            and all(as_number(expected[key]) is not None and as_number(expected[key]) == as_number(got.get(key) or "")
                    for key in ("quantity", "unit_price", "amount")))


# ---------- one invoice ----------

def score_invoice(expected: dict, got: dict | None) -> dict:
    """Compare one labeled invoice with what the system gave (None = the system found no invoice for it)."""
    got = got or {"fields": {}, "line_items": [], "validation_errors": [], "needs_review": False, "error": "not found by the system"}
    values = {field: (got["fields"].get(field) or {}).get("value") for field in FIELDS}
    fields = {field: judge(field, expected["fields"][field], values[field]) for field in FIELDS}

    expected_lines = expected["line_items"]
    got_lines = got["line_items"]
    right_lines = sum(same_line(want, have) for want, have in zip(expected_lines, got_lines))

    expected_problems = set(expected["expected_problems"])
    found_problems = {error["rule"] for error in got["validation_errors"]}
    return {
        "fields": fields,
        "values": {field: {"expected": expected["fields"][field], "got": values[field]} for field in FIELDS},
        "lines_expected": len(expected_lines),
        "lines_got": len(got_lines),
        "lines_right": right_lines,
        "problems_expected": sorted(expected_problems),
        "problems_found": sorted(found_problems),
        "problems_caught": sorted(expected_problems & found_problems),
        "problems_not_expected": sorted(found_problems - expected_problems),
        "should_need_review": bool(expected_problems),
        "needs_review": got["needs_review"],
        "ai_model": got.get("ai_model"),
        "error": got.get("error"),
    }


# ---------- the whole run ----------

def score(labels: dict, raw: dict) -> dict:
    documents = []
    for label in labels["documents"]:
        outcome = raw["documents"].get(label["file"])
        if outcome is None:
            documents.append({"file": label["file"], "kind": label["kind"], "expected": label["expected"], "status": "not run"})
            continue
        final = outcome.get("final") or {}
        got_invoices = final.get("invoices", [])
        invoices = [score_invoice(expected, got_invoices[index] if index < len(got_invoices) else None)
                    for index, expected in enumerate(label["invoices"])]
        documents.append({
            "file": label["file"], "kind": label["kind"], "expected": label["expected"], "note": label["note"],
            "status": outcome["status"],
            "reason": outcome.get("reason") or final.get("error"),
            "invoice_errors": [invoice["error"] for invoice in got_invoices if invoice.get("error")],
            "invoices_expected": len(label["invoices"]),
            "invoices_got": len(got_invoices),
            "wall_seconds": outcome.get("wall_seconds"),
            "processing_seconds": float(outcome["processing_seconds"]) if outcome.get("processing_seconds") else None,
            "invoices": invoices,
        })
    run = [document for document in documents if document["status"] != "not run"]
    return {
        "mode": raw.get("mode"), "started_at": raw.get("started_at"), "finished_at": raw.get("finished_at"),
        "documents_in_dataset": len(documents), "documents_run": len(run),
        "outcomes": outcomes(run),
        "fields": field_scores(run),
        "fields_by_kind": {kind: field_scores([d for d in run if d["kind"] == kind]) for kind in sorted({d["kind"] for d in run if d["invoices"]})},
        "line_items": line_scores(run),
        "problems": problem_scores(run),
        "time": time_scores(run),
        "ai_models": model_counts(run),
        "mistakes": mistakes(run),
        "documents": documents,
    }


def percent(part: int, whole: int) -> float | None:
    return round(part / whole * 100, 1) if whole else None


def outcomes(run: list[dict]) -> dict:
    """Document success and failure rates. A document succeeds when it is done and none of its invoices failed."""
    def fully_done(document):
        return document["status"] == "done" and not document["invoice_errors"]

    valid = [document for document in run if document["expected"] == "done"]  # files that should work
    invalid = [document for document in run if document["expected"] != "done"]  # broken or unsupported files
    succeeded = [document for document in valid if fully_done(document)]
    handled = [document for document in invalid if document["status"] == document["expected"]]
    all_succeeded_or_handled = len(succeeded) + len(handled)
    return {
        "valid_documents": len(valid),
        "valid_succeeded": len(succeeded),
        "success_rate": percent(len(succeeded), len(valid)),
        "failure_rate": percent(len(valid) - len(succeeded), len(valid)),
        "valid_not_succeeded": [{"file": d["file"], "status": d["status"], "reason": d["reason"] or "; ".join(d["invoice_errors"])}
                                for d in valid if not fully_done(d)],
        "invalid_documents": len(invalid),
        "invalid_handled": len(handled),
        "invalid_handled_rate": percent(len(handled), len(invalid)),
        "invalid_details": [{"file": d["file"], "expected": d["expected"], "status": d["status"], "reason": d["reason"]} for d in invalid],
        "all_documents": len(run),
        "all_as_expected_rate": percent(all_succeeded_or_handled, len(run)),
        "invoices_split_right": sum(d["invoices_got"] == d["invoices_expected"] for d in valid),
    }


def field_scores(run: list[dict]) -> dict:
    """How many fields were right, wrong, missed or made up; overall and per field."""
    judged = [(field, result) for document in run for invoice in document["invoices"] for field, result in invoice["fields"].items()]
    counts = {result: sum(1 for _, r in judged if r == result) for result in ("right", "wrong", "missed", "made up")}
    per_field = {}
    for field in FIELDS:
        results = [r for f, r in judged if f == field]
        per_field[field] = {"right": results.count("right"), "of": len(results), "accuracy": percent(results.count("right"), len(results))}
    return {"fields_judged": len(judged), **counts, "accuracy": percent(counts["right"], len(judged)),
            "invoices": sum(len(d["invoices"]) for d in run),
            "invoices_all_fields_right": sum(all(r == "right" for r in i["fields"].values()) for d in run for i in d["invoices"]),
            "per_field": per_field}


def line_scores(run: list[dict]) -> dict:
    invoices = [invoice for document in run for invoice in document["invoices"] if invoice["lines_expected"]]
    expected = sum(invoice["lines_expected"] for invoice in invoices)
    right = sum(invoice["lines_right"] for invoice in invoices)
    return {"lines_expected": expected, "lines_right": right, "accuracy": percent(right, expected),
            "invoices_with_right_line_count": sum(i["lines_got"] == i["lines_expected"] for i in invoices), "invoices": len(invoices)}


def problem_scores(run: list[dict]) -> dict:
    """Did the checks find the problems put in on purpose, and did they complain about clean invoices?
    Only invoices the system really read count here: an invoice that failed or was not found has nothing to check."""
    invoices = [invoice for document in run for invoice in document["invoices"] if not invoice["error"]]
    expected = sum(len(invoice["problems_expected"]) for invoice in invoices)
    caught = sum(len(invoice["problems_caught"]) for invoice in invoices)
    # An invoice should be sent to review when it has a problem on purpose OR a value was read wrong
    review_right = sum(invoice["needs_review"] == (invoice["should_need_review"] or not all_right(invoice)) for invoice in invoices)
    unexpected = [{"invoice": invoice["values"]["invoice_number"]["expected"], "rules": invoice["problems_not_expected"]}
                  for invoice in invoices if invoice["problems_not_expected"]]
    # The safety net: an invoice with a wrong or missing value should at least be sent to a person (needs review)
    with_mistakes = [invoice for invoice in invoices if any(result != "right" for result in invoice["fields"].values())]
    not_flagged = [{"invoice": invoice["values"]["invoice_number"]["expected"],
                    "fields": [field for field, result in invoice["fields"].items() if result != "right"]}
                   for invoice in with_mistakes if not invoice["needs_review"]]
    return {"invoices_read": len(invoices),
            "problems_expected": expected, "problems_caught": caught, "caught_rate": percent(caught, expected),
            # "Clean" = no problem on purpose AND every value read right: then a review flag was not needed
            "clean_invoices": len(clean := [i for i in invoices if not i["should_need_review"] and all_right(i)]),
            "clean_invoices_flagged": sum(i["needs_review"] for i in clean),
            "clean_invoices_flagged_list": [{"invoice": i["values"]["invoice_number"]["expected"], "rules": i["problems_found"]}
                                            for i in clean if i["needs_review"]],
            "needs_review_right": review_right, "needs_review_right_rate": percent(review_right, len(invoices)),
            "unexpected_problems": unexpected,
            "invoices_with_mistakes": len(with_mistakes), "invoices_with_mistakes_flagged": len(with_mistakes) - len(not_flagged),
            "invoices_with_mistakes_not_flagged": not_flagged}


def all_right(invoice: dict) -> bool:
    return all(result == "right" for result in invoice["fields"].values())


def time_scores(run: list[dict]) -> dict:
    """Seconds from upload until done or failed (as a user waits), per kind of file."""
    def stats(documents):
        seconds = [d["wall_seconds"] for d in documents if d["wall_seconds"] is not None and d["status"] != "refused"]
        if not seconds:
            return None
        return {"documents": len(seconds), "average": round(statistics.mean(seconds), 2), "median": round(statistics.median(seconds), 2),
                "fastest": min(seconds), "slowest": max(seconds)}

    processed = [d for d in run if d["status"] != "refused"]
    slowest = sorted(processed, key=lambda d: d["wall_seconds"] or 0, reverse=True)[:3]
    per_invoice = [d["wall_seconds"] / d["invoices_got"] for d in processed if d["kind"] in READ_WITH_AI and d["invoices_got"] and d["status"] == "done"]
    return {"all": stats(processed), "by_kind": {kind: stats([d for d in processed if d["kind"] == kind]) for kind in sorted({d["kind"] for d in processed})},
            "seconds_per_invoice_read_with_ai": round(statistics.mean(per_invoice), 2) if per_invoice else None,
            "slowest": [{"file": d["file"], "seconds": d["wall_seconds"]} for d in slowest]}


def model_counts(run: list[dict]) -> dict:
    counts = {}
    for document in run:
        for invoice in document["invoices"]:
            if invoice["ai_model"]:
                counts[invoice["ai_model"]] = counts.get(invoice["ai_model"], 0) + 1
    return counts


def mistakes(run: list[dict]) -> list[dict]:
    """Every field that was not right: what was expected and what the system gave"""
    found = []
    for document in run:
        for invoice in document["invoices"]:
            for field, result in invoice["fields"].items():
                if result != "right":
                    found.append({"file": document["file"], "invoice": invoice["values"]["invoice_number"]["expected"], "field": field,
                                  "result": result, **invoice["values"][field]})
    return found


# ---------- on the screen ----------

def summary(scores: dict) -> str:
    o, f, p, t, li = scores["outcomes"], scores["fields"], scores["problems"], scores["time"], scores["line_items"]
    lines = [
        f"{scores['mode']}: {scores['documents_run']} of {scores['documents_in_dataset']} documents",
        f"Documents that should work: {o['valid_succeeded']} of {o['valid_documents']} succeeded "
        f"(success rate {o['success_rate']}%, failure rate {o['failure_rate']}%)",
        f"Broken or unsupported files handled as expected: {o['invalid_handled']} of {o['invalid_documents']}",
        f"Fields right: {f['right']} of {f['fields_judged']} ({f['accuracy']}%), wrong {f['wrong']}, missed {f['missed']}, made up {f['made up']}",
        f"Line items right: {li['lines_right']} of {li['lines_expected']} ({li['accuracy']}%)",
        f"Problems caught (in the {p['invoices_read']} invoices read): {p['problems_caught']} of {p['problems_expected']}; "
        f"clean invoices (no problem, read right) flagged anyway: "
        f"{p['clean_invoices_flagged']} of {p['clean_invoices']}",
        f"Invoices with a wrong or missing value that were sent to review: {p['invoices_with_mistakes_flagged']} of {p['invoices_with_mistakes']}",
    ]
    if t["all"]:
        lines.append(f"Time per document: average {t['all']['average']} s, median {t['all']['median']} s, slowest {t['all']['slowest']} s")
    return "\n".join(lines)


def main():
    raw_file = Path(sys.argv[1]) if len(sys.argv) > 1 else EVALUATION / "results" / "raw_results.json"
    if not raw_file.is_absolute() and not raw_file.exists():
        raw_file = EVALUATION / raw_file
    labels = json.loads((EVALUATION / "labels.json").read_text(encoding="utf-8"))
    scores = score(labels, json.loads(raw_file.read_text(encoding="utf-8")))
    scores_file = raw_file.with_name(raw_file.stem.replace("raw_results", "real_run") + "_scores.json")
    scores_file.write_text(json.dumps(scores, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(summary(scores))
    print(f"\nSaved in {scores_file}")


if __name__ == "__main__":
    main()
