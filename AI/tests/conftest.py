"""pytest loads this file automatically. It adds two options:

    --save-results   writes an easy-to-read results file for each Task into the test-results/ folder
    --real-gemini    also runs the few tests that call the real Gemini (the free tier allows only
                     20 requests a day, so these are skipped unless you ask for them)

    uv run pytest tests/task1 --save-results
    uv run pytest tests/task2 --real-gemini --save-results
"""

import datetime
from pathlib import Path

import pytest

RESULTS_FOLDER = Path(__file__).parents[2] / "test-results"

# Test folder -> (title of the report, file name)
TASKS = {
    "task1": ("Task 1 — Document Processing", "task1_document_processing.txt"),
    "task2": ("Task 2 — AI Information Extraction", "task2_ai_extraction.txt"),
    "task3": ("Task 3 — Data Validation", "task3_validation.txt"),
    "task4": ("Task 4 — Backend API (the AI service's part)", "task4_ai_service.txt"),
    "task5": ("Task 5 — Database and search (the AI service's part)", "task5_ai_service.txt"),
    "task7": ("Task 7 — Testing and evaluation (the AI service's part)", "task7_evaluation_tools.txt"),
}

# Every finished test is added here: (task folder, step title, description, "PASS"/"FAIL"/"SKIP", reason, seconds)
results = []


def pytest_addoption(parser):
    parser.addoption("--save-results", action="store_true", help="save easy-to-read results in test-results/")
    parser.addoption("--real-gemini", action="store_true", help="also run the tests that call the real Gemini")


def pytest_configure(config):
    config.addinivalue_line("markers", "real_gemini: the test calls the real Gemini (uses the free daily limit)")


def pytest_collection_modifyitems(config, items):
    """Skip the real-Gemini tests unless --real-gemini is given."""
    if config.getoption("--real-gemini"):
        return
    skip = pytest.mark.skip(reason="calls the real Gemini (free limit: 20 requests a day); run with --real-gemini")
    for item in items:
        if "real_gemini" in item.keywords:
            item.add_marker(skip)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """Runs after each part of a test; we keep the result of the test itself."""
    report = yield
    if report.when == "call" or report.failed or report.skipped:
        description = (item.function.__doc__ or item.name).strip()
        if hasattr(item, "callspec"):  # a test that runs once per example, e.g. (blurry)
            description += f" ({item.callspec.id})"
        if report.skipped:
            outcome, reason = "SKIP", report.longrepr[2].removeprefix("Skipped: ")
        elif report.passed:
            outcome, reason = "PASS", ""
        else:
            outcome, reason = "FAIL", plain_reason(call.excinfo)
        step = (item.module.__doc__ or item.module.__name__).strip()
        results.append((Path(item.path).parent.name, step, description, outcome, reason, report.duration))
    return report


def plain_reason(excinfo) -> str:
    """Explain a failure in one simple sentence."""
    if excinfo is None:
        return "the test could not be run"
    if excinfo.errisinstance(AssertionError):
        return "the result was not what the test expected"
    # Any other error means the code crashed: show the error's name and message.
    return f"the code stopped with an error: {excinfo.exconly().splitlines()[0]}"


def pytest_sessionfinish(session):
    if not session.config.getoption("--save-results"):
        return
    for task_folder, (title, file_name) in TASKS.items():
        task_results = [result for result in results if result[0] == task_folder]
        if task_results:
            write_report(title, task_folder, task_results, RESULTS_FOLDER / file_name)


def write_report(title, task_folder, task_results, path):
    count = {outcome: sum(result[3] == outcome for result in task_results) for outcome in ("PASS", "FAIL", "SKIP")}
    seconds = sum(result[5] for result in task_results)
    if count["FAIL"]:
        summary = f"{count['FAIL']} OF {len(task_results)} TESTS FAILED"
    else:
        summary = f"ALL {count['PASS']} TESTS PASSED"
    if count["SKIP"]:
        summary += f", {count['SKIP']} SKIPPED"

    lines = [
        f"{title}: test results",
        "=" * 60,
        f"Date:    {datetime.datetime.now():%Y-%m-%d %H:%M}",
        f"Result:  {summary}  ({seconds:.1f} seconds)",
        "",
        "Each line below is one automatic check of the system.",
        "PASS means the system did the right thing; FAIL means it did not (the reason is shown).",
        "SKIP means the check was not run this time (the reason is shown).",
        "Text in brackets is the example that was used, e.g. (blurry) is a blurry picture.",
    ]

    steps = sorted(set(result[1] for result in task_results))  # "Step 1 ...", "Step 2 ...", in order
    for step in steps:
        step_results = [result for result in task_results if result[1] == step]
        step_passed = sum(result[3] == "PASS" for result in step_results)
        lines += ["", f"{step}  ({step_passed} of {len(step_results)} passed)", "-" * 60]
        for _, _, description, outcome, reason, _ in step_results:
            lines.append(f"  {outcome}  {description}")
            if reason:
                lines.append(f"        reason: {reason}")

    lines += ["", "To run these checks again:", f"    cd AI && uv run pytest tests/{task_folder} --save-results"]
    if count["SKIP"]:
        lines += ["To also run the checks with the real Gemini:",
                  f"    cd AI && uv run pytest tests/{task_folder} --real-gemini --save-results"]
    if count["FAIL"]:
        lines += ["To see the full details of a failure:", f"    cd AI && uv run pytest tests/{task_folder} -v"]
    lines.append("")
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
