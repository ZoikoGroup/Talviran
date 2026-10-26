"""treasury_price_from_curve_v1's golden gate.

No DMO-equivalent worked example exists for US Treasuries in this codebase
(this is a model-implied spec, not a transcription of a published formula),
so the golden checks are: (1) production and shadow implementations - two
genuinely different discount-factor computations (see shadow_implementation
.py's own docstring) - agree to a tight tolerance across flat AND non-flat
curves, and (2) a flat curve reduces to the standard, independently
hand-derived semi-annual bond pricing formula, computed directly in this
test file rather than imported from the implementation under test.
"""

import datetime as dt
from decimal import Decimal, localcontext

from app.modules.calculation.specs.gilt_price_yield_v1.schedule import (
    COUPONS_PER_YEAR,
    timeline_for_settlement,
)
from app.modules.calculation.specs.treasury_price_from_curve_v1 import (
    implementation as production,
)
from app.modules.calculation.specs.treasury_price_from_curve_v1 import (
    shadow_implementation as shadow,
)
from app.modules.calculation.specs.treasury_price_from_curve_v1.implementation import CurvePoint

_AGREEMENT_TOLERANCE = Decimal("1E-30")
_FORMULA_TOLERANCE = Decimal("1E-20")


def _flat_curve(rate_pct: Decimal) -> list[CurvePoint]:
    return [CurvePoint(tenor_years=Decimal(t) / 2, par_yield_pct=rate_pct) for t in range(1, 61)]


def _non_flat_curve() -> list[CurvePoint]:
    # A real-shaped upward-sloping curve, not a flat one - this is what
    # actually exercises the two implementations' different discounting
    # paths; a flat curve alone can't prove they handle a genuine term
    # structure identically.
    return [
        CurvePoint(tenor_years=Decimal("0.5"), par_yield_pct=Decimal("4.80")),
        CurvePoint(tenor_years=Decimal("1"), par_yield_pct=Decimal("4.70")),
        CurvePoint(tenor_years=Decimal("2"), par_yield_pct=Decimal("4.50")),
        CurvePoint(tenor_years=Decimal("3"), par_yield_pct=Decimal("4.40")),
        CurvePoint(tenor_years=Decimal("5"), par_yield_pct=Decimal("4.35")),
        CurvePoint(tenor_years=Decimal("7"), par_yield_pct=Decimal("4.40")),
        CurvePoint(tenor_years=Decimal("10"), par_yield_pct=Decimal("4.50")),
        CurvePoint(tenor_years=Decimal("20"), par_yield_pct=Decimal("4.75")),
        CurvePoint(tenor_years=Decimal("30"), par_yield_pct=Decimal("4.85")),
    ]


def _standard_flat_rate_price(
    *,
    coupon_per_100: Decimal,
    maturity_date: dt.date,
    settlement_date: dt.date,
    flat_rate_pct: Decimal,
) -> Decimal:
    """Independently hand-derived: the textbook semi-annual bond pricing
    formula P = sum_k[ CF_k / (1+y/2)^(k-1+r/s) ], computed directly here
    with no call into either implementation under test (only the already-
    approved, shared quasi-coupon-date utility is reused to get real
    calendar dates - the arithmetic itself is written fresh).
    """
    with localcontext() as ctx:
        ctx.prec = 50
        timeline = timeline_for_settlement(
            maturity_date=maturity_date, settlement_date=settlement_date
        )
        coupon_payment = coupon_per_100 / COUPONS_PER_YEAR
        r = (timeline.next_quasi_coupon_date - settlement_date).days
        s = (timeline.next_quasi_coupon_date - timeline.previous_quasi_coupon_date).days
        r_over_s = Decimal(r) / Decimal(s)
        y = flat_rate_pct / 100

        price = Decimal(0)
        for j, cash_flow_date in enumerate(timeline.remaining_quasi_coupon_dates):
            cash_flow = coupon_payment + (100 if cash_flow_date == maturity_date else 0)
            price += cash_flow / (1 + y / COUPONS_PER_YEAR) ** (r_over_s + j)
        return price


