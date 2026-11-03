"""Step 2b and 3 — Asking Gemini for the invoice fields, and checking its evidence"""

import pytest
from google.genai import errors

import extract_invoice
from clean_values import clean_amount, clean_currency
from extract_invoice import InvoiceAnswer, check_evidence, extract_invoice as extract

INVOICE_TEXT = """--- Page 1 ---
ACME TRADING LTD
Invoice No: INV-2026-001          Date: 15/10/2026
Bill to: Blue Sky Foods
Office chairs   10   100.00   1,000.00
Subtotal: 1,000.00
VAT (15%): 150.00
Total: $1,150.00"""


def field(value, evidence):
    return {"value": value, "evidence": evidence}


GOOD_ANSWER = {
    "invoice_number": field("INV-2026-001", "Invoice No: INV-2026-001"),
    "invoice_date": field("15/10/2026", "Date: 15/10/2026"),
    "supplier_name": field("ACME TRADING LTD", "ACME TRADING LTD"),
    "customer_name": field("Blue Sky Foods", "Bill to: Blue Sky Foods"),
    "subtotal": field("1,000.00", "Subtotal: 1,000.00"),
    "tax": field("150.00", "VAT (15%): 150.00"),
    "total": field("$1,150.00", "Total: $1,150.00"),
    "currency": field("$", "Total: $1,150.00"),
    "line_items": [{"description": "Office chairs", "quantity": "10", "unit_price": "100.00",
                    "amount": "1,000.00", "evidence": "Office chairs   10   100.00   1,000.00"}],
}


# ---------- a fake Gemini, so most tests are free, fast and work without internet ----------

class FakeResponse:
    def __init__(self, parsed):
        self.parsed = parsed


class FakeGemini:
    """Gives the planned answers one by one. An answer can be a dict (a good answer),
    None (a broken answer) or an error (e.g. "free limit reached")."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []
        self.models = self  # the real client is used as client.models.generate_content(...)

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return FakeResponse(None if answer is None else InvoiceAnswer.model_validate(answer))


def gemini_error(code: int, retry_delay: str | None = None) -> errors.APIError:
    """An error like the real Gemini sends. A 429 can say how long to wait, e.g. retry_delay="7717s"."""
    details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay}] if retry_delay else []
    error_class = errors.ClientError if code < 500 else errors.ServerError
    return error_class(code, {"error": {"code": code, "message": "test error", "details": details}})


@pytest.fixture
def use_fake_gemini(monkeypatch):
    """Replace the real Gemini with a fake one, and skip the real waiting between retries.
    By default there is one model ("model-a"); pass models=[...] to test switching between models."""
    def install(*answers, models=("model-a",)):
        fake = FakeGemini(*answers)
        monkeypatch.setattr(extract_invoice, "make_client", lambda: fake)
        monkeypatch.setattr(extract_invoice.time, "sleep", lambda seconds: None)
        monkeypatch.setattr(extract_invoice, "DEFAULT_MODELS", list(models))
        monkeypatch.setattr(extract_invoice, "used_up_until", {})  # every test starts fresh
        monkeypatch.delenv("GEMINI_MODELS", raising=False)
        return fake
    return install


# ---------- Step 2b: asking Gemini ----------

def test_gives_the_fields_in_our_shape(use_fake_gemini):
    """Gives every field with its value and evidence, plus the line items"""
    use_fake_gemini(GOOD_ANSWER)

    result = extract(INVOICE_TEXT)

    assert result["fields"]["total"] == {"value": "$1,150.00", "evidence": "Total: $1,150.00"}
    assert set(result["fields"]) == set(extract_invoice.INVOICE_FIELDS)
    assert result["line_items"][0]["description"] == "Office chairs"
    assert result["warnings"] == []
    assert result["model"] == "model-a"  # which model read it


def test_sends_the_prompt_the_text_and_strict_settings(use_fake_gemini):
    """Sends our instructions and the document, with temperature 0 and the fixed answer shape"""
    fake = use_fake_gemini(GOOD_ANSWER)

    extract(INVOICE_TEXT)

    call = fake.calls[0]
    assert INVOICE_TEXT in call["contents"]
    assert call["config"].system_instruction == extract_invoice.PROMPT
    assert call["config"].temperature == 0
    assert call["config"].response_schema is InvoiceAnswer
    assert call["model"] == "model-a"


def test_the_prompt_forbids_guessing_and_calculating():
    """The instructions tell the AI never to guess and never to calculate"""
    prompt = extract_invoice.PROMPT.lower()

    assert "never guess" in prompt
    assert "do not calculate" in prompt
    assert "null" in prompt


def test_very_long_text_is_cut_with_a_warning(use_fake_gemini):
    """Cuts a very long invoice text to stay within the free limits, and warns about it"""
    fake = use_fake_gemini(GOOD_ANSWER)

    result = extract("x" * (extract_invoice.MAX_TEXT_CHARACTERS + 500))

    assert len(fake.calls[0]["contents"]) < extract_invoice.MAX_TEXT_CHARACTERS + 100
    assert "very long" in result["warnings"][0]


@pytest.mark.parametrize("code", [
    pytest.param(429, id="free limit reached (429)"),
    pytest.param(503, id="Gemini busy (503)"),
])
def test_waits_and_tries_again_after_a_temporary_error(use_fake_gemini, code):
    """Waits and tries again when Gemini is busy or the free limit is reached"""
    fake = use_fake_gemini(gemini_error(code), gemini_error(code), GOOD_ANSWER)

    result = extract(INVOICE_TEXT)

    assert len(fake.calls) == 3
    assert result["fields"]["invoice_number"]["value"] == "INV-2026-001"


@pytest.mark.parametrize("code, message", [
    pytest.param(429, "free Gemini limit was reached", id="free limit reached (429)"),
    pytest.param(503, "Gemini is busy or unavailable", id="Gemini busy (503)"),
])
def test_gives_up_with_a_clear_message_after_three_retries(use_fake_gemini, code, message):
    """Gives up after 3 retries with a clear message instead of crashing"""
    fake = use_fake_gemini(*[gemini_error(code)] * 4)

    with pytest.raises(ValueError, match=message):
        extract(INVOICE_TEXT)
    assert len(fake.calls) == 4  # the first try + 3 retries


def test_daily_free_limit_stops_at_once_and_says_when_to_try_again(use_fake_gemini):
    """When Gemini says the free limit resets in hours, stops at once and says when to try again"""
    fake = use_fake_gemini(gemini_error(429, retry_delay="7717s"))  # about 2 hours 9 minutes

    with pytest.raises(ValueError, match="Try again in about 2 h 9 min"):
        extract(INVOICE_TEXT)
    assert len(fake.calls) == 1  # no pointless retries


def test_waits_as_long_as_gemini_asks(use_fake_gemini, monkeypatch):
    """Waits as long as Gemini asks for when that is longer than our own wait"""
    waits = []
    fake = use_fake_gemini(gemini_error(429, retry_delay="20s"), GOOD_ANSWER)
    monkeypatch.setattr(extract_invoice.time, "sleep", waits.append)

    extract(INVOICE_TEXT)

    assert waits == [20.0]
    assert len(fake.calls) == 2


# ---------- switching to the next free model ----------

def test_switches_to_the_next_model_when_the_daily_limit_is_used_up(use_fake_gemini):
    """When one model's daily free limit is used up, the next model is used"""
    fake = use_fake_gemini(gemini_error(429, retry_delay="7717s"), GOOD_ANSWER, models=["model-a", "model-b"])

    result = extract(INVOICE_TEXT)

    assert [call["model"] for call in fake.calls] == ["model-a", "model-b"]
    assert result["model"] == "model-b"


