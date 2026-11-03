"""Step 4 — Cleaning amounts, dates and currencies into one standard form"""

import pytest

from clean_values import clean_amount, clean_currency, clean_date, clean_text


@pytest.mark.parametrize("text, expected", [
    pytest.param("1150", "1150.00", id="1150"),
    pytest.param("1,150.00", "1150.00", id="1,150.00 (US/UK style)"),
    pytest.param("1.150,00", "1150.00", id="1.150,00 (European style)"),
    pytest.param("$1,150.00", "1150.00", id="$1,150.00"),
    pytest.param("1.150,00 €", "1150.00", id="1.150,00 euro sign"),
    pytest.param("USD 99.99", "99.99", id="USD 99.99"),
    pytest.param("99,99", "99.99", id="99,99 (European decimal comma)"),
    pytest.param("1,150", "1150.00", id="1,150 (thousands)"),
    pytest.param("1.150", "1150.00", id="1.150 (European thousands)"),
    pytest.param("1,000,000", "1000000.00", id="1,000,000"),
    pytest.param("1 150,50", "1150.50", id="1 150,50 (space as thousands)"),
    pytest.param("150.5", "150.50", id="150.5 (as Excel gives it)"),
    pytest.param("(150.00)", "-150.00", id="(150.00) is negative"),
    pytest.param("$(150.00)", "-150.00", id="$(150.00) is negative"),
    pytest.param("-20", "-20.00", id="-20"),
    pytest.param("-$20", "-20.00", id="-$20"),
    pytest.param("Total - 150.00", "150.00", id="a dash with spaces is not a minus"),
    pytest.param("1 150 000,00", "1150000.00", id="1 150 000,00 (spaces as thousands)"),
    pytest.param("Total due 2,500.00", "2500.00", id="words around the amount"),
])
def test_cleans_amounts(text, expected):
    """Turns an amount into an exact number"""
    assert clean_amount(text) == (expected, None)


def test_amounts_stay_exact():
    """Keeps every digit: no rounding errors like 0.30000000000000004"""
    assert clean_amount("0.1")[0] == "0.10"
    assert clean_amount("1234567890.12")[0] == "1234567890.12"


def test_unit_prices_and_quantities_keep_their_decimals():
    """Keeps extra decimals of a unit price and does not add decimals to a quantity"""
    assert clean_amount("33.3333") == ("33.3333", None)
    assert clean_amount("10", money=False) == ("10", None)


@pytest.mark.parametrize("text", [
    pytest.param("N/A", id="N/A"),
    pytest.param("see attached", id="words only"),
])
def test_text_that_is_not_an_amount(text):
    """Gives no value and explains why when the text is not an amount"""
    value, problem = clean_amount(text)

    assert value is None
    assert "is not an amount" in problem


def test_amount_with_more_than_one_number_is_flagged():
    """Uses the first number when there are several, and says so (e.g. a VAT percentage next to the total)"""
    value, problem = clean_amount("1,150.00 (incl. 15% VAT)")

    assert value == "1150.00"
    assert "more than one number" in problem


def test_empty_amount():
    """An empty amount is simply missing (no value, no problem message)"""
    assert clean_amount(None) == (None, None)
    assert clean_amount("  ") == (None, None)


@pytest.mark.parametrize("text, expected", [
    pytest.param("2026-10-15", "2026-10-15", id="2026-10-15"),
    pytest.param("2026/10/15", "2026-10-15", id="2026/10/15"),
    pytest.param("2026-10-15 14:30:00", "2026-10-15", id="with a time (Excel)"),
    pytest.param("2026-10-15T00:00:00", "2026-10-15", id="with a T time (computer style)"),
    pytest.param("15 Oct. 2026", "2026-10-15", id="15 Oct. 2026 (dot after month)"),
    pytest.param("15 Sept 2026", "2026-09-15", id="15 Sept 2026"),
    pytest.param("15 Oct 2026", "2026-10-15", id="15 Oct 2026"),
    pytest.param("15 October 2026", "2026-10-15", id="15 October 2026"),
    pytest.param("Oct 15, 2026", "2026-10-15", id="Oct 15, 2026"),
    pytest.param("October 15th, 2026", "2026-10-15", id="October 15th, 2026"),
    pytest.param("15-Oct-2026", "2026-10-15", id="15-Oct-2026"),
    pytest.param("15/10/2026", "2026-10-15", id="15/10/2026 (day first)"),
    pytest.param("10/15/2026", "2026-10-15", id="10/15/2026 (month first, US)"),
    pytest.param("15.10.2026", "2026-10-15", id="15.10.2026 (dots)"),
    pytest.param("03.04.2026", "2026-04-03", id="03.04.2026 (dots are always day first)"),
    pytest.param("15/10/26", "2026-10-15", id="15/10/26 (two-digit year)"),
    pytest.param("05/05/2026", "2026-05-05", id="05/05/2026 (same either way)"),
])
def test_cleans_dates(text, expected):
    """Turns a date into the standard form YYYY-MM-DD"""
    assert clean_date(text) == (expected, None)


def test_unclear_date_is_not_guessed():
    """Does not guess a date that could be 3 April or 4 March"""
    value, problem = clean_date("03/04/2026")

    assert value is None
    assert "unclear" in problem


@pytest.mark.parametrize("text, problem_words", [
    pytest.param("31/02/2026", "not a real date", id="31 February"),
    pytest.param("next Tuesday", "not a date we can read", id="words"),
])
def test_impossible_or_unreadable_date(text, problem_words):
    """Gives no value and explains why for an impossible or unreadable date"""
    value, problem = clean_date(text)

    assert value is None
    assert problem_words in problem


@pytest.mark.parametrize("text, expected", [
    pytest.param("USD", "USD", id="USD"),
    pytest.param("usd", "USD", id="usd (small letters)"),
    pytest.param("Total: 1,150.00 EUR", "EUR", id="code inside a text"),
    pytest.param("1.150,00 €", "EUR", id="euro sign"),
    pytest.param("£ 20", "GBP", id="pound sign"),
    pytest.param("৳ 500", "BDT", id="taka sign"),
    pytest.param("Tk 500", "BDT", id="Tk"),
    pytest.param("US$ 10", "USD", id="US$"),
    pytest.param("C$ 10", "CAD", id="C$"),
    pytest.param("USD1,150.00", "USD", id="code touching the number"),
    pytest.param("1,150.00USD", "USD", id="code after the number"),
    pytest.param("Tk500", "BDT", id="Tk touching the number"),
])
def test_cleans_currencies(text, expected):
    """Finds the currency code"""
    assert clean_currency(text) == (expected, None)


def test_dollar_sign_alone_is_usd_but_uncertain():
    """A '$' alone gives USD, marked as uncertain"""
    value, problem = clean_currency("$1,150.00")

    assert value == "USD"
    assert "could also be" in problem


def test_yen_sign_is_not_guessed():
    """Does not guess between Japanese and Chinese currency for '¥'"""
    value, problem = clean_currency("¥ 5000")

    assert value is None
    assert "JPY" in problem and "CNY" in problem


def test_no_currency_found():
    """Gives no currency when the text has none"""
    assert clean_currency("1,150.00") == (None, None)


def test_currency_code_inside_a_longer_word_does_not_count():
    """Does not see a currency code hidden inside another word (e.g. 'Tkt' is not 'Tk')"""
    assert clean_currency("Tkt 12") == (None, None)


def test_cleans_text():
    """Removes extra spaces and line breaks from names"""
    assert clean_text("  Acme \n Trading   Ltd ") == ("Acme Trading Ltd", None)
    assert clean_text("   ") == (None, None)
