"""Task 5, meaning search: turn text into an "embedding", a list of 768 numbers that describes its meaning.
Texts with a similar meaning get similar numbers, so "office furniture" ends up close to "chairs".

We use Gemini's embedding model. It has its own free daily limit, separate from the models that read
invoices, so searching doesn't use up the requests we need for extraction.
"""

import logging
import os
import time

from google.genai import errors, types

# The client, waits and helpers are the same as for reading invoices
from extract_invoice import (LONGEST_WAIT_SECONDS, RETRY_WAIT_SECONDS, TEMPORARY_ERRORS, make_client, readable_wait,
                             wait_time_from_gemini)

logger = logging.getLogger(__name__)

# Override with GEMINI_EMBEDDING_MODEL in AI/.env
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"

# 768 numbers per text: the size the database column has (vector(768)). The model can give more (3072),
# but 768 is much smaller to store and search, and works almost as well.
EMBEDDING_SIZE = 768

# How many texts at most in one request (one request can embed many texts, which saves requests)
MAX_TEXTS = 100
# The model reads at most about 2,000 tokens (~8,000 characters). Longer texts are cut.
MAX_TEXT_CHARACTERS = 8_000

# "document" = the text of an invoice, to be stored. "search" = the words a person searches for.
# The model makes slightly different numbers for each, which makes searching work better.
TASK_TYPES = {"document": "RETRIEVAL_DOCUMENT", "search": "RETRIEVAL_QUERY"}

# When the daily limit is used up: the time (time.time()) when we can ask again
used_up_until = 0.0


class EmbeddingNotAvailable(Exception):
    """Gemini can't make embeddings right now (limit used up, busy, or no key). Trying later can work."""


def embed_texts(texts: list[str], purpose: str = "document") -> dict:
    """Turn each text into 768 numbers. Returns {"model": ..., "embeddings": [[...768 numbers], ...]},
    in the same order as the texts. Raises ValueError for wrong input and EmbeddingNotAvailable
    when Gemini can't do it right now."""
    global used_up_until
    check_input(texts, purpose)
    if used_up_until > time.time():  # we already know the limit is used up: don't even ask
        raise used_up_error(used_up_until - time.time())

    try:
        client = make_client()
    except ValueError as error:  # no key in AI/.env
        raise EmbeddingNotAvailable(str(error))

    model = os.environ.get("GEMINI_EMBEDDING_MODEL", "").strip() or DEFAULT_EMBEDDING_MODEL
    config = types.EmbedContentConfig(task_type=TASK_TYPES[purpose], output_dimensionality=EMBEDDING_SIZE)
    contents = [text[:MAX_TEXT_CHARACTERS] for text in texts]

    attempt = 0
    while True:
        try:
            response = client.models.embed_content(model=model, contents=contents, config=config)
            break
        except errors.APIError as error:
            gemini_wait = wait_time_from_gemini(error)
            if error.code == 429 and gemini_wait is not None and gemini_wait > LONGEST_WAIT_SECONDS:
                used_up_until = time.time() + gemini_wait
                raise used_up_error(gemini_wait)
            if error.code in TEMPORARY_ERRORS and attempt < len(RETRY_WAIT_SECONDS):
                wait = max(RETRY_WAIT_SECONDS[attempt], gemini_wait or 0)
                logger.warning("Gemini %s: error %s, trying again in %s seconds", model, error.code, wait)
                time.sleep(wait)
                attempt += 1
                continue
            raise EmbeddingNotAvailable(explain_error(error, model))

    embeddings = [list(embedding.values or []) for embedding in response.embeddings or []]
    # Never store half an answer: we need exactly one list of 768 numbers per text
    if len(embeddings) != len(texts) or any(len(numbers) != EMBEDDING_SIZE for numbers in embeddings):
        raise EmbeddingNotAvailable("Meaning search is not available: the AI gave an unexpected answer")
    return {"model": model, "embeddings": embeddings}


def check_input(texts, purpose):
    if purpose not in TASK_TYPES:
        raise ValueError('purpose must be "document" or "search"')
    if not isinstance(texts, list) or not texts:
        raise ValueError("Give at least one text")
    if len(texts) > MAX_TEXTS:
        raise ValueError(f"Give at most {MAX_TEXTS} texts at a time")
    for number, text in enumerate(texts, start=1):
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Text {number} is empty")


def used_up_error(wait_seconds: float) -> EmbeddingNotAvailable:
    return EmbeddingNotAvailable("Meaning search is not available: the free Gemini limit for embeddings is used up "
                                 f"for today. Try again in about {readable_wait(wait_seconds)}.")


def explain_error(error: errors.APIError, model: str) -> str:
    if error.code in (401, 403) or (error.code == 400 and "API key" in str(error)):
        return "Meaning search is not available: the Gemini API key is not valid. Check GEMINI_API_KEY in AI/.env."
    if error.code == 404:
        return f"Meaning search is not available: the model {model} is not available"
    if error.code == 429:
        return "Meaning search is not available: the free Gemini limit was reached. Try again later."
    if error.code in TEMPORARY_ERRORS:
        return "Meaning search is not available: Gemini is busy. Try again later."
    return f"Meaning search is not available: Gemini returned error {error.code}"