def test_a_used_up_model_is_not_asked_again(use_fake_gemini):
    """Remembers a used-up model, so the next invoices go straight to the next model"""
    fake = use_fake_gemini(gemini_error(429, retry_delay="7717s"), GOOD_ANSWER, GOOD_ANSWER,
                           models=["model-a", "model-b"])

    extract(INVOICE_TEXT)
    extract(INVOICE_TEXT)

    assert [call["model"] for call in fake.calls] == ["model-a", "model-b", "model-b"]


def test_all_models_used_up_says_when_to_try_again(use_fake_gemini):
    """When every model's daily limit is used up, says so and gives the soonest time to try again"""
    use_fake_gemini(gemini_error(429, retry_delay="7717s"), gemini_error(429, retry_delay="3600s"),
                    models=["model-a", "model-b"])

    with pytest.raises(ValueError, match=r"used up for today on every model we use \(2\). Try again in about 1 h 0 min"):
        extract(INVOICE_TEXT)


def test_busy_model_is_skipped_after_its_retries(use_fake_gemini):
    """When a model stays busy after its retries, the next model is used"""
    fake = use_fake_gemini(*[gemini_error(503)] * 4, GOOD_ANSWER, models=["model-a", "model-b"])

    result = extract(INVOICE_TEXT)

    assert result["model"] == "model-b"
    assert len(fake.calls) == 5


def test_model_that_no_longer_exists_is_skipped(use_fake_gemini):
    """A model that Google has removed (404) is skipped, without retrying it"""
    fake = use_fake_gemini(gemini_error(404), GOOD_ANSWER, models=["old-model", "model-b"])

    result = extract(INVOICE_TEXT)

    assert [call["model"] for call in fake.calls] == ["old-model", "model-b"]
    assert result["model"] == "model-b"


def test_models_can_be_chosen_in_the_env_file(use_fake_gemini, monkeypatch):
    """The models to use can be set with GEMINI_MODELS in AI/.env"""
    fake = use_fake_gemini(GOOD_ANSWER)
    monkeypatch.setenv("GEMINI_MODELS", "my-model, my-backup-model")

    result = extract(INVOICE_TEXT)

    assert fake.calls[0]["model"] == "my-model"
    assert result["model"] == "my-model"


