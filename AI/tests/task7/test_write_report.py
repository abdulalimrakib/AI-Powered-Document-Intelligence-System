"""Step 6 — Writing the evaluation report from the measured results"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "evaluation"))
import write_report  # noqa: E402
from score import score  # noqa: E402

RESULTS = Path(__file__).parents[2] / "evaluation" / "results"
RAW = json.loads((RESULTS / "raw_results.json").read_text(encoding="utf-8"))
SCORES = json.loads((RESULTS / "real_run_scores.json").read_text(encoding="utf-8"))
REPORT = write_report.write(SCORES, RAW)


def test_the_saved_scores_are_the_scores_of_the_saved_results():
    """The saved scores are exactly what score.py gives for the saved results and the answer sheet"""
    labels = json.loads((RESULTS.parent / "labels.json").read_text(encoding="utf-8"))
    assert score(labels, RAW) == SCORES


def test_the_report_shows_the_measured_main_numbers():
    """The report shows the measured success rate, failure rate, accuracy and times"""
    o, f, t = SCORES["outcomes"], SCORES["fields"], SCORES["time"]["all"]
    assert f"{o['valid_succeeded']} of {o['valid_documents']} = {o['success_rate']}%" in REPORT
    assert f"= {o['failure_rate']}%" in REPORT
    assert f"{f['right']} of {f['fields_judged']} = {f['accuracy']}%" in REPORT
    assert f"{t['average']} s / {t['median']} s" in REPORT


def test_the_report_lists_every_mistake():
    """Every field that was not right is listed in the report, with what was expected and what was given"""
    # The table under "Every field that was not right", without its two heading lines, until the empty line after it
    after = REPORT.split("### Every field that was not right\n\n")[1]
    rows = after.split("\n\n")[0].splitlines()[2:]
    assert len(rows) == len(SCORES["mistakes"])
    for mistake in SCORES["mistakes"]:
        assert any(mistake["file"] in row and (mistake["got"] or "(empty)") in row for row in rows)


def test_the_report_shows_every_broken_file_with_its_reason():
    """Every broken or unsupported file is in the report with the reason the system gave"""
    for item in SCORES["outcomes"]["invalid_details"]:
        assert item["file"] in REPORT and item["reason"] in REPORT


def test_the_report_explains_its_corrections_and_limits():
    """The report says openly what was corrected after the run, and the limits of the evaluation"""
    assert "Corrections made after the run" in REPORT
    assert "Limits of this evaluation" in REPORT


def test_the_saved_report_is_up_to_date():
    """The report in deliverables/EVALUATION_REPORT.md is exactly what the saved results give (nobody changed it by hand)"""
    assert write_report.REPORT.read_text(encoding="utf-8") == REPORT
