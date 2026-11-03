import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

# Settings come from AI/.env, so the key is never written in the code.
load_dotenv(Path(__file__).parent / ".env")

# Free models, best first. Each has its own daily free limit (about 20 requests), so when one is
# used up we switch to the next. Override with GEMINI_MODELS in AI/.env, e.g. "gemini-3.5-flash,gemini-2.5-flash".
DEFAULT_MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-3.1-flash-lite"]
PROMPT = (Path(__file__).parent / "extract_prompt.txt").read_text(encoding="utf-8")

# Very long invoices are cut, to stay inside the free limits. Normal invoices are far shorter.
MAX_TEXT_CHARACTERS = 60_000

# Gemini can be busy (503) or we can reach the per-minute limit (429). Then we wait and try again.
RETRY_WAIT_SECONDS = [5, 15, 30]
TEMPORARY_ERRORS = [429, 500, 503, 504]

# If Gemini says "retry in 2 hours", that model's daily limit is used up: waiting is pointless.
LONGEST_WAIT_SECONDS = 60

# Models whose daily limit is used up, and the time (time.time()) when they can be used again.
used_up_until = {}

INVOICE_FIELDS = ["invoice_number", "invoice_date", "supplier_name", "customer_name",
                  "subtotal", "tax", "total", "currency"]
LINE_ITEM_FIELDS = ["description", "quantity", "unit_price", "amount"]


# ---------- the shape Gemini must answer in ----------

class Field(BaseModel):
    value: str | None
    evidence: str | None


class LineItem(BaseModel):
    description: str | None
    quantity: str | None
    unit_price: str | None
    amount: str | None
    evidence: str | None


class InvoiceAnswer(BaseModel):
    invoice_number: Field
    invoice_date: Field
    supplier_name: Field
    customer_name: Field
    subtotal: Field
    tax: Field
    total: Field
    currency: Field
    line_items: list[LineItem]


# ---------- Step 2b: ask Gemini ----------

def extract_invoice(text: str) -> dict:
    """Ask Gemini for the invoice fields in this text. Returns the same shape as spreadsheet invoices:
    {"fields": {field: {"value", "evidence"}}, "line_items": [...], "warnings": [...], "model": "..."}.
    Raises ValueError with a clear message when it can't be done."""
    warnings = []
    if len(text) > MAX_TEXT_CHARACTERS:
        text = text[:MAX_TEXT_CHARACTERS]
        warnings.append(f"The invoice text is very long; only the first {MAX_TEXT_CHARACTERS} characters were read")

    answer, model = ask_gemini(text)
    fields = {field: getattr(answer, field).model_dump() for field in INVOICE_FIELDS}
    line_items = [item.model_dump() for item in answer.line_items]
    return {"fields": fields, "line_items": line_items, "warnings": warnings, "model": model}


class ModelUsedUp(Exception):
    """This model's daily free limit is used up."""
    def __init__(self, wait_seconds: float):
        self.wait_seconds = wait_seconds


class ModelNotWorking(Exception):
    """This model is busy, or doesn't exist anymore. The message says which."""


def ask_gemini(text: str) -> tuple[InvoiceAnswer, str]:
    """Try the models one by one until one answers. Returns (answer, the model that answered)."""
    client = make_client()
    config = types.GenerateContentConfig(
        system_instruction=PROMPT,
        temperature=0,  # the same text always gives the same answer
        response_mime_type="application/json",
        response_schema=InvoiceAnswer,  # Gemini must answer in exactly this shape
    )
    contents = f"Document text:\n<<<\n{text}\n>>>"

    models = model_list()
    problem = None
    for model in models:
        if used_up_until.get(model, 0) > time.time():
            continue  # we already know its daily limit is used up: don't even ask
        try:
            return ask_model(client, model, contents, config), model
        except ModelUsedUp as used_up:
            used_up_until[model] = time.time() + used_up.wait_seconds
        except ModelNotWorking as not_working:
            problem = str(not_working)

    if problem:  # at least one model was busy or missing: that is the most useful message
        raise ValueError(f"AI extraction failed: {problem}")
    wait = min(used_up_until[model] for model in models) - time.time()
    raise ValueError(f"AI extraction failed: the free Gemini limit is used up for today on every model we use "
                     f"({len(models)}). Try again in about {readable_wait(wait)}.")


