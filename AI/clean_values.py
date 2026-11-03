"""Turn values written in many styles into one standard form.

Every function returns (value, problem):
- value:   the cleaned value, or None if it can't be read safely
- problem: None if all is fine, otherwise a short message explaining what is doubtful
We never guess: when something is unclear, we say so in the problem message."""

import datetime
import re
from decimal import Decimal, InvalidOperation

# ---------- amounts ----------

# A number: digits, possibly with "," or "." between them, e.g. "1,150.00", "99,99", "1150".
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def clean_amount(text: str | None, money: bool = True) -> tuple[str | None, str | None]:
    """Turn an amount like "$1,150.00", "1.150,00 €", "(150)" or "99,99" into an exact number as text
    ("1150.00"). money=True writes at least 2 decimals; use money=False for quantities."""
    if text is None or not text.strip():
        return None, None

    # "1 150 000,00": a space between groups of 3 digits is a thousands separator, so remove it.
    joined = re.sub(r"(?<=\d) (?=\d{3}\b)", "", text)
    numbers = list(NUMBER.finditer(joined))
    if not numbers:
        return None, f"'{text}' is not an amount"

    first = numbers[0]
    before, after = joined[:first.start()], joined[first.end():]
    try:
        amount = Decimal(remove_thousands_separators(first.group()))
    except InvalidOperation:
        return None, f"'{text}' is not an amount"

    # A minus sign or brackets around the number make it negative: "-$20", "(150.00)", "$(150.00)".
    # The sign must touch the number (or its currency sign): "Total - 150.00" is not negative.
    just_before = before.rstrip("$€£¥₹৳")
    if just_before.endswith("-") or (just_before.endswith("(") and after.startswith(")")):
        amount = -amount
    if money and amount.as_tuple().exponent > -2:  # 1150 -> 1150.00, but 1.2345 stays as it is
        amount = amount.quantize(Decimal("0.01"))

    # "1,150.00 (incl. 15% VAT)": we use the first number, but someone should check it.
    problem = f"'{text}' has more than one number; the first one was used" if len(numbers) > 1 else None
    return str(amount), problem


def remove_thousands_separators(number: str) -> str:
    """Return the number with "." as the decimal point and no thousands separators."""
    commas, dots = number.count(","), number.count(".")

    if commas and dots:
        # Both are used: the one that comes last is the decimal point.
        #   "1,150.00" -> 1150.00     "1.150,00" -> 1150.00
        decimal_point = "," if number.rfind(",") > number.rfind(".") else "."
        thousands = "." if decimal_point == "," else ","
        return number.replace(thousands, "").replace(decimal_point, ".")

    separator = "," if commas else "." if dots else None
    if separator is None:
        return number
    if number.count(separator) > 1:  # "1,000,000" or "1.000.000": only thousands separators
        return number.replace(separator, "")

    # Only one separator. Exactly 3 digits after it means thousands ("1,150" -> 1150);
    # 1 or 2 digits mean decimals ("99,99" -> 99.99). Money almost never has 3 decimals.
    digits_after = len(number) - number.index(separator) - 1
    if digits_after == 3:
        return number.replace(separator, "")
    return number.replace(separator, ".")


# ---------- dates ----------

# Written-out dates we understand, e.g. "15 Oct 2026", "October 15, 2026", "15-Oct-2026".
DATE_FORMATS = ["%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y", "%d-%b-%Y", "%d-%B-%Y"]

# Dates made only of numbers, e.g. "15/10/2026", "10-15-26", "15.10.2026".
NUMBER_DATE = re.compile(r"^(\d{1,2})([./-])(\d{1,2})[./-](\d{2}|\d{4})$")


