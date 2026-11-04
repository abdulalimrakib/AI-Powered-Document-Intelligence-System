"""Step 4 — Turning text into meaning numbers (embeddings) for meaning search (POST /embed)"""

import math

import pytest
from fastapi.testclient import TestClient
from google.genai import errors

import embed_text
from embed_text import EMBEDDING_SIZE, EmbeddingNotAvailable, embed_texts
from main import app

client = TestClient(app)


# ---------- a fake Gemini, so these tests are free, fast and work without internet ----------

class FakeEmbedding:
    def __init__(self, values):
        self.values = values


class FakeResponse:
    def __init__(self, embeddings):
        self.embeddings = embeddings


class FakeGemini:
    """Gives the planned answers one by one. An answer is "numbers" (768 numbers per text),
    an error, or a list of embeddings (to test a broken answer)."""

    def __init__(self, *answers):
        self.answers = list(answers) or ["numbers"]
        self.calls = []
        self.models = self  # the real client is used as client.models.embed_content(...)

    def embed_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        if answer == "numbers":  # text number i gets [i, i, i, ...], so the order can be checked
            return FakeResponse([FakeEmbedding([float(i)] * EMBEDDING_SIZE) for i in range(len(contents))])
        return FakeResponse(answer)


def gemini_error(code: int, retry_delay: str | None = None, message: str = "test error") -> errors.APIError:
    """An error like the real Gemini sends. A 429 can say how long to wait, e.g. retry_delay="7717s"."""
    details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay}] if retry_delay else []
    error_class = errors.ClientError if code < 500 else errors.ServerError
    return error_class(code, {"error": {"code": code, "message": message, "details": details}})


@pytest.fixture
def use_fake_gemini(monkeypatch):
    """Replace the real Gemini with a fake one, and skip the real waiting between retries."""
    waits = []

    def install(*answers):
        fake = FakeGemini(*answers)
        fake.waits = waits
        monkeypatch.setattr(embed_text, "make_client", lambda: fake)
        monkeypatch.setattr(embed_text.time, "sleep", waits.append)
        monkeypatch.setattr(embed_text, "used_up_until", 0.0)  # every test starts fresh
        monkeypatch.delenv("GEMINI_EMBEDDING_MODEL", raising=False)
        return fake
    return install


# ---------- making embeddings ----------

def test_gives_768_numbers_for_each_text_in_order(use_fake_gemini):
    """Gives 768 numbers for each text, in the same order as the texts, and says which model made them"""
    use_fake_gemini()

    result = embed_texts(["Acme Ltd, office chairs", "FastNet, broadband"])

    assert result["model"] == "gemini-embedding-001"
    assert [len(numbers) for numbers in result["embeddings"]] == [768, 768]
    assert [numbers[0] for numbers in result["embeddings"]] == [0.0, 1.0]  # text 1 first, then text 2


def test_sends_all_texts_in_one_request(use_fake_gemini):
    """Sends all texts in one request (this saves free requests), asking for 768 numbers"""
    fake = use_fake_gemini()

    embed_texts(["one", "two", "three"])

    assert len(fake.calls) == 1
    assert fake.calls[0]["contents"] == ["one", "two", "three"]
    assert fake.calls[0]["config"].output_dimensionality == 768


@pytest.mark.parametrize("purpose, task_type", [
    pytest.param("document", "RETRIEVAL_DOCUMENT", id="an invoice to store"),
    pytest.param("search", "RETRIEVAL_QUERY", id="the words of a search"),
])
def test_tells_gemini_what_the_text_is_for(use_fake_gemini, purpose, task_type):
    """Tells Gemini whether the text is an invoice to store or the words of a search"""
    fake = use_fake_gemini()

    embed_texts(["office furniture"], purpose)

    assert fake.calls[0]["config"].task_type == task_type


def test_uses_the_model_from_the_settings(use_fake_gemini, monkeypatch):
    """Uses the model set in GEMINI_EMBEDDING_MODEL (AI/.env) when there is one"""
    fake = use_fake_gemini()
    monkeypatch.setenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2")

    result = embed_texts(["office chairs"])

    assert fake.calls[0]["model"] == "gemini-embedding-2"
    assert result["model"] == "gemini-embedding-2"


def test_cuts_a_very_long_text(use_fake_gemini):
    """Cuts a very long text to what the model can read"""
    fake = use_fake_gemini()

    embed_texts(["x" * 20_000])

    assert len(fake.calls[0]["contents"][0]) == embed_text.MAX_TEXT_CHARACTERS


# ---------- when Gemini has a problem ----------

@pytest.mark.parametrize("error", [
    pytest.param(gemini_error(503), id="busy"),
    pytest.param(gemini_error(429, "7s"), id="per-minute limit"),
])
def test_waits_and_tries_again(use_fake_gemini, error):
    """Waits and tries again when Gemini is busy or the per-minute limit is reached"""
    fake = use_fake_gemini(error, "numbers")

    result = embed_texts(["office chairs"])

    assert len(result["embeddings"]) == 1
    assert len(fake.calls) == 2
    assert fake.waits[0] >= 5


def test_gives_up_when_gemini_stays_busy(use_fake_gemini):
    """Gives up with a clear message when Gemini stays busy after all retries"""
    fake = use_fake_gemini(*[gemini_error(503)] * 4)

    with pytest.raises(EmbeddingNotAvailable, match="Gemini is busy. Try again later."):
        embed_texts(["office chairs"])
    assert len(fake.calls) == 4  # the first try + 3 retries