def ask_model(client: genai.Client, model: str, contents: str, config: types.GenerateContentConfig):
    """Ask one model, waiting and trying again when it is busy for a moment."""
    broken_answers = 0
    attempt = 0
    while True:
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
        except errors.APIError as error:
            gemini_wait = wait_time_from_gemini(error)
            if error.code == 429 and gemini_wait is not None and gemini_wait > LONGEST_WAIT_SECONDS:
                raise ModelUsedUp(gemini_wait)
            if error.code == 404:
                raise ModelNotWorking(f"the model {model} is not available")
            if error.code in TEMPORARY_ERRORS and attempt < len(RETRY_WAIT_SECONDS):
                # Wait as long as Gemini asks for, or our own wait time if that is longer.
                time.sleep(max(RETRY_WAIT_SECONDS[attempt], gemini_wait or 0))
                attempt += 1
                continue
            if error.code == 429:
                raise ModelNotWorking("the free Gemini limit was reached. Try again later.")
            if error.code in TEMPORARY_ERRORS:
                raise ModelNotWorking("Gemini is busy or unavailable. Try again later.")
            raise ValueError(explain_error(error))

        if isinstance(response.parsed, InvoiceAnswer):
            return response.parsed
        # The answer was not valid JSON in our shape. This is rare: try once more.
        broken_answers += 1
        if broken_answers > 1:
            raise ValueError("AI extraction failed: the AI did not answer in the expected format")


def model_list() -> list[str]:
    from_env = os.environ.get("GEMINI_MODELS", "")
    models = [model.strip() for model in from_env.split(",") if model.strip()]
    return models or DEFAULT_MODELS


def make_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing in AI/.env")
    return genai.Client(api_key=api_key)


def wait_time_from_gemini(error: errors.APIError) -> float | None:
    """A 429 error from Gemini says how long to wait ("retryDelay": "7717s"). Returns the seconds, or None."""
    details = error.details.get("error", {}).get("details", []) if isinstance(error.details, dict) else []
    for detail in details:
        if detail.get("@type", "").endswith("RetryInfo") and detail.get("retryDelay"):
            return float(detail["retryDelay"].rstrip("s"))
    return None


def readable_wait(seconds: float) -> str:
    hours, minutes = divmod(max(1, round(seconds / 60)), 60)  # 7717 seconds -> "2 h 9 min"
    return f"{hours} h {minutes} min" if hours else f"{minutes} min"


def explain_error(error: errors.APIError) -> str:
    """A clear message for errors that trying again or another model can't fix."""
    if error.code in (401, 403) or (error.code == 400 and "API key" in str(error)):
        return "AI extraction failed: the Gemini API key is not valid. Check GEMINI_API_KEY in AI/.env."
    return f"AI extraction failed: Gemini returned error {error.code}"


# ---------- Step 3: check the AI's evidence ----------

def check_evidence(invoice: dict, text: str) -> dict[str, str]:
    """Check that every value the AI gave really comes from the document ("trust, but verify").
    A value passes when its evidence is in the document text AND the value is in its evidence.
    Returns {field: problem message} for the values that fail."""
    document = simplify(text)
    problems = {}

    for field, answer in invoice["fields"].items():
        problem = evidence_problem(answer["value"], answer["evidence"], document)
        if problem:
            problems[field] = problem

    for number, item in enumerate(invoice["line_items"], start=1):
        for field in LINE_ITEM_FIELDS:
            problem = evidence_problem(item[field], item["evidence"], document)
            if problem:
                problems[f"line item {number} {field}"] = problem

    return problems


def evidence_problem(value: str | None, evidence: str | None, document: str) -> str | None:
    if value is None:
        return None  # nothing was claimed, so there is nothing to check
    if not evidence:
        return "the AI gave no evidence for this value"
    if simplify(evidence) not in document:
        return "the AI's evidence was not found in the document"
    if simplify(value) not in simplify(evidence):
        return "the value is not in the AI's evidence"
    return None


def simplify(text: str) -> str:
    """Small letters and single spaces, so line breaks and extra spaces don't matter when comparing."""
    return " ".join(text.lower().split())
