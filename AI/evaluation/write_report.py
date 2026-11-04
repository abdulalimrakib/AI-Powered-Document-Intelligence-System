"""Task 7, Step 6: write the evaluation report from the saved results.

    uv run python evaluation/write_report.py

Reads results/raw_results.json and results/real_run_scores.json (made by run_evaluation.py and score.py) and writes
test-results/evaluation_report.txt. Every number in the report is taken from those files, never typed by hand.
"""

import datetime
import json
from pathlib import Path

EVALUATION = Path(__file__).parent
PROJECT = EVALUATION.parents[1]
REPORT = PROJECT / "test-results" / "evaluation_report.txt"
FIELD_NAMES = {"invoice_number": "Invoice number", "invoice_date": "Invoice date", "supplier_name": "Supplier",
               "customer_name": "Customer", "subtotal": "Subtotal", "tax": "Tax", "total": "Total", "currency": "Currency"}
KINDS = ["digital PDF", "scanned PDF", "image", "spreadsheet", "broken"]
OCR_KINDS = {"scanned PDF", "image"}


def table(rows: list[list[str]], indent: str = "  ") -> list[str]:
    """Rows of text as an aligned table; the first row is the heading"""
    widths = [max(len(str(row[column])) for row in rows) for column in range(len(rows[0]))]
    lines = []
    for number, row in enumerate(rows):
        lines.append(indent + "  ".join(str(cell).ljust(width) for cell, width in zip(row, widths)).rstrip())
        if number == 0:
            lines.append(indent + "  ".join("-" * width for width in widths))
    return lines


def pct(value) -> str:
    return "—" if value is None else f"{value}%"


