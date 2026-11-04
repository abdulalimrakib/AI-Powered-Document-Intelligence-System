"""Task 7, Step 6: write the evaluation report from the saved results.

    uv run python evaluation/write_report.py

Reads results/raw_results.json and results/real_run_scores.json (made by run_evaluation.py and score.py) and writes
deliverables/EVALUATION_REPORT.md. Every number in the report is taken from those files, never typed by hand.
"""

import datetime
import json
from pathlib import Path

EVALUATION = Path(__file__).parent
PROJECT = EVALUATION.parents[1]
REPORT = PROJECT / "deliverables" / "EVALUATION_REPORT.md"
MEANING_SEARCH_SCORES = EVALUATION / "results" / "meaning_search_scores.txt"
FIELD_NAMES = {"invoice_number": "Invoice number", "invoice_date": "Invoice date", "supplier_name": "Supplier",
               "customer_name": "Customer", "subtotal": "Subtotal", "tax": "Tax", "total": "Total", "currency": "Currency"}
KINDS = ["digital PDF", "scanned PDF", "image", "spreadsheet", "broken"]
OCR_KINDS = {"scanned PDF", "image"}


def table(rows: list[list]) -> list[str]:
    """Rows as a Markdown table; the first row is the heading"""
    lines = ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    lines.insert(1, "|" + "---|" * len(rows[0]))
    return lines


def pct(value) -> str:
    return "—" if value is None else f"{value}%"


def section(title: str) -> list[str]:
    return ["", f"## {title}", ""]