def clean_date(text: str | None) -> tuple[str | None, str | None]:
    """Turn a date like "15/10/2026", "Oct 15th, 2026" or "2026-10-15 14:30:00" into "2026-10-15"."""
    if text is None or not text.strip():
        return None, None

    simple = text.strip()
    simple = re.sub(r"[ T]\d{1,2}:\d{2}(:\d{2})?$", "", simple)  # drop a time at the end
    simple = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", simple, flags=re.IGNORECASE)  # "15th" -> "15"
    simple = re.sub(r"([A-Za-z])\.", r"\1", simple)  # "Oct." -> "Oct"
    simple = re.sub(r"\bSept\b", "Sep", simple, flags=re.IGNORECASE)  # Python only knows "Sep"
    simple = " ".join(simple.replace(",", " ").split())  # "Oct 15, 2026" -> "Oct 15 2026"

    for date_format in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(simple, date_format).date().isoformat(), None
        except ValueError:
            pass

    match = NUMBER_DATE.match(simple)
    if match is None:
        return None, f"'{text}' is not a date we can read"
    return clean_number_date(text, int(match[1]), match[2], int(match[3]), match[4])


def clean_number_date(text: str, first: int, separator: str, second: int, year_text: str):
    year = int(year_text) + 2000 if len(year_text) == 2 else int(year_text)  # "26" -> 2026

    if separator == ".":  # "15.10.2026": dots are only used with the day first
        day, month = first, second
    elif first > 12:  # "15/10/2026": 15 can't be a month, so the day is first
        day, month = first, second
    elif second > 12:  # "10/15/2026": 15 can't be a month, so the month is first (US style)
        day, month = second, first
    elif first == second:  # "05/05/2026": the same either way
        day, month = first, second
    else:  # "03/04/2026": 3 April or 4 March? We don't guess.
        return None, f"'{text}' is unclear: the day and month could be either way round"

    try:
        return datetime.date(year, month, day).isoformat(), None
    except ValueError:
        return None, f"'{text}' is not a real date"


# ---------- currency ----------

CURRENCY_CODES = ["USD", "EUR", "GBP", "BDT", "INR", "PKR", "JPY", "CNY", "AUD", "CAD", "CHF", "SGD",
                  "AED", "SAR", "MYR", "THB", "NZD", "SEK", "NOK", "DKK"]

# Symbols and words that clearly mean one currency. Longer ones first, so "US$" wins over "$".
CURRENCY_SIGNS = [("US$", "USD"), ("C$", "CAD"), ("A$", "AUD"), ("S$", "SGD"), ("€", "EUR"), ("£", "GBP"),
                  ("৳", "BDT"), ("₹", "INR"), ("taka", "BDT"), ("tk", "BDT"), ("euro", "EUR")]


def clean_currency(text: str | None) -> tuple[str | None, str | None]:
    """Find the currency in a text like "USD", "$1,150.00", "1.150,00 €" or "Tk 500" and return its code."""
    if text is None or not text.strip():
        return None, None

    for code in CURRENCY_CODES:
        if is_separate_word(code, text):
            return code, None

    for sign, code in CURRENCY_SIGNS:
        if sign.isalpha():  # a word like "Tk"
            if is_separate_word(sign, text):
                return code, None
        elif sign in text:
            return code, None

    if "$" in text:
        return "USD", "a '$' alone could also be Canadian, Australian or another dollar"
    if "¥" in text:
        return None, "'¥' is used by both Japan (JPY) and China (CNY)"
    return None, None


def is_separate_word(word: str, text: str) -> bool:
    """True if the word is in the text and not part of a longer word. Digits may touch it:
    "USD1,150" and "Tk500" count, but "EURO" doesn't count as "EUR" and "Tkt" doesn't count as "Tk"."""
    return re.search(rf"(?<![A-Za-z]){word}(?![A-Za-z])", text, re.IGNORECASE) is not None


# ---------- plain text (names, invoice numbers, descriptions) ----------


def clean_text(text: str | None) -> tuple[str | None, str | None]:
    """Remove extra spaces and line breaks: "  Acme \\n Trading  Ltd " -> "Acme Trading Ltd"."""
    if text is None:
        return None, None
    simple = " ".join(text.split())
    return (simple or None), None
