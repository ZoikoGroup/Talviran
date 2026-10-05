"""FIN-001's golden-test gate for gilt_risk_metrics_v1 (Macaulay duration,
modified duration, DV01, convexity) — golden/v1/corpus.json.

Unlike gilt_price_yield_v1, no DMO-published (or any external) source exists
for these metrics (confirmed by fetching and text-searching DMO's own pinned
price/yield methodology doc — see implementation.py's docstring). The
corpus's expected_* values are therefore this spec's own analytical
(shadow) implementation's frozen output, not an independently-published
reference — an honest limitation recorded in golden/v1/corpus.json's own
"source" block, and in FIN-001 §26's still-open FIN-O3 decision (Product +
Methodology sign-off on the customer-facing definition), which this test
does not resolve.

Given that, this file's checks are:
  1. the analytical (shadow) implementation reproduces its own frozen
     historical corpus values almost exactly — catches a future regression
     in that implementation itself;
  2. the numerical (production) implementation matches those same frozen
     values within a tolerance wide enough to absorb its inherent
     central-finite-difference truncation error (empirically ~1e-9 to
     ~1e-5 across these 8 cases, at BUMP_SIZE=1bp) — a much looser bound
     than gilt_price_yield_v1's near-exact production/shadow agreement,
     because here the two implementations use genuinely different methods
     (exact calculus vs. numerical approximation), not just independently
     re-derived algebra for the same closed form;
  3. production and shadow agree with each other at that same realistic
     tolerance, not gilt_price_yield_v1's 1E-30 — a real bug (wrong sign,
     off-by-one, wrong time-weighting) would still produce a divergence far
     larger than the expected approximation-error scale, so this remains a
     meaningful regression gate, just calibrated to an honest baseline.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.calculation.golden_manifest import verify_corpus_integrity
from app.modules.calculation.specs.gilt_price_yield_v1.implementation import (
    ConventionalGiltInputs,
)
from app.modules.calculation.specs.gilt_risk_metrics_v1.implementation import (
    compute_risk_metrics as production_compute_risk_metrics,
)
from app.modules.calculation.specs.gilt_risk_metrics_v1.shadow_implementation import (
    compute_risk_metrics as shadow_compute_risk_metrics,
)

CORPUS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "modules"
    / "calculation"
    / "specs"
    / "gilt_risk_metrics_v1"
    / "golden"
    / "v1"
)
CORPUS_PATH = CORPUS_DIR / "corpus.json"
CORPUS = json.loads(CORPUS_PATH.read_text())

# Loose: absorbs production's finite-difference truncation error at
# BUMP_SIZE=1bp (measured empirically up to ~3.8e-6 for duration across
# these 8 cases) - a real bug would diverge far beyond this margin.
_DURATION_TOLERANCE = Decimal("1E-4")
_DV01_TOLERANCE = Decimal("1E-6")
_CONVEXITY_TOLERANCE = Decimal("1E-3")

# Tight: the shadow implementation reproducing its OWN frozen corpus
# values is a near-exact check (the only slack is the corpus's own
# 9-decimal-place quantization when it was written).
_SHADOW_SELF_CONSISTENCY_TOLERANCE = Decimal("1E-8")


def test_corpus_v1_bytes_have_not_silently_changed() -> None:
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


def test_corpus_case_count_is_the_expected_8() -> None:
    assert len(CORPUS["risk_metrics_cases"]) == 8


@pytest.mark.parametrize("case", CORPUS["risk_metrics_cases"], ids=lambda c: c["id"])
def test_shadow_implementation_reproduces_its_own_corpus_values(
    case: dict[str, object],
) -> None:
    inputs = _inputs_from_case(case)
    result = shadow_compute_risk_metrics(inputs, Decimal(str(case["y"])))

    assert abs(
        result.macaulay_duration - Decimal(str(case["expected_macaulay_duration"]))
    ) < _SHADOW_SELF_CONSISTENCY_TOLERANCE, case["id"]
    assert abs(
        result.modified_duration - Decimal(str(case["expected_modified_duration"]))
    ) < _SHADOW_SELF_CONSISTENCY_TOLERANCE, case["id"]
    assert abs(
        result.dv01 - Decimal(str(case["expected_dv01"]))
    ) < _SHADOW_SELF_CONSISTENCY_TOLERANCE, case["id"]
    assert abs(
        result.convexity - Decimal(str(case["expected_convexity"]))
    ) < _SHADOW_SELF_CONSISTENCY_TOLERANCE, case["id"]


@pytest.mark.parametrize("case", CORPUS["risk_metrics_cases"], ids=lambda c: c["id"])
def test_production_implementation_matches_corpus_within_approximation_tolerance(
    case: dict[str, object],
) -> None:
    inputs = _inputs_from_case(case)
    result = production_compute_risk_metrics(inputs, Decimal(str(case["y"])))

    assert abs(
        result.macaulay_duration - Decimal(str(case["expected_macaulay_duration"]))
    ) < _DURATION_TOLERANCE, case["id"]
    assert abs(
        result.modified_duration - Decimal(str(case["expected_modified_duration"]))
    ) < _DURATION_TOLERANCE, case["id"]
    assert abs(
        result.dv01 - Decimal(str(case["expected_dv01"]))
    ) < _DV01_TOLERANCE, case["id"]
    assert abs(
        result.convexity - Decimal(str(case["expected_convexity"]))
    ) < _CONVEXITY_TOLERANCE, case["id"]


@pytest.mark.parametrize("case", CORPUS["risk_metrics_cases"], ids=lambda c: c["id"])
def test_production_and_shadow_implementations_agree(case: dict[str, object]) -> None:
    """The dual-implementation gate proper: production (numerical
    bump-and-reprice) and shadow (analytical cash-flow-weighted-sum) must
    agree with EACH OTHER within the same approximation-error-scale
    tolerance, independent of the frozen corpus values.
    """
    inputs = _inputs_from_case(case)
    y = Decimal(str(case["y"]))
    production = production_compute_risk_metrics(inputs, y)
    shadow = shadow_compute_risk_metrics(inputs, y)

    assert abs(production.macaulay_duration - shadow.macaulay_duration) < _DURATION_TOLERANCE
    assert abs(production.modified_duration - shadow.modified_duration) < _DURATION_TOLERANCE
    assert abs(production.dv01 - shadow.dv01) < _DV01_TOLERANCE
    assert abs(production.convexity - shadow.convexity) < _CONVEXITY_TOLERANCE
