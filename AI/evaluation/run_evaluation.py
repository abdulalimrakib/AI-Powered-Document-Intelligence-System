"""Task 7, Step 3: run the evaluation through the REAL system and save everything that comes back.

    uv run python evaluation/run_evaluation.py              # the real run (uses about 22 Gemini requests)
    uv run python evaluation/run_evaluation.py --no-gemini  # a practice run: no Gemini key, so no requests
    uv run python evaluation/run_evaluation.py --fresh      # forget earlier results and start again

What it does:
1. Starts its own AI service (port 8100) and backend (port 3100), with its own database, queue and upload folder,
   so your real data and the test data are never touched.
2. Uploads every file of the dataset through the backend API (like the website does), one at a time, and waits
   until it is done or failed. It saves after every document.
3. When the free Gemini limit is used up for today, it stops at once and says when to try again. The next run
   only does the files that are not finished yet, so no request is wasted.
4. At the end it fetches the final state of every document (a duplicate is only known after its copy is read)
   and saves it all in evaluation/results/. score.py turns it into numbers.
"""

import argparse
import datetime
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

EVALUATION = Path(__file__).parent
PROJECT = EVALUATION.parents[1]
AI_FOLDER = PROJECT / "AI"
BACKEND_FOLDER = PROJECT / "backend"
RESULTS = EVALUATION / "results"

AI_PORT = 8100
BACKEND_PORT = 3100
BACKEND = f"http://localhost:{BACKEND_PORT}"
WAIT_FOR_DOCUMENT_SECONDS = 15 * 60  # a slow Gemini answer with retries and model switches can take minutes

# The words the AI service uses when the daily free limit is used up (see AI/extract_invoice.py)
LIMIT_USED_UP = "limit is used up for today"


def main():
    parser = argparse.ArgumentParser(description="Run the evaluation through the real system.")
    parser.add_argument("--no-gemini", action="store_true", help="practice run: start the AI service without a Gemini key")
    parser.add_argument("--fresh", action="store_true", help="forget earlier results and empty the evaluation database")
    options = parser.parse_args()

    name, database = run_settings(options.no_gemini)
    results_file = RESULTS / f"{name}.json"
    RESULTS.mkdir(exist_ok=True)

    labels = json.loads((EVALUATION / "labels.json").read_text(encoding="utf-8"))
    results = load_results(results_file, options.fresh)
    results["mode"] = "practice run without Gemini" if options.no_gemini else "real run"
    todo = [document for document in labels["documents"] if document["file"] not in results["documents"]]
    print(f"{len(labels['documents']) - len(todo)} documents already done, {len(todo)} to do")

    prepare_database(database, empty=options.fresh)
    services = start_services(database, options.no_gemini)
    try:
        with httpx.Client(base_url=BACKEND, timeout=60) as client:
            for number, document in enumerate(todo, start=1):
                print(f"[{number}/{len(todo)}] {document['file']} ...", end=" ", flush=True)
                outcome = run_one(client, document["file"])
                if outcome is None:  # the daily limit is used up: stop, and do this file next time
                    break
                results["documents"][document["file"]] = outcome
                save(results_file, results)
                print(outcome["status"], f"({outcome['wall_seconds']} s)")

            # The final state of every document, read again now that all are processed (duplicates, embeddings)
            for file, outcome in results["documents"].items():
                if outcome.get("document_id"):
                    outcome["final"] = client.get(f"/api/v1/documents/{outcome['document_id']}").json()["data"]
            results["finished_at"] = now()
            save(results_file, results)
    finally:
        stop_services(services)

    left = len(labels["documents"]) - len(results["documents"])
    print(f"\nSaved in {results_file.relative_to(PROJECT)}." + (f" {left} documents are not done yet: run this again later." if left else " All documents are done."))


def run_settings(no_gemini: bool) -> tuple[str, str]:
    """(results file name, database). A practice run has its own, so it is never mixed with the real run."""
    return ("practice_run", "docintel_eval_practice") if no_gemini else ("raw_results", "docintel_eval")


def ai_environment(no_gemini: bool) -> dict:
    """The settings for the AI service. A practice run gets no Gemini key, so it can't use Gemini."""
    environment = dict(os.environ)
    if no_gemini:
        environment["GEMINI_API_KEY"] = ""  # an empty key wins over AI/.env (python-dotenv keeps what is set)
    return environment


