"""FIN-001's golden-test gate for gilt_treasury_spread_v1 — pure arithmetic
cases (not DMO/TreasuryDirect-sourced: this is Talvrin's own cross-market
comparison methodology, not a published formula). golden/v1/corpus.json is
versioned and never edited in place.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.modules.calculation.golden_manifest import verify_corpus_integrity
from app.modules.calculation.specs.gilt_treasury_spread_v1.implementation import (
    SpreadInputs,
    compute_spread,
)
from app.modules.calculation.specs.gilt_treasury_spread_v1.shadow_implementation import (
    compute_spread as shadow_compute_spread,
)

CORPUS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "modules"
    / "calculation"
    / "specs"
    / "gilt_treasury_spread_v1"
    / "golden"
    / "v1"
)
CORPUS_PATH = CORPUS_DIR / "corpus.json"
CORPUS = json.loads(CORPUS_PATH.read_text())

_TOLERANCE = Decimal("1E-9")


def test_corpus_v1_bytes_have_not_silently_changed() -> None:
    verify_corpus_integrity(CORPUS_DIR)


def _inputs_from_case(case: dict[str, Any]) -> SpreadInputs:
    return SpreadInputs(
        uk_yield_pct=Decimal(str(case["uk_yield_pct"])),
        us_yield_pct=Decimal(str(case["us_yield_pct"])),
    )


@pytest.mark.parametrize("case", CORPUS["spread_cases"], ids=lambda c: c["id"])
def test_spread_matches_expected(case: dict[str, Any]) -> None:
    result = compute_spread(_inputs_from_case(case))
    expected_pct = Decimal(str(case["expected_spread_pct"]))
    expected_bp = Decimal(str(case["expected_spread_bp"]))
    assert abs(result.spread_pct - expected_pct) < _TOLERANCE, case["id"]
    assert abs(result.spread_bp - expected_bp) < _TOLERANCE, case["id"]


@pytest.mark.parametrize("case", CORPUS["spread_cases"], ids=lambda c: c["id"])
def test_shadow_implementation_matches_expected(case: dict[str, Any]) -> None:
    """FIN-001's dual-implementation gate: the independently-derived
    (bp-space) implementation must ALSO reproduce the expected values, not
    just agree with the production implementation.
    """
    result = shadow_compute_spread(_inputs_from_case(case))
    expected_pct = Decimal(str(case["expected_spread_pct"]))
    assert abs(result.spread_pct - expected_pct) < _TOLERANCE, case["id"]


@pytest.mark.parametrize("case", CORPUS["spread_cases"], ids=lambda c: c["id"])
def test_production_and_shadow_implementations_agree(case: dict[str, Any]) -> None:
    inputs = _inputs_from_case(case)
    production = compute_spread(inputs)
    shadow = shadow_compute_spread(inputs)
    assert abs(production.spread_pct - shadow.spread_pct) < Decimal("1E-30"), case["id"]
    assert abs(production.spread_bp - shadow.spread_bp) < Decimal("1E-30"), case["id"]


def test_corpus_case_count_is_the_expected_6() -> None:
    assert len(CORPUS["spread_cases"]) == 6
