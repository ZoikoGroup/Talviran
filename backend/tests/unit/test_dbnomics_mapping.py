"""Unit tests for the DBnomics macro-series parser, against real fixtures
(tests/fixtures/dbnomics_india_*.json, captured 2026-09-18 from
DBnomics' live, public, unauthenticated /series endpoint for World Bank
WDI) — proof the parser handles the real response shape, not an invented
one.
"""

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

from app.modules.market.connectors.dbnomics_macro.mapping import (
    MacroObservationCandidate,
    RecordIssue,
    parse_series_response,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _load(name: str) -> object:
    return json.loads((FIXTURES_DIR / name).read_bytes())


def test_parses_india_gdp_from_real_fixture() -> None:
    # DBnomics' `observations=1` param means "include observations data"
    # (a boolean flag), not "limit to 1" — a real response carries the
    # series' full available history, same as the BoE curve feed returns
    # every published date and leaves "pick the latest" to the caller.
    candidates = parse_series_response(_load("dbnomics_india_gdp.json"))
    assert len(candidates) == 64
    assert all(isinstance(c, MacroObservationCandidate) for c in candidates)

    latest = candidates[-1]
    assert isinstance(latest, MacroObservationCandidate)
    assert latest.provider_code == "WB"
    assert latest.dataset_code == "WDI"
    assert latest.series_code == "A-NY.GDP.MKTP.CD-IND"
    assert latest.period == "2023"
    assert latest.period_start_day == dt.date(2023, 1, 1)
    assert latest.period_end_day == dt.date(2024, 1, 1)
    assert latest.value == Decimal("3549918918777.53")

    earliest = candidates[0]
    assert isinstance(earliest, MacroObservationCandidate)
    assert earliest.period == "1960"


def test_parses_india_cpi_from_real_fixture() -> None:
    candidates = parse_series_response(_load("dbnomics_india_cpi.json"))
    assert len(candidates) > 0
    assert all(
        isinstance(c, MacroObservationCandidate) and c.series_code == "A-FP.CPI.TOTL.ZG-IND"
        for c in candidates
    )


def test_missing_series_docs_is_a_record_issue_not_a_crash() -> None:
    result = parse_series_response({"message": "Series not found"})
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "no series.docs found" in result[0].reason


def test_empty_docs_is_a_record_issue() -> None:
    result = parse_series_response({"series": {"docs": []}})
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)


def test_unsupported_frequency_is_a_record_issue_not_a_guessed_span() -> None:
    doc = {
        "@frequency": "quarterly",
        "provider_code": "WB",
        "dataset_code": "WDI",
        "series_code": "SOME-QUARTERLY-SERIES",
        "period": ["2023-Q1"],
        "period_start_day": ["2023-01-01"],
        "value": [1.0],
    }
    result = parse_series_response({"series": {"docs": [doc]}})
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "unsupported frequency" in result[0].reason


def test_parallel_array_length_mismatch_is_a_record_issue() -> None:
    doc = {
        "@frequency": "annual",
        "provider_code": "WB",
        "dataset_code": "WDI",
        "series_code": "X",
        "period": ["2022", "2023"],
        "period_start_day": ["2022-01-01", "2023-01-01"],
        "value": [1.0],
    }
    result = parse_series_response({"series": {"docs": [doc]}})
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "length mismatch" in result[0].reason


def test_null_value_is_a_record_issue_not_a_guess() -> None:
    doc = {
        "@frequency": "annual",
        "provider_code": "WB",
        "dataset_code": "WDI",
        "series_code": "X",
        "period": ["2023"],
        "period_start_day": ["2023-01-01"],
        "value": [None],
    }
    result = parse_series_response({"series": {"docs": [doc]}})
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert result[0].raw_period == "2023"
    assert "null value" in result[0].reason


def test_one_bad_observation_does_not_drop_the_others() -> None:
    doc = {
        "@frequency": "annual",
        "provider_code": "WB",
        "dataset_code": "WDI",
        "series_code": "X",
        "period": ["2022", "2023"],
        "period_start_day": ["2022-01-01", "2023-01-01"],
        "value": [100.0, None],
    }
    result = parse_series_response({"series": {"docs": [doc]}})
    assert len(result) == 2
    assert isinstance(result[0], MacroObservationCandidate)
    assert isinstance(result[1], RecordIssue)
