"""pytest loads this file automatically. It adds the --save-results option, which writes an
easy-to-read results file for each Task into the test-results/ folder.

    uv run pytest tests/task1 --save-results
"""

import datetime
from pathlib import Path

import pytest

RESULTS_FOLDER = Path(__file__).parents[2] / "test-results"

# Test folder -> (title of the report, file name)
TASKS = {
    "task1": ("Task 1 — Document Processing", "task1_document_processing.txt"),
}

# Every finished test is added here: (task folder, step title, description, passed?, reason, seconds)
results = []


def pytest_addoption(parser):
    parser.addoption("--save-results", action="store_true", help="save easy-to-read results in test-results/")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """Runs after each part of a test; we keep the result of the test itself."""
    report = yield
    if report.when == "call" or report.failed:
        description = (item.function.__doc__ or item.name).strip()
        if hasattr(item, "callspec"):  # a test that runs once per example, e.g. (blurry)
            description += f" ({item.callspec.id})"
        reason = plain_reason(call.excinfo) if call.excinfo else ""
        step = (item.module.__doc__ or item.module.__name__).strip()
        results.append((Path(item.path).parent.name, step, description, report.passed, reason, report.duration))
    return report


def plain_reason(excinfo) -> str:
    """Explain a failure in one simple sentence."""
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
    passed = sum(result[3] for result in task_results)
    failed = len(task_results) - passed
    seconds = sum(result[5] for result in task_results)
    summary = f"ALL {passed} TESTS PASSED" if failed == 0 else f"{failed} OF {len(task_results)} TESTS FAILED"

    lines = [
        f"{title}: test results",
        "=" * 60,
        f"Date:    {datetime.datetime.now():%Y-%m-%d %H:%M}",
        f"Result:  {summary}  ({seconds:.1f} seconds)",
        "",
        "Each line below is one automatic check of the system.",
        "PASS means the system did the right thing; FAIL means it did not (the reason is shown).",
        "Text in brackets is the example that was used, e.g. (blurry) is a blurry picture.",
    ]

    steps = sorted(set(result[1] for result in task_results))  # "Step 1 ...", "Step 2 ...", in order
    for step in steps:
        step_results = [result for result in task_results if result[1] == step]
        step_passed = sum(result[3] for result in step_results)
        lines += ["", f"{step}  ({step_passed} of {len(step_results)} passed)", "-" * 60]
        for _, _, description, ok, reason, _ in step_results:
            lines.append(f"  {'PASS' if ok else 'FAIL'}  {description}")
            if not ok:
                lines.append(f"        reason: {reason}")

    lines += ["", "To run these checks again:", f"    cd AI && uv run pytest tests/{task_folder} --save-results"]
    if failed:
        lines += ["To see the full details of a failure:", f"    cd AI && uv run pytest tests/{task_folder} -v"]
    lines.append("")
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
