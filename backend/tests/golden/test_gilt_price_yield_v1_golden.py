"""FIN-001's golden-test gate for gilt_price_yield_v1: the production
implementation must reproduce DMO's own published worked examples exactly
(golden/v1/corpus.json — sourced from yldconv.pdf, not invented). A failure
here means the implementation has diverged from the DMO's own formula, not
just "a test changed" — this corpus is versioned and never edited in place.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.calculation.golden_manifest import verify_corpus_integrity
from app.modules.calculation.specs.gilt_price_yield_v1.implementation import (
    ConventionalGiltInputs,
    accrued_interest,
    dirty_price_from_yield,
    yield_from_price,
)
from app.modules.calculation.specs.gilt_price_yield_v1.shadow_implementation import (
    dirty_price_from_yield as shadow_dirty_price_from_yield,
)

CORPUS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "modules"
    / "calculation"
    / "specs"
    / "gilt_price_yield_v1"
    / "golden"
    / "v1"
)
CORPUS_PATH = CORPUS_DIR / "corpus.json"
CORPUS = json.loads(CORPUS_PATH.read_text())

_PRICE_TOLERANCE = Decimal("1E-6")
_YIELD_TOLERANCE = Decimal("1E-8")


def test_corpus_v1_bytes_have_not_silently_changed() -> None:
    # Checks corpus.json's checksum against golden/v1/manifest.json (see
    # app/modules/calculation/golden_manifest.py) rather than a hardcoded
    # constant here - this corpus is versioned and never edited in place
    # (the plan's own Week 12 requirement); a legitimate change means a new
    # golden/v2/ via scripts.propose_golden_corpus_version, not editing
    # this version's manifest to match.
    verify_corpus_integrity(CORPUS_DIR)


def _inputs_from_case(case: dict[str, object]) -> ConventionalGiltInputs:
    return ConventionalGiltInputs(
        coupon_per_100=Decimal(str(case["c"])),
        coupons_per_year=int(str(case["f"])),
        days_to_next_quasi_coupon=int(str(case["r"])),
        days_in_quasi_coupon_period=int(str(case["s"])),
        full_quasi_coupon_periods_remaining=int(str(case["n"])),
        next_cash_flow=Decimal(str(case["d1"])),
        next_but_one_cash_flow=Decimal(str(case["d2"])),
    )


@pytest.mark.parametrize("case", CORPUS["price_from_yield_cases"], ids=lambda c: c["id"])
def test_dirty_price_from_yield_matches_dmo_worked_example(case: dict[str, object]) -> None:
    inputs = _inputs_from_case(case)
    result = dirty_price_from_yield(inputs, Decimal(str(case["y"])))
    expected = Decimal(str(case["expected_dirty_price"]))
    assert abs(result - expected) < _PRICE_TOLERANCE, f"{case['id']}: got {result}, want {expected}"


@pytest.mark.parametrize("case", CORPUS["yield_from_price_cases"], ids=lambda c: c["id"])
def test_yield_from_price_matches_dmo_worked_example(case: dict[str, object]) -> None:
    inputs = _inputs_from_case(case)
    result = yield_from_price(inputs, Decimal(str(case["dirty_price"])))
    expected = Decimal(str(case["expected_yield"]))
    assert abs(result - expected) < _YIELD_TOLERANCE, f"{case['id']}: got {result}, want {expected}"


@pytest.mark.parametrize("case", CORPUS["accrued_interest_cases"], ids=lambda c: c["id"])
def test_accrued_interest_matches_dmo_worked_example(case: dict[str, object]) -> None:
    result = accrued_interest(
        next_cash_flow=Decimal(str(case["next_cash_flow"])),
        days_since_previous_quasi_coupon=int(str(case["days_since_previous_quasi_coupon"])),
        days_in_quasi_coupon_period=int(str(case["days_in_quasi_coupon_period"])),
        settled_on_or_before_ex_dividend=bool(case["settled_on_or_before_ex_dividend"]),
    )
    expected = Decimal(str(case["expected_accrued_interest"]))
    assert abs(result - expected) < _PRICE_TOLERANCE, f"{case['id']}: got {result}, want {expected}"


def test_corpus_case_count_is_the_expected_16() -> None:
    """Regression guard: catches an accidental truncation of the corpus
    file without needing to know its exact content.
    """
    assert len(CORPUS["price_from_yield_cases"]) == 8
    assert len(CORPUS["yield_from_price_cases"]) == 8


@pytest.mark.parametrize("case", CORPUS["price_from_yield_cases"], ids=lambda c: c["id"])
def test_shadow_implementation_matches_dmo_worked_example(case: dict[str, object]) -> None:
    """FIN-001's dual-implementation gate: the independently-derived
    cash-flow-loop implementation must ALSO reproduce DMO's own numbers,
    not just agree with the production implementation.
    """
    inputs = _inputs_from_case(case)
    result = shadow_dirty_price_from_yield(inputs, Decimal(str(case["y"])))
    expected = Decimal(str(case["expected_dirty_price"]))
    assert abs(result - expected) < _PRICE_TOLERANCE, f"{case['id']}: got {result}, want {expected}"


@pytest.mark.parametrize("case", CORPUS["price_from_yield_cases"], ids=lambda c: c["id"])
def test_production_and_shadow_implementations_agree(case: dict[str, object]) -> None:
    """The other half of the dual-implementation gate: production and
    shadow must agree with EACH OTHER, at a much tighter tolerance than
    either needs to match DMO's rounded published figures — this is what
    actually catches a subtle divergence the golden corpus's looser
    tolerance might paper over.
    """
    inputs = _inputs_from_case(case)
    y = Decimal(str(case["y"]))
    production_price = dirty_price_from_yield(inputs, y)
    shadow_price = shadow_dirty_price_from_yield(inputs, y)
    assert abs(production_price - shadow_price) < Decimal("1E-30"), case["id"]


def test_price_and_yield_solvers_round_trip_for_every_case() -> None:
    """price -> yield -> price must return (approximately) the original
    price - proves the two directions of the formula are actually
    consistent with each other, not just each independently matching DMO.
    """
    for case in CORPUS["price_from_yield_cases"]:
        inputs = _inputs_from_case(case)
        original_yield = Decimal(str(case["y"]))
        price = dirty_price_from_yield(inputs, original_yield)
        recovered_yield = yield_from_price(inputs, price)
        assert abs(recovered_yield - original_yield) < Decimal("1E-9"), case["id"]