def run_one(client: httpx.Client, file: str) -> dict | None:
    """Upload one file and wait until it is finished. Returns what happened, or None when the daily limit is used up."""
    data = (EVALUATION / "dataset" / file).read_bytes()
    start = time.perf_counter()
    answer = client.post("/api/v1/documents", files=[("files", (file, data))]).json()
    if not answer["success"]:  # refused at upload (unsupported or empty file)
        reasons = [item["reason"] for item in (answer.get("data") or {}).get("rejected", [])] or [answer["message"]]
        return {"status": "refused", "reason": reasons[0], "wall_seconds": round(time.perf_counter() - start, 2), "document_id": None}

    document_id = answer["data"]["documents"][0]["id"]
    deadline = time.time() + WAIT_FOR_DOCUMENT_SECONDS
    while time.time() < deadline:
        document = client.get(f"/api/v1/documents/{document_id}").json()["data"]
        if document["status"] in ("done", "failed"):
            break
        time.sleep(0.2)  # check often, so the measured time is close to the real time
    else:
        raise SystemExit(f"\n{file} was not finished after {WAIT_FOR_DOCUMENT_SECONDS // 60} minutes. Is the AI service working?")
    wall_seconds = round(time.perf_counter() - start, 2)

    errors = [document["error"] or ""] + [invoice["error"] or "" for invoice in document["invoices"]]
    limit_message = next((error for error in errors if LIMIT_USED_UP in error), None)
    if limit_message:
        print(f"\n\nSTOPPED: {limit_message}\nNothing more is sent today. Run this again later; finished documents are kept.")
        return None

    return {"status": document["status"], "document_id": document_id, "wall_seconds": wall_seconds,
            "processing_seconds": document["processing_seconds"], "uploaded_at": document["created_at"]}


def load_results(results_file: Path, fresh: bool) -> dict:
    if results_file.exists() and not fresh:
        return json.loads(results_file.read_text(encoding="utf-8"))
    return {"started_at": now(), "documents": {}}


def save(results_file: Path, results: dict):
    results_file.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# ---------- starting and stopping our own copy of the system ----------

def prepare_database(database: str, empty: bool):
    """Create the evaluation database in the Postgres container if it doesn't exist (and empty it for --fresh)."""
    def psql(sql: str, db: str = "docintel") -> str:
        result = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "docintel", "-d", db, "-tAc", sql],
                                cwd=PROJECT, capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(f"Postgres can't be reached. Start it with: docker compose up -d\n{result.stderr}")
        return result.stdout.strip()

    if psql(f"SELECT 1 FROM pg_database WHERE datname = '{database}'") != "1":
        psql(f"CREATE DATABASE {database}")
    elif empty and psql("SELECT to_regclass('documents')", database):
        psql("TRUNCATE documents RESTART IDENTITY CASCADE", database)


def start_services(database: str, no_gemini: bool) -> list[subprocess.Popen]:
    for port in (AI_PORT, BACKEND_PORT):
        with socket.socket() as probe:
            if probe.connect_ex(("localhost", port)) == 0:
                raise SystemExit(f"Port {port} is already in use. Stop what is running there and try again.")

    ai = subprocess.Popen([str(AI_FOLDER / ".venv" / "bin" / "uvicorn"), "main:app", "--port", str(AI_PORT)],
                          cwd=AI_FOLDER, env=ai_environment(no_gemini), stdout=open(RESULTS / "ai_service.log", "w"), stderr=subprocess.STDOUT)
    backend_env = {**os.environ, "PORT": str(BACKEND_PORT), "AI_API_URL": f"http://localhost:{AI_PORT}",
                   "DATABASE_URL": f"postgres://docintel:docintel@localhost:5440/{database}",
                   "QUEUE_NAME": f"documents-{database}",
                   "UPLOAD_FOLDER": str(BACKEND_FOLDER / "storage" / f"{database}-uploads")}
    backend = subprocess.Popen([str(BACKEND_FOLDER / "node_modules" / ".bin" / "ts-node"), "server.ts"],
                               cwd=BACKEND_FOLDER, env=backend_env, stdout=open(RESULTS / "backend.log", "w"), stderr=subprocess.STDOUT)
    services = [ai, backend]

    for url in (f"http://localhost:{AI_PORT}/health", f"{BACKEND}/health"):
        for _ in range(120):
            try:
                if httpx.get(url, timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        else:
            stop_services(services)
            raise SystemExit(f"{url} did not start. See evaluation/results/*.log")
    print(f"Started the AI service (port {AI_PORT}) and the backend (port {BACKEND_PORT}), database {database}"
          + (", WITHOUT a Gemini key" if no_gemini else ""))
    return services


def stop_services(services: list[subprocess.Popen]):
    for service in services:
        service.terminate()
    for service in services:
        try:
            service.wait(timeout=10)
        except subprocess.TimeoutExpired:
            service.kill()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nStopped. Finished documents are saved; run this again to continue.")
