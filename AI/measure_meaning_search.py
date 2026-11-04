"""Measures how well meaning search works, with the real Gemini embedding model.

Why: meaning search must decide which invoices are "close enough" to the search words
(MIN_SIMILARITY and MAX_GAP in backend/controllers/search.controller.ts). We chose those numbers
from the scores this script measures, instead of guessing.

What it does: 12 made-up invoice summaries (in the same form as backend/lib/embeddings.ts makes them)
and 12 searches, where we wrote down which invoices are the right answers. It prints the scores and
how many right and wrong answers each cut-off rule keeps.

Uses 2 Gemini embedding requests (one for all invoices, one for all searches).

    uv run python measure_meaning_search.py
"""

import math

from embed_text import embed_texts

# Made-up sample invoices (no real data): "From: supplier. Bought: line items"
INVOICES = {
    "furniture": "From: Acme Office Supplies. Bought: Office chairs; Desk lamps; Filing cabinet",
    "internet": "From: FastNet. Bought: Broadband internet, October; Router rental",
    "phone": "From: CityMobile. Bought: Mobile phone plan, 5 lines; Roaming charges",
    "electricity": "From: Green Power Co. Bought: Electricity usage September; Standing charge",
    "coffee": "From: Bean There Roasters. Bought: Arabica coffee beans 5kg; Oat milk",
    "cleaning": "From: Sparkle Cleaning Ltd. Bought: Office cleaning, weekly; Window washing",
    "software": "From: CloudSoft Inc. Bought: Accounting software subscription, annual",
    "laptops": "From: TechWorld. Bought: Laptop 14 inch x3; USB-C docking station",
    "travel": "From: SkyHigh Travel. Bought: Flight Dhaka to Singapore; Hotel 2 nights",
    "printing": "From: PrintHub. Bought: Business cards 500; Flyers A5 2000",
    "legal": "From: Rahman & Co Solicitors. Bought: Legal advice, contract review",
    "rent": "From: Gulshan Properties. Bought: Office rent, November",
}

# The search words, and the invoices that are right answers
SEARCHES = {
    "office furniture": ["furniture"],
    "chairs": ["furniture"],
    "internet bill": ["internet"],
    "telecom": ["internet", "phone"],
    "utilities": ["electricity", "internet"],
    "coffee": ["coffee"],
    "food and drinks": ["coffee"],
    "computers": ["laptops"],
    "business trip": ["travel"],
    "marketing materials": ["printing"],
    "lawyer": ["legal"],
    "cleaning services": ["cleaning"],
}

MIN_SIMILARITY = 0.58  # the same numbers as in backend/controllers/search.controller.ts
MAX_GAP = 0.03


def closeness(a: list[float], b: list[float]) -> float:
    """Cosine similarity: 1 = the same meaning, 0 = unrelated. Postgres (pgvector) uses the same idea."""
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def main():
    names = list(INVOICES)
    invoices = embed_texts([INVOICES[name] for name in names], "document")
    searches = embed_texts(list(SEARCHES), "search")
    print(f"Model: {invoices['model']}\n")
    print("The 4 closest invoices for each search (* = a right answer):")

    right, wrong = [], []  # (score, how far below the best result)
    first_is_right = 0
    for (words, answers), search in zip(SEARCHES.items(), searches["embeddings"]):
        scores = sorted(((closeness(search, numbers), name) for name, numbers in zip(names, invoices["embeddings"])),
                        reverse=True)
        best = scores[0][0]
        first_is_right += scores[0][1] in answers
        for score, name in scores:
            (right if name in answers else wrong).append((score, best - score))
        print(f"  {words:22}" + "  ".join(f"{name}={score:.3f}{'*' if name in answers else ''}" for score, name in scores[:4]))

    print(f"\nThe right invoice was first in {first_is_right} of {len(SEARCHES)} searches.")
    print(f"Right answers score {min(r[0] for r in right):.3f} to {max(r[0] for r in right):.3f}; "
          f"the best wrong answer scores {max(w[0] for w in wrong):.3f}.\n")
    rules = [
        ("score >= 0.58", lambda score, gap: score >= 0.58),
        ("score >= 0.60", lambda score, gap: score >= 0.60),
        ("within 0.03 of the best", lambda score, gap: gap <= 0.03),
        (f"score >= {MIN_SIMILARITY} AND within {MAX_GAP} of the best (used)",
         lambda score, gap: score >= MIN_SIMILARITY and gap <= MAX_GAP),
    ]
    print(f"{'Rule':52} {'right answers kept':>20} {'wrong answers shown':>20}")
    for title, keep in rules:
        kept_right = sum(keep(score, gap) for score, gap in right)
        kept_wrong = sum(keep(score, gap) for score, gap in wrong)
        print(f"{title:52} {f'{kept_right}/{len(right)}':>20} {f'{kept_wrong}/{len(wrong)}':>20}")


if __name__ == "__main__":
    main()
