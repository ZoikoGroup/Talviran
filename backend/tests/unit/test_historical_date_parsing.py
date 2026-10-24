"""Unit tests for the historical-question date parser (evidence/service.py)
— pure string parsing, no DB dependency.
"""

import datetime as dt

from app.modules.evidence.service import _mentioned_historical_cutoff, _parse_mentioned_date


def test_parses_day_month_year() -> None:
    assert _parse_mentioned_date("15 September 2026") == dt.date(2026, 9, 15)


def test_parses_day_month_year_with_ordinal_suffix() -> None:
    assert _parse_mentioned_date("on the 15th September 2026") == dt.date(2026, 9, 15)


def test_parses_month_day_year_us_style() -> None:
    assert _parse_mentioned_date("September 15, 2026") == dt.date(2026, 9, 15)


def test_parses_month_day_year_without_comma() -> None:
    assert _parse_mentioned_date("Sept 15 2026") == dt.date(2026, 9, 15)


def test_parses_iso_date() -> None:
    assert _parse_mentioned_date("as of 2026-09-15") == dt.date(2026, 9, 15)


def test_rejects_bare_numeric_date_never_guesses_dd_mm_vs_mm_dd() -> None:
    # 15/09/2026 is genuinely ambiguous (UK DD/MM vs US MM/DD) - must not
    # be silently misread as either.
    assert _parse_mentioned_date("on 15/09/2026") is None


def test_rejects_invalid_calendar_date() -> None:
    assert _parse_mentioned_date("32 September 2026") is None
    assert _parse_mentioned_date("15 Notamonth 2026") is None


def test_mentioned_historical_cutoff_requires_trigger_phrase() -> None:
    # A date alone, with no historical-intent framing, is not a historical
    # question - e.g. an event date mentioned in passing about a live query.
    assert (
        _mentioned_historical_cutoff("AZN reported results on 15 September 2026, price now?")
        is None
    )


def test_mentioned_historical_cutoff_with_trigger_phrase() -> None:
    assert _mentioned_historical_cutoff(
        "What did Talvrin know on 15 September 2026?"
    ) == dt.date(2026, 9, 15)


def test_mentioned_historical_cutoff_as_of_phrasing() -> None:
    assert _mentioned_historical_cutoff("what was the yield curve as of 2026-09-15") == dt.date(
        2026, 9, 15
    )


def test_mentioned_historical_cutoff_no_date_returns_none() -> None:
    assert _mentioned_historical_cutoff("what did Talvrin know about gilts?") is None