_CASES = [
    # (maturity, coupon, settlement)
    (dt.date(2036, 8, 15), Decimal("4.0"), dt.date(2026, 10, 26)),
    (dt.date(2029, 2, 28), Decimal("2.375"), dt.date(2026, 10, 26)),
    (dt.date(2056, 5, 15), Decimal("4.625"), dt.date(2026, 10, 26)),
    (dt.date(2028, 11, 30), Decimal("3.5"), dt.date(2027, 3, 1)),
]


def test_flat_curve_matches_standard_bond_formula() -> None:
    flat_rate = Decimal("4.5")
    for maturity, coupon, settlement in _CASES:
        result = production.model_implied_price(
            coupon_per_100=coupon, maturity_date=maturity, settlement_date=settlement,
            curve=_flat_curve(flat_rate),
        )
        expected = _standard_flat_rate_price(
            coupon_per_100=coupon, maturity_date=maturity, settlement_date=settlement,
            flat_rate_pct=flat_rate,
        )
        assert abs(result.dirty_price - expected) < _FORMULA_TOLERANCE, (maturity, settlement)


def test_shadow_matches_production_on_flat_curve() -> None:
    flat_rate = Decimal("3.75")
    for maturity, coupon, settlement in _CASES:
        prod = production.model_implied_price(
            coupon_per_100=coupon, maturity_date=maturity, settlement_date=settlement,
            curve=_flat_curve(flat_rate),
        )
        shad = shadow.model_implied_price(
            coupon_per_100=coupon, maturity_date=maturity, settlement_date=settlement,
            curve=_flat_curve(flat_rate),
        )
        assert abs(prod.dirty_price - shad.dirty_price) < _AGREEMENT_TOLERANCE, (
            maturity,
            settlement,
        )
        assert abs(prod.accrued_interest - shad.accrued_interest) < _AGREEMENT_TOLERANCE
        assert abs(prod.clean_price - shad.clean_price) < _AGREEMENT_TOLERANCE


def test_shadow_matches_production_on_non_flat_curve() -> None:
    curve = _non_flat_curve()
    for maturity, coupon, settlement in _CASES:
        prod = production.model_implied_price(
            coupon_per_100=coupon, maturity_date=maturity, settlement_date=settlement, curve=curve
        )
        shad = shadow.model_implied_price(
            coupon_per_100=coupon, maturity_date=maturity, settlement_date=settlement, curve=curve
        )
        assert abs(prod.dirty_price - shad.dirty_price) < _AGREEMENT_TOLERANCE, (
            maturity,
            settlement,
        )
        assert abs(prod.accrued_interest - shad.accrued_interest) < _AGREEMENT_TOLERANCE
        assert abs(prod.clean_price - shad.clean_price) < _AGREEMENT_TOLERANCE


def test_interpolate_curve_matches_published_points_exactly() -> None:
    curve = [CurvePoint(Decimal("1"), Decimal("4.0")), CurvePoint(Decimal("2"), Decimal("5.0"))]
    assert production.interpolate_curve(curve, Decimal("1")) == Decimal("4.0")
    assert production.interpolate_curve(curve, Decimal("2")) == Decimal("5.0")
    assert production.interpolate_curve(curve, Decimal("1.5")) == Decimal("4.5")


def test_interpolate_curve_clamps_outside_published_range() -> None:
    curve = [CurvePoint(Decimal("0.5"), Decimal("4.0")), CurvePoint(Decimal("30"), Decimal("5.0"))]
    assert production.interpolate_curve(curve, Decimal("0.1")) == Decimal("4.0")
    assert production.interpolate_curve(curve, Decimal("50")) == Decimal("5.0")


def test_dirty_minus_accrued_equals_clean_price() -> None:
    result = production.model_implied_price(
        coupon_per_100=Decimal("4.0"), maturity_date=dt.date(2036, 8, 15),
        settlement_date=dt.date(2026, 10, 26), curve=_flat_curve(Decimal("4.5")),
    )
    assert abs(result.clean_price - (result.dirty_price - result.accrued_interest)) < Decimal(
        "1E-20"
    )
