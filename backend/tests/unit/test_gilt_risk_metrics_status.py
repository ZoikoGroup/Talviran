"""Proves gilt_risk_metrics_v1/status.py's suppression/status decisions
against TAL-FI-GILT-001 Table 13 (docs/Talvrin_Gilt_Analytics_Methodology_
Decision.docx) - see status.py's own docstring for exactly which Table 13
rows are in scope here versus deferred to a future service-layer.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.calculation.specs.gilt_price_yield_v1.implementation import (
    ConventionalGiltInputs,
)
from app.modules.calculation.specs.gilt_risk_metrics_v1.status import (
    RiskMetricsStatus,
    compute_risk_metrics_outcome,
)

_CORPUS_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "modules"
    / "calculation"
    / "specs"
    / "gilt_risk_metrics_v1"
    / "golden"
    / "v1"
    / "corpus.json"
)
_CORPUS = json.loads(_CORPUS_PATH.read_text())


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


@pytest.mark.parametrize(
    "case",
    [c for c in _CORPUS["risk_metrics_cases"] if "exdiv" in c["id"]],
    ids=lambda c: c["id"],
)
def test_real_exdiv_case_is_tagged_ex_dividend_not_suppressed(
    case: dict[str, object],
) -> None:
    """The corpus's real DMO-sourced "-exdiv" cases all have n != 0 (not the
    final period), so Table 13's regular "Settlement in ex-dividend period"
    row applies: compute analytics and tag the status, don't suppress.
    """
    inputs = _inputs_from_case(case)
    assert inputs.full_quasi_coupon_periods_remaining != 0
    outcome = compute_risk_metrics_outcome(inputs, Decimal(str(case["y"])))
    assert outcome.status == RiskMetricsStatus.EX_DIVIDEND
    assert outcome.metrics is not None


@pytest.mark.parametrize(
    "case",
    [c for c in _CORPUS["risk_metrics_cases"] if "exdiv" not in c["id"]],
    ids=lambda c: c["id"],
)
def test_real_cum_dividend_case_is_ok_not_suppressed(case: dict[str, object]) -> None:
    inputs = _inputs_from_case(case)
    outcome = compute_risk_metrics_outcome(inputs, Decimal(str(case["y"])))
    assert outcome.status == RiskMetricsStatus.OK
    assert outcome.metrics is not None


def test_final_ex_dividend_period_is_suppressed() -> None:
    """Table 13's "Final ex-dividend period" row: n=0 (the final period)
    AND ex-dividend (d1=0) together mean a normal gilt trade cannot settle
    here at all (DMO rule) - synthetic case, since none of the 8 real DMO
    worked examples happen to land in this specific combination (gate G1
    explicitly allows supplementing missing edge cases this way).
    """
    inputs = ConventionalGiltInputs(
        coupon_per_100=Decimal("8"),
        coupons_per_year=2,
        days_to_next_quasi_coupon=14,
        days_in_quasi_coupon_period=182,
        full_quasi_coupon_periods_remaining=0,
        next_cash_flow=Decimal("0"),
        next_but_one_cash_flow=Decimal("4"),
    )
    outcome = compute_risk_metrics_outcome(inputs, Decimal("0.04445"))
    assert outcome.status == RiskMetricsStatus.UNAVAILABLE_FINAL_SETTLEMENT
    assert outcome.metrics is None


def test_final_cum_dividend_period_is_not_suppressed() -> None:
    """n=0 alone (final period, but still cum-dividend, d1 != 0) is a
    perfectly normal settlement - only the ex-dividend COMBINATION with the
    final period is suppressed, not the final period on its own.
    """
    inputs = ConventionalGiltInputs(
        coupon_per_100=Decimal("8"),
        coupons_per_year=2,
        days_to_next_quasi_coupon=14,
        days_in_quasi_coupon_period=182,
        full_quasi_coupon_periods_remaining=0,
        next_cash_flow=Decimal("4"),
        next_but_one_cash_flow=Decimal("0"),
    )
    outcome = compute_risk_metrics_outcome(inputs, Decimal("0.04445"))
    assert outcome.status == RiskMetricsStatus.OK
    assert outcome.metrics is not None


def test_yield_outside_mathematical_domain_is_calculation_unavailable() -> None:
    """TAL-FI-GILT-001 §5.1's domain constraint is 1 + y/f > 0. A yield
    that violates it (y=-3, f=2 gives 1 + (-3/2) = -0.5) drives the discount
    factor negative, and raising a negative Decimal to the fractional r/s
    exponent raises decimal.InvalidOperation - confirmed empirically, not
    assumed - which must surface as CALCULATION_UNAVAILABLE, not propagate
    as an unhandled exception or silently return garbage.
    """
    inputs = ConventionalGiltInputs(
        coupon_per_100=Decimal("8"),
        coupons_per_year=2,
        days_to_next_quasi_coupon=14,
        days_in_quasi_coupon_period=182,
        full_quasi_coupon_periods_remaining=33,
        next_cash_flow=Decimal("4"),
        next_but_one_cash_flow=Decimal("4"),
    )
    outcome = compute_risk_metrics_outcome(inputs, Decimal("-3"))
    assert outcome.status == RiskMetricsStatus.CALCULATION_UNAVAILABLE
    assert outcome.metrics is None