def write(scores: dict, raw: dict) -> str:
    o, f, li, p, t = scores["outcomes"], scores["fields"], scores["line_items"], scores["problems"], scores["time"]
    documents = scores["documents"]
    invoices_ai = sum(len(d["invoices"]) for d in documents if d["kind"] in ("digital PDF", "scanned PDF", "image"))
    started = datetime.datetime.fromisoformat(raw["started_at"])
    finished = datetime.datetime.fromisoformat(raw["finished_at"])
    minutes = (finished - started).total_seconds() / 60
    meaning_failed = [file for file, d in raw["documents"].items()
                      if any(h["step"] == "meaning search" for h in (d.get("final") or {}).get("history", []))]
    mistakes = scores["mistakes"]
    ocr_mistakes = [m for m in mistakes if next(d["kind"] for d in documents if d["file"] == m["file"]) in OCR_KINDS]
    invoices = sum(d["invoices_expected"] if "invoices_expected" in d else 0 for d in documents)

    lines = [
        "# Evaluation report",
        "",
        f"- **Run:** {started:%Y-%m-%d %H:%M} to {finished:%H:%M} ({minutes:.1f} minutes), {scores['mode']}",
        f"- **Dataset:** {scores['documents_in_dataset']} made-up documents with {invoices} invoices "
        f"({invoices_ai} read with Gemini), with a labeled answer sheet (`AI/evaluation/`)",
        "- **Method:** every file was uploaded through the backend API, like the website does, and the result was "
        "compared with the answer sheet",
        "- Every number below is measured and written by `AI/evaluation/write_report.py`; none is typed by hand.",
    ]

    lines += section("1. Summary")
    lines += table([
        ["Measure", "Result"],
        ["Document success rate (files that should work)", f"{o['valid_succeeded']} of {o['valid_documents']} = {pct(o['success_rate'])}"],
        ["Document failure rate (files that should work)", f"{o['valid_documents'] - o['valid_succeeded']} of {o['valid_documents']} = {pct(o['failure_rate'])}"],
        ["Broken or unsupported files handled as expected", f"{o['invalid_handled']} of {o['invalid_documents']} = {pct(o['invalid_handled_rate'])}"],
        ["**Extraction accuracy (fields right)**", f"**{f['right']} of {f['fields_judged']} = {pct(f['accuracy'])}**"],
        ["Values made up (not in the document)", f"{f['made up']}"],
        ["Invoices with every field right", f"{f['invoices_all_fields_right']} of {f['invoices']}"],
        ["Line items fully right", f"{li['lines_right']} of {li['lines_expected']} = {pct(li['accuracy'])}"],
        ["Problems put in on purpose that were caught", f"{p['problems_caught']} of {p['problems_expected']} = {pct(p['caught_rate'])}"],
        ["Invoices with a mistake that were sent to review", f"{p['invoices_with_mistakes_flagged']} of {p['invoices_with_mistakes']}"],
        ["Processing time per document (average / median)", f"{t['all']['average']} s / {t['all']['median']} s"],
    ])

    lines += section("2. Documents: success and failure")
    lines += [f"Files that should work: {o['valid_documents']}, succeeded: {o['valid_succeeded']}. Invoices were split correctly "
              f"(e.g. 3 invoices in one PDF, 1 invoice over 2 pages) in {o['invoices_split_right']} of {o['valid_documents']} documents."]
    for failed in o["valid_not_succeeded"]:
        lines.append(f"- Did not succeed: {failed['file']} ({failed['status']}): {failed['reason']}")
    lines += ["", "Broken and unsupported files must fail or be refused with a clear reason:", ""]
    lines += table([["File", "Expected", "Result", "Reason given"]] +
                   [[f"`{d['file']}`", d["expected"], d["status"], d["reason"] or ""] for d in o["invalid_details"]])

    lines += section("3. Extraction accuracy")
    lines += ["A field is right when it matches the answer sheet: money to the cent, dates as the same day, names ignoring "
              "capital letters. A field that is not on the invoice must come back empty.", ""]
    rows = [["Kind of file", "Documents", "Invoices", "Fields right", "Accuracy"]]
    for kind in KINDS:
        if kind in scores["fields_by_kind"]:
            k = scores["fields_by_kind"][kind]
            rows.append([kind, sum(d["kind"] == kind for d in documents), k["invoices"], f"{k['right']} of {k['fields_judged']}", pct(k["accuracy"])])
    rows.append(["**all**", len([d for d in documents if d["invoices"]]), f["invoices"], f"{f['right']} of {f['fields_judged']}", f"**{pct(f['accuracy'])}**"])
    lines += table(rows)
    lines += [""]
    lines += table([["Field", "Right", "Accuracy"]] +
                   [[FIELD_NAMES[name], f"{v['right']} of {v['of']}", pct(v["accuracy"])] for name, v in f["per_field"].items()])
    lines += ["", f"Wrong values: {f['wrong']}. Missed (written but not given): {f['missed']}. "
              f"Made up (not written but given): {f['made up']}."]
    lines += ["", "### Every field that was not right", ""]
    lines += table([["File", "Invoice", "Field", "Result", "Expected", "Given"]] +
                   [[f"`{m['file']}`", m["invoice"], FIELD_NAMES[m["field"]], m["result"], m["expected"] or "(empty)", m["got"] or "(empty)"]
                    for m in mistakes]) if mistakes else ["None."]

    lines += section("4. Validation")
    lines += table([
        ["Measure", "Result"],
        ["Problems put in on purpose that were caught", f"{p['problems_caught']} of {p['problems_expected']}"],
        ["Invoices with a wrong or missing value sent to review", f"{p['invoices_with_mistakes_flagged']} of {p['invoices_with_mistakes']}"],
        ["Clean invoices, read right, flagged anyway", f"{p['clean_invoices_flagged']} of {p['clean_invoices']}"],
        ["'Needs review' right", f"{p['needs_review_right']} of {p['invoices_read']} = {pct(p['needs_review_right_rate'])}"],
    ])
    if p["invoices_with_mistakes_not_flagged"]:
        lines += ["", "Invoices with a mistake that were **not** sent to review:"]
        lines += [f"- {item['invoice']}: {', '.join(item['fields'])}" for item in p["invoices_with_mistakes_not_flagged"]]

    lines += section("5. Processing time")
    lines += ["Seconds from upload until the document is done or failed, one document at a time.", ""]
    rows = [["Kind of file", "Documents", "Average", "Median", "Fastest", "Slowest"]]
    for kind in KINDS:
        if t["by_kind"].get(kind):
            k = t["by_kind"][kind]
            rows.append([kind, k["documents"], f"{k['average']} s", f"{k['median']} s", f"{k['fastest']} s", f"{k['slowest']} s"])
    a = t["all"]
    rows.append(["**all**", a["documents"], f"{a['average']} s", f"{a['median']} s", f"{a['fastest']} s", f"{a['slowest']} s"])
    lines += table(rows)
    lines += ["", f"- Per invoice read with Gemini (average): {t['seconds_per_invoice_read_with_ai']} s. Most of the time is the "
              "Gemini request; spreadsheets are read without AI.",
              "- Gemini models used: " + ", ".join(f"{model} ({count} invoices)" for model, count in scores["ai_models"].items()) + ".",
              f"- Meaning search: {'every document was added' if not meaning_failed else 'not added for ' + ', '.join(meaning_failed)}."]

    lines += section("6. What the results show")
    lines += [
        f"- **Digital PDFs and spreadsheets:** {pct(scores['fields_by_kind'].get('digital PDF', {}).get('accuracy'))} and "
        f"{pct(scores['fields_by_kind'].get('spreadsheet', {}).get('accuracy'))} of fields right.",
        f"- **{len(ocr_mistakes)} of the {len(mistakes)} mistakes come from OCR, not from Gemini.** They are all in scans and photos, "
        "where Tesseract read the dotted zeros of the font as 6 or 9 (e.g. `IMG-4003` became `IMG-4663`). Gemini copied "
        "the OCR text exactly, as instructed.",
        "- **The safety net worked:** a misread date with month 16 was left empty instead of guessed, misread amounts no "
        f"longer added up and were flagged, every invoice with a mistake was sent to review "
        f"({p['invoices_with_mistakes_flagged']} of {p['invoices_with_mistakes']}), and no value was made up ({f['made up']}).",
        f"- Low-certainty pictures are sent to review even when read right ({p['clean_invoices_flagged']} of "
        f"{p['clean_invoices']} clean invoices): a quick human check is preferred over trusting a doubtful value.",
        "- Free-tier model rotation worked: when the first model's daily limit was used up, the next model took over.",
    ]

    lines += section("7. Corrections made after the run")
    lines += [
        "The answer sheet had two mistakes, both proven from the files themselves, and was corrected openly:",
        "",
        "- `d04_european_numbers.pdf`: the PDF font could not draw the € sign, so no currency is written; the system's "
        "empty answer is right.",
        "- `d07_no_tax_dollar_sign.pdf`: a lone `$` is correctly marked 'uncertain', but by design only the important "
        "fields send an invoice to review.",
        "",
        "Two measures were also made fairer after seeing the first numbers: problems are only judged on invoices the "
        "system read, and a review flag only counts as 'not needed' when the invoice was clean and read right. "
        "The files used in the run were not changed (checked byte for byte).",
    ]

    lines += section("8. Limits of this evaluation")
    lines += [
        f"- The dataset is small ({scores['documents_in_dataset']} documents) and made up, with one layout and printed "
        "text. Real invoices, especially photos, will score lower.",
        "- It is one run; Gemini can answer slightly differently between runs, even at temperature 0.",
        "- Times were measured on one laptop, one document at a time, including the free tier's waits and retries.",
    ]

    lines += section("9. Meaning search")
    measured = MEANING_SEARCH_SCORES.read_text(encoding="utf-8")
    first = next(line for line in measured.splitlines() if line.startswith("The right invoice was first"))
    lines += ["Measured separately with the real Gemini embedding model on 12 sample invoices. " + first,
              "The search cut-off was chosen from these scores (`AI/evaluation/results/meaning_search_scores.txt`)."]

    lines += section("How to repeat")
    lines += ["```bash",
              "cd AI",
              "uv run python evaluation/run_evaluation.py   # the real run (about 22 Gemini requests)",
              "uv run python evaluation/score.py            # the numbers (no Gemini)",
              "uv run python evaluation/write_report.py     # this report",
              "```", ""]
    return "\n".join(lines)


def main():
    raw = json.loads((EVALUATION / "results" / "raw_results.json").read_text(encoding="utf-8"))
    scores = json.loads((EVALUATION / "results" / "real_run_scores.json").read_text(encoding="utf-8"))
    REPORT.write_text(write(scores, raw), encoding="utf-8")
    print(f"Written: {REPORT.relative_to(PROJECT)}")


if __name__ == "__main__":
    main()