def test_stops_at_once_when_the_daily_limit_is_used_up(use_fake_gemini):
    """Stops at once when the daily limit is used up, says when to try again, and doesn't ask again"""
    fake = use_fake_gemini(gemini_error(429, "7717s"))

    with pytest.raises(EmbeddingNotAvailable, match="used up for today. Try again in about 2 h 9 min"):
        embed_texts(["office chairs"])
    with pytest.raises(EmbeddingNotAvailable, match="used up for today"):
        embed_texts(["office chairs"])  # the second time Gemini is not asked at all
    assert len(fake.calls) == 1
    assert fake.waits == []  # no waiting: waiting hours would be pointless


@pytest.mark.parametrize("error, message", [
    pytest.param(gemini_error(400, message="API key not valid"), "the Gemini API key is not valid", id="wrong key"),
    pytest.param(gemini_error(404), "the model gemini-embedding-001 is not available", id="model removed"),
])
def test_explains_errors_that_retrying_cant_fix(use_fake_gemini, error, message):
    """Explains errors that trying again can't fix, without retrying"""
    fake = use_fake_gemini(error)

    with pytest.raises(EmbeddingNotAvailable, match=message):
        embed_texts(["office chairs"])
    assert len(fake.calls) == 1


def test_explains_a_missing_api_key(monkeypatch):
    """Explains a missing API key instead of crashing"""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(embed_text, "used_up_until", 0.0)

    with pytest.raises(EmbeddingNotAvailable, match="GEMINI_API_KEY is missing"):
        embed_texts(["office chairs"])


@pytest.mark.parametrize("answer", [
    pytest.param([FakeEmbedding([0.1] * 768)], id="one embedding for two texts"),
    pytest.param([FakeEmbedding([0.1] * 3), FakeEmbedding([0.1] * 3)], id="too few numbers"),
    pytest.param(None, id="no embeddings at all"),
])
def test_refuses_a_broken_answer(use_fake_gemini, answer):
    """Refuses a broken answer from Gemini, so nothing half-made is stored"""
    use_fake_gemini(answer)

    with pytest.raises(EmbeddingNotAvailable, match="unexpected answer"):
        embed_texts(["office chairs", "broadband"])


# ---------- wrong input ----------

@pytest.mark.parametrize("texts, purpose, message", [
    pytest.param([], "document", "Give at least one text", id="no texts"),
    pytest.param("office chairs", "document", "Give at least one text", id="text instead of a list"),
    pytest.param(["chairs", "  "], "document", "Text 2 is empty", id="an empty text"),
    pytest.param(["chairs", 5], "document", "Text 2 is empty", id="a number instead of a text"),
    pytest.param(["chairs"] * 101, "document", "Give at most 100 texts at a time", id="too many texts"),
    pytest.param(["chairs"], "invoice", 'purpose must be "document" or "search"', id="unknown purpose"),
])
def test_refuses_wrong_input(use_fake_gemini, texts, purpose, message):
    """Refuses wrong input with a clear message, without asking Gemini"""
    fake = use_fake_gemini()

    with pytest.raises(ValueError, match=message):
        embed_texts(texts, purpose)
    assert fake.calls == []


# ---------- the address the backend uses: POST /embed ----------

def test_api_gives_the_embeddings(use_fake_gemini):
    """POST /embed gives the model and the embeddings"""
    use_fake_gemini()

    response = client.post("/embed", json={"texts": ["office furniture"], "purpose": "search"})

    assert response.status_code == 200
    assert response.json()["model"] == "gemini-embedding-001"
    assert len(response.json()["embeddings"][0]) == 768


def test_api_refuses_wrong_input_with_400(use_fake_gemini):
    """POST /embed answers 400 with a clear message for wrong input"""
    use_fake_gemini()

    response = client.post("/embed", json={"texts": [""]})

    assert response.status_code == 400
    assert response.json() == {"detail": "Text 1 is empty"}


def test_api_answers_503_when_embeddings_are_not_available(use_fake_gemini):
    """POST /embed answers 503 (try again later) when Gemini can't make embeddings right now"""
    use_fake_gemini(gemini_error(429, "7717s"))

    response = client.post("/embed", json={"texts": ["office chairs"]})

    assert response.status_code == 503
    assert "used up for today" in response.json()["detail"]


# ---------- the real Gemini (only with --real-gemini) ----------

def closeness(a: list[float], b: list[float]) -> float:
    """Cosine similarity: 1 = the same meaning, 0 = unrelated. The database uses the same idea."""
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


@pytest.mark.real_gemini
def test_real_gemini_furniture_is_closer_to_chairs_than_to_internet():
    """Real Gemini: "office furniture" is closer in meaning to a chairs invoice than to an internet bill"""
    invoices = embed_texts([
        "Supplier: Acme Ltd. Customer: Blue Sky Foods. Bought: Office chairs, Desk lamps",
        "Supplier: FastNet. Customer: Blue Sky Foods. Bought: Broadband internet, October",
    ], "document")["embeddings"]
    search = embed_texts(["office furniture"], "search")["embeddings"][0]

    assert closeness(search, invoices[0]) > closeness(search, invoices[1])
