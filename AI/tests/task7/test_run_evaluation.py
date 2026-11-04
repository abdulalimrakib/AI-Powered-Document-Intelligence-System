"""Step 3 — Running the evaluation through the system (with a fake backend here, so no Gemini is used)"""

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "evaluation"))
import run_evaluation  # noqa: E402

FILE = "d01_clean_usd.pdf"  # any file of the dataset; the fake backend decides what happens to it


def fake_backend(monkeypatch, upload: dict, statuses: list[dict]):
    """A fake backend: answers the upload with `upload`, and each status request with the next of `statuses`."""
    monkeypatch.setattr(run_evaluation.time, "sleep", lambda seconds: None)  # don't really wait
    asked = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(f"{request.method} {request.url.path}")
        if request.method == "POST":
            return httpx.Response(201 if upload["success"] else 400, json=upload)
        return httpx.Response(200, json={"success": True, "data": statuses.pop(0) if len(statuses) > 1 else statuses[0]})

    client = httpx.Client(base_url="http://fake", transport=httpx.MockTransport(answer))
    return client, asked


def document(status: str, error=None, invoice_errors=(), seconds="4.20") -> dict:
    return {"id": 7, "status": status, "error": error, "processing_seconds": seconds, "created_at": "2026-11-04T10:00:00Z",
            "invoices": [{"error": message} for message in invoice_errors]}


UPLOADED = {"success": True, "data": {"documents": [{"id": 7}], "rejected": []}}


def test_waits_until_a_document_is_done_and_keeps_its_times(monkeypatch):
    """Uploads a file, waits while it is pending and processing, and keeps the result and the times"""
    client, asked = fake_backend(monkeypatch, UPLOADED, [document("pending"), document("processing"), document("done")])

    outcome = run_evaluation.run_one(client, FILE)

    assert outcome["status"] == "done"
    assert outcome["document_id"] == 7
    assert outcome["processing_seconds"] == "4.20"
    assert outcome["wall_seconds"] >= 0
    assert asked == ["POST /api/v1/documents"] + ["GET /api/v1/documents/7"] * 3


def test_keeps_a_failed_document(monkeypatch):
    """A document that fails (e.g. a damaged file) is kept as failed"""
    client, _ = fake_backend(monkeypatch, UPLOADED, [document("failed", error="The PDF is damaged and can't be opened", seconds=None)])

    assert run_evaluation.run_one(client, FILE)["status"] == "failed"


def test_keeps_the_reason_of_a_file_refused_at_upload(monkeypatch):
    """A file the backend refuses at upload is kept as refused, with the reason"""
    refused = {"success": False, "message": "None of the files can be processed.",
               "data": {"documents": [], "rejected": [{"filename": FILE, "reason": "The file is empty."}]}}
    client, asked = fake_backend(monkeypatch, refused, [])

    outcome = run_evaluation.run_one(client, FILE)

    assert outcome == {"status": "refused", "reason": "The file is empty.", "wall_seconds": outcome["wall_seconds"], "document_id": None}
    assert asked == ["POST /api/v1/documents"]


@pytest.mark.parametrize("failed", [
    pytest.param(document("failed", error="AI extraction failed: the free Gemini limit is used up for today on every model we use (4). Try again in about 2 h 9 min."), id="whole document"),
    pytest.param(document("done", invoice_errors=[None, "AI extraction failed: the free Gemini limit is used up for today on every model we use (4). Try again in about 2 h."]), id="one invoice of a document"),
])
def test_stops_when_the_daily_gemini_limit_is_used_up(monkeypatch, capsys, failed):
    """Stops at once when the daily Gemini limit is used up, so the file is done again next time"""
    client, _ = fake_backend(monkeypatch, UPLOADED, [failed])

    assert run_evaluation.run_one(client, FILE) is None
    assert "STOPPED" in capsys.readouterr().out


def test_continues_with_the_files_that_are_not_done(tmp_path):
    """Keeps earlier results, so a new run only does the files that are not done yet"""
    results_file = tmp_path / "raw_results.json"
    results_file.write_text(json.dumps({"started_at": "earlier", "documents": {FILE: {"status": "done"}}}))

    assert run_evaluation.load_results(results_file, fresh=False)["documents"] == {FILE: {"status": "done"}}
    assert run_evaluation.load_results(results_file, fresh=True)["documents"] == {}


def test_the_practice_run_is_kept_apart_from_the_real_run():
    """The practice run uses its own database and results file, never the real run's"""
    assert run_evaluation.run_settings(no_gemini=True) == ("practice_run", "docintel_eval_practice")
    assert run_evaluation.run_settings(no_gemini=False) == ("raw_results", "docintel_eval")


def test_the_practice_run_has_no_gemini_key(monkeypatch):
    """The practice run starts the AI service without a Gemini key; the real run keeps the key"""
    monkeypatch.setenv("GEMINI_API_KEY", "a-key")

    assert run_evaluation.ai_environment(no_gemini=True)["GEMINI_API_KEY"] == ""
    assert run_evaluation.ai_environment(no_gemini=False)["GEMINI_API_KEY"] == "a-key"