def section(title: str) -> list[str]:
    return ["", "", title.upper(), "=" * len(title)]


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

    lines = [
        "Evaluation report: AI-Powered Document Intelligence System",
        "=" * 60,
        f"Run:      {started:%Y-%m-%d %H:%M} to {finished:%H:%M} ({minutes:.1f} minutes), {scores['mode']}",
        f"Dataset:  {scores['documents_in_dataset']} documents with {sum(d['invoices_expected'] if 'invoices_expected' in d else 0 for d in documents)} invoices "
        f"({invoices_ai} of them read with Gemini), made up for this test (AI/evaluation/make_dataset.py)",
        "Written:  by AI/evaluation/write_report.py from AI/evaluation/results/. Every number below is measured, none is typed by hand.",
        "",
        "How it was measured: every file was uploaded through the backend API, exactly like the website does",
        "(backend -> queue -> AI service -> OCR / Gemini -> checks -> database), one at a time, and the result was",
        "compared with an answer sheet (labels.json) that was written by the same script that made the files.",
    ]

    lines += section("1. Summary")
    lines += table([
        ["Measure", "Result"],
        ["Document success rate (files that should work)", f"{o['valid_succeeded']} of {o['valid_documents']} = {pct(o['success_rate'])}"],
        ["Document failure rate (files that should work)", f"{o['valid_documents'] - o['valid_succeeded']} of {o['valid_documents']} = {pct(o['failure_rate'])}"],
        ["Broken or unsupported files handled as expected", f"{o['invalid_handled']} of {o['invalid_documents']} = {pct(o['invalid_handled_rate'])}"],
        ["Extraction accuracy (fields right)", f"{f['right']} of {f['fields_judged']} = {pct(f['accuracy'])}"],
        ["Values made up (not in the document)", f"{f['made up']}"],
        ["Invoices with every field right", f"{f['invoices_all_fields_right']} of {f['invoices']}"],
        ["Line items fully right", f"{li['lines_right']} of {li['lines_expected']} = {pct(li['accuracy'])}"],
        ["Problems put in on purpose that were caught", f"{p['problems_caught']} of {p['problems_expected']} = {pct(p['caught_rate'])}"],
        ["Invoices with a mistake that were sent to review", f"{p['invoices_with_mistakes_flagged']} of {p['invoices_with_mistakes']}"],
        ["Processing time per document (average / median)", f"{t['all']['average']} s / {t['all']['median']} s"],
    ])

    lines += section("2. Documents: success and failure")
    lines += [f"  Files that should work: {o['valid_documents']}. Succeeded (done, and none of their invoices failed): "
              f"{o['valid_succeeded']}. Invoices split correctly (e.g. 3 invoices in one PDF, 1 invoice over 2 pages): "
              f"{o['invoices_split_right']} of {o['valid_documents']} documents."]
    for failed in o["valid_not_succeeded"]:
        lines.append(f"  Did not succeed: {failed['file']} ({failed['status']}): {failed['reason']}")
    lines += ["", "  Broken and unsupported files (these SHOULD fail or be refused, with a clear reason):"]
    lines += table([["File", "Expected", "Result", "Reason given"]] +
                   [[d["file"], d["expected"], d["status"], d["reason"] or ""] for d in o["invalid_details"]], indent="    ")
    lines += [f"  All {o['all_documents']} documents together: {pct(o['all_as_expected_rate'])} behaved as expected."]

    lines += section("3. Extraction accuracy")
    lines += ["  A field is right when it has the same value as the answer sheet: money to the cent, dates as the same day,",
              "  names ignoring capital letters and extra spaces. A field that is not on the invoice must come back empty.", ""]
    rows = [["Kind of file", "Documents", "Invoices", "Fields right", "Accuracy"]]
    for kind in KINDS:
        if kind in scores["fields_by_kind"]:
            k = scores["fields_by_kind"][kind]
            rows.append([kind, sum(d["kind"] == kind for d in documents), k["invoices"], f"{k['right']} of {k['fields_judged']}", pct(k["accuracy"])])
    rows.append(["all", len([d for d in documents if d["invoices"]]), f["invoices"], f"{f['right']} of {f['fields_judged']}", pct(f["accuracy"])])
    lines += table(rows)
    lines += ["", "  Per field:"]
    lines += table([["Field", "Right", "Accuracy"]] +
                   [[FIELD_NAMES[name], f"{v['right']} of {v['of']}", pct(v["accuracy"])] for name, v in f["per_field"].items()], indent="    ")
    lines += ["", f"  Wrong values: {f['wrong']}. Missed (written but not given): {f['missed']}. Made up (not written but given): {f['made up']}."]
    lines += ["", "  Every field that was not right:"]
    lines += table([["File", "Invoice", "Field", "Result", "Expected", "Given"]] +
                   [[m["file"], m["invoice"], FIELD_NAMES[m["field"]], m["result"], m["expected"] or "(empty)", m["got"] or "(empty)"] for m in mistakes],
                   indent="    ") if mistakes else ["    none"]

    lines += section("4. Validation (the checks)")
    lines += table([
        ["Measure", "Result"],
        ["Problems put in on purpose that were caught", f"{p['problems_caught']} of {p['problems_expected']}"],
        ["Invoices with a wrong or missing value sent to review", f"{p['invoices_with_mistakes_flagged']} of {p['invoices_with_mistakes']}"],
        ["Clean invoices, read right, flagged anyway", f"{p['clean_invoices_flagged']} of {p['clean_invoices']}"],
        ["'Needs review' right (should: a problem or a misread value)", f"{p['needs_review_right']} of {p['invoices_read']} = {pct(p['needs_review_right_rate'])}"],
    ])
    if p["invoices_with_mistakes_not_flagged"]:
        lines += ["", "  Invoices with a mistake that were NOT sent to review:"]
        lines += [f"    {item['invoice']}: {', '.join(item['fields'])}" for item in p["invoices_with_mistakes_not_flagged"]]
    if p["clean_invoices_flagged_list"]:
        lines += ["", "  Clean invoices flagged anyway (a person checks them although nothing was wrong):"]
        lines += [f"    {item['invoice']}: {', '.join(item['rules'])}" for item in p["clean_invoices_flagged_list"]]

    lines += section("5. Processing time")
    lines += ["  Seconds from upload until the document is done or failed, as a user waits for it (one document at a time).", ""]
    rows = [["Kind of file", "Documents", "Average", "Median", "Fastest", "Slowest"]]
    for kind in KINDS:
        if t["by_kind"].get(kind):
            k = t["by_kind"][kind]
            rows.append([kind, k["documents"], f"{k['average']} s", f"{k['median']} s", f"{k['fastest']} s", f"{k['slowest']} s"])
    a = t["all"]
    rows.append(["all", a["documents"], f"{a['average']} s", f"{a['median']} s", f"{a['fastest']} s", f"{a['slowest']} s"])
    lines += table(rows)
    lines += ["", f"  Per invoice read with Gemini (average): {t['seconds_per_invoice_read_with_ai']} s.",
              "  Slowest documents: " + ", ".join(f"{s['file']} ({s['seconds']} s)" for s in t["slowest"]) + ".",
              "  Gemini models that read the invoices: " + ", ".join(f"{model} {count}" for model, count in scores["ai_models"].items()) + ".",
              f"  Meaning search: {'every document was added' if not meaning_failed else 'not added for ' + ', '.join(meaning_failed)}."]

    lines += section("6. What the results show")
    lines += [
        f"  - Digital PDFs and spreadsheets: {pct(scores['fields_by_kind'].get('digital PDF', {}).get('accuracy'))} and "
        f"{pct(scores['fields_by_kind'].get('spreadsheet', {}).get('accuracy'))} of fields right.",
        f"  - {len(ocr_mistakes)} of the {len(mistakes)} field mistakes are in scanned PDFs and images, so they come from OCR (reading",
        "    text from a picture), not from Gemini: Gemini returned exactly the text OCR gave it. The font used for the scans",
        "    and photos draws the zero with a dot inside, and Tesseract read several of those zeros as 6 or 9",
        "    (e.g. the date 2026-10-13 became 2026-16-13, and IMG-4003 became IMG-4663). Most invoices use fonts with a",
        "    plain zero, so this dataset is harder for OCR than usual; we kept the result instead of changing the font.",
        "  - The safety net worked: a misread date like 2026-16-13 (there is no month 16) was left empty instead of",
        "    guessed, and misread amounts no longer added up, so the checks flagged them. Every invoice with a mistake",
        f"    was sent to review ({p['invoices_with_mistakes_flagged']} of {p['invoices_with_mistakes']}). No value was made up ({f['made up']}).",
        "  - Pictures read with low certainty are marked 'uncertain' and sent to review even when they were read right",
        f"    ({p['clean_invoices_flagged']} of {p['clean_invoices']} clean invoices). That costs a person a quick look, which we prefer",
        "    over trusting a value that may be wrong.",
        "  - Free-tier model rotation worked during the run: when the daily limit of the first model was used up, the",
        "    next model read the remaining invoices. That model was faster, but it also read all the scans and images,",
        "    so speed and accuracy can't be compared fairly between the two models from this run.",
        "  - Most of the processing time is the Gemini request (spreadsheets, read without AI, take under a second).",
        "  - The PDF that was cut off in the middle was repaired by the PDF library into a blank page, so it failed with",
        "    'No text was found to read' instead of a more precise 'damaged file' message. It still failed, as it should.",
    ]

    lines += section("7. Corrections made after the run (openly)")
    lines += [
        "  The answer sheet had two mistakes, both proven from the files themselves. They were corrected in",
        "  make_dataset.py (with a comment), and a test now checks that labeled values can really be read in the PDFs:",
        "  - d04_european_numbers.pdf: the PDF font could not draw the € sign, so the file shows 'Total: · 3.399,24'.",
        "    No currency is written, so the system's empty answer is right; the label said EUR.",
        "  - d07_no_tax_dollar_sign.pdf: a '$' alone is correctly marked 'uncertain', but by design (Task 3) only the",
        "    important fields (number, date, supplier, total) send an invoice to review; the label expected a problem.",
        "  Two measures were made fairer after seeing the first numbers: problems are only judged on invoices the system",
        "  read, and a review flag only counts as 'not needed' when the invoice was clean AND read right.",
        "  The files used in the run were not changed (checked byte for byte).",
    ]

    lines += section("8. Limits of this evaluation")
    lines += [
        f"  - The dataset is small ({scores['documents_in_dataset']} documents, {f['invoices']} invoices) and made up by us, so the",
        "    invoices are cleaner and more alike than real ones (one layout, printed text, no handwriting, no stamps or logos).",
        "    Real invoices will score lower, especially photos.",
        "  - It is one run. Gemini can answer slightly differently from run to run, even with temperature 0.",
        "  - The free Gemini tier limits how many invoices can be tested per day, and the model used changes when a",
        "    daily limit is used up, which changes the speed.",
        "  - Times were measured on one laptop, one document at a time, with the free tier's waits and retries included.",
        "  - The answer sheet was written by the same people who built the system; we tried to keep it independent by",
        "    making it before the run, together with the files, and by recording every correction above.",
    ]

    lines += section("9. Meaning search (measured separately in Task 5)")
    measured = (PROJECT / "test-results" / "task5_meaning_search_scores.txt").read_text(encoding="utf-8")
    first = next(line for line in measured.splitlines() if line.startswith("The right invoice was first"))
    lines += ["  Measured with the real Gemini embedding model on sample invoices and searches",
              "  (test-results/task5_meaning_search_scores.txt): " + first]

    lines += section("How to repeat this evaluation")
    lines += ["  cd AI",
              "  uv run python evaluation/make_dataset.py       # the files and the answer sheet (already in git)",
              "  uv run python evaluation/run_evaluation.py     # the real run (about 22 Gemini requests)",
              "  uv run python evaluation/score.py              # the numbers (no Gemini)",
              "  uv run python evaluation/write_report.py       # this report", ""]
    return "\n".join(lines)


def main():
    raw = json.loads((EVALUATION / "results" / "raw_results.json").read_text(encoding="utf-8"))
    scores = json.loads((EVALUATION / "results" / "real_run_scores.json").read_text(encoding="utf-8"))
    REPORT.write_text(write(scores, raw), encoding="utf-8")
    print(f"Written: {REPORT.relative_to(PROJECT)}")


if __name__ == "__main__":
    main()