def test_invalid_api_key_is_not_retried(use_fake_gemini):
    """An invalid API key gives a clear message at once, without retrying"""
    fake = use_fake_gemini(gemini_error(403))

    with pytest.raises(ValueError, match="API key is not valid"):
        extract(INVOICE_TEXT)
    assert len(fake.calls) == 1


def test_one_broken_answer_is_retried(use_fake_gemini):
    """Asks again once when the AI's answer is not in the expected format"""
    fake = use_fake_gemini(None, GOOD_ANSWER)

    result = extract(INVOICE_TEXT)

    assert len(fake.calls) == 2
    assert result["fields"]["total"]["value"] == "$1,150.00"


def test_two_broken_answers_give_a_clear_message(use_fake_gemini):
    """Gives a clear message when the AI's answer is broken twice"""
    use_fake_gemini(None, None)

    with pytest.raises(ValueError, match="did not answer in the expected format"):
        extract(INVOICE_TEXT)


def test_missing_api_key(monkeypatch):
    """Gives a clear message when GEMINI_API_KEY is not set"""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="GEMINI_API_KEY is missing"):
        extract(INVOICE_TEXT)


# ---------- Step 3: checking the evidence ("trust, but verify") ----------

def answer_with(**changes) -> dict:
    """GOOD_ANSWER as returned by extract(), with some fields changed."""
    fields = {name: dict(value) for name, value in GOOD_ANSWER.items() if name != "line_items"}
    fields.update(changes)
    return {"fields": fields, "line_items": [dict(item) for item in GOOD_ANSWER["line_items"]]}


def test_real_evidence_passes():
    """Values whose evidence is really in the document pass the check"""
    assert check_evidence(answer_with(), INVOICE_TEXT) == {}


def test_spaces_line_breaks_and_capitals_do_not_matter():
    """Small differences in spaces, line breaks or capital letters do not fail the check"""
    invoice = answer_with(supplier_name=field("Acme Trading Ltd", "acme   trading\nltd"))

    assert check_evidence(invoice, INVOICE_TEXT) == {}


def test_invented_evidence_is_caught():
    """Catches a value whose evidence is not in the document (an invented value)"""
    invoice = answer_with(customer_name=field("Green Leaf Ltd", "Bill to: Green Leaf Ltd"))

    assert check_evidence(invoice, INVOICE_TEXT) == {
        "customer_name": "the AI's evidence was not found in the document"}


def test_changed_value_with_real_evidence_is_caught():
    """Catches a value that was changed, even when its evidence is real"""
    invoice = answer_with(total=field("$1,500.00", "Total: $1,150.00"))

    assert check_evidence(invoice, INVOICE_TEXT) == {"total": "the value is not in the AI's evidence"}


def test_value_without_evidence_is_caught():
    """Catches a value given without any evidence"""
    invoice = answer_with(tax=field("150.00", None))

    assert check_evidence(invoice, INVOICE_TEXT) == {"tax": "the AI gave no evidence for this value"}


def test_missing_values_are_not_problems():
    """A field the AI left empty (null) is not an evidence problem"""
    invoice = answer_with(customer_name=field(None, None))

    assert check_evidence(invoice, INVOICE_TEXT) == {}


def test_line_items_are_checked_too():
    """Checks the line items as well"""
    invoice = answer_with()
    invoice["line_items"][0]["amount"] = "9,999.00"

    assert check_evidence(invoice, INVOICE_TEXT) == {"line item 1 amount": "the value is not in the AI's evidence"}


# ---------- a few checks with the real Gemini (only run with --real-gemini) ----------

@pytest.mark.real_gemini
def test_real_gemini_reads_a_complete_invoice():
    """Real Gemini: reads every field of a complete invoice, all with real evidence"""
    result = extract(INVOICE_TEXT)

    values = {name: answer["value"] for name, answer in result["fields"].items()}
    assert values["invoice_number"] == "INV-2026-001"
    assert values["customer_name"] == "Blue Sky Foods"
    # The AI may write the total as "$1,150.00" or "1,150.00" (the "$" is in the currency field);
    # both are right. We check what matters: the cleaned amount.
    assert clean_amount(values["total"])[0] == "1150.00"
    assert clean_amount(values["tax"])[0] == "150.00"
    assert clean_currency(values["currency"])[0] == "USD"
    assert check_evidence(result, INVOICE_TEXT) == {}


@pytest.mark.real_gemini
def test_real_gemini_does_not_invent_missing_values():
    """Real Gemini: leaves missing fields empty and does not calculate a total that is not written"""
    receipt = "--- Page 1 ---\nReceipt\nInvoice No: R-77\nCoffee beans   2 x 12.50   25.00\nMilk   1 x 3.00   3.00"

    result = extract(receipt)

    values = {name: answer["value"] for name, answer in result["fields"].items()}
    assert values["total"] is None  # 25.00 + 3.00 = 28.00, but no total is written
    assert values["supplier_name"] is None
    assert values["customer_name"] is None
    assert values["invoice_date"] is None
    assert check_evidence(result, receipt) == {}
