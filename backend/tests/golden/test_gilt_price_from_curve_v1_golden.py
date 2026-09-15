"""gilt_price_from_curve_v1's own golden gate: DMO never published a worked
example for a curve-discounted price (it isn't their formula), so the
strongest available check - per the spec's own docstring and
memory "talvrin-model-implied-vs-market-price" - is internal consistency
with gilt_price_yield_v1, which DOES have real DMO-sourced golden values:
if the BoE curve were flat at rate y, the curve-discounted price must
equal gilt_price_yield_v1's price at YTM=y, because the two specs share
the same period-counting/day-count structure by construction.
"""

import datetime as dt
from decimal import Decimal

from app.modules.calculation.specs.gilt_price_from_curve_v1.implementation import (
    CurvePoint,
    interpolate_curve,
    model_implied_price,
)
from app.modules.calculation.specs.gilt_price_yield_v1.implementation import (
    dirty_price_from_yield,
)
from app.modules.calculation.specs.gilt_price_yield_v1.schedule import standard_inputs_from_dates

_FLAT_CURVE_TOLERANCE = Decimal("1E-20")


def _flat_curve(rate_pct: Decimal) -> list[CurvePoint]:
    return [
        CurvePoint(tenor_years=Decimal(t) / 2, spot_rate_pct=rate_pct)
        for t in range(1, 81)  # 0.5Y .. 40Y, matching the real BoE publication grid
    ]


def test_flat_curve_matches_gilt_price_yield_v1_exactly() -> None:
    maturity = dt.date(2036, 3, 7)
    settlement = dt.date(2026, 9, 15)
    coupon = Decimal("4.25")
    flat_rate = Decimal("4.5")  # 4.5%

    curve_result = model_implied_price(
        coupon_per_100=coupon,
        maturity_date=maturity,
        settlement_date=settlement,
        curve=_flat_curve(flat_rate),
    )

    inputs = standard_inputs_from_dates(
        coupon_per_100=coupon, maturity_date=maturity, settlement_date=settlement
    )
    yield_v1_dirty_price = dirty_price_from_yield(inputs, flat_rate / 100)

    assert abs(curve_result.dirty_price - yield_v1_dirty_price) < _FLAT_CURVE_TOLERANCE


def test_flat_curve_matches_across_multiple_flat_rates_and_maturities() -> None:
    cases = [
        (dt.date(2036, 3, 7), Decimal("4.25"), dt.date(2026, 9, 15), Decimal("3.0")),
        (dt.date(2036, 3, 7), Decimal("4.25"), dt.date(2027, 1, 2), Decimal("6.75")),
        (dt.date(2028, 6, 15), Decimal("2.0"), dt.date(2026, 9, 15), Decimal("4.5")),
    ]
    for maturity, coupon, settlement, flat_rate in cases:
        curve_result = model_implied_price(
            coupon_per_100=coupon, maturity_date=maturity, settlement_date=settlement,
            curve=_flat_curve(flat_rate),
        )
        inputs = standard_inputs_from_dates(
            coupon_per_100=coupon, maturity_date=maturity, settlement_date=settlement
        )
        yield_v1_dirty_price = dirty_price_from_yield(inputs, flat_rate / 100)
        assert abs(curve_result.dirty_price - yield_v1_dirty_price) < _FLAT_CURVE_TOLERANCE, (
            maturity, settlement, flat_rate,
        )


def test_interpolate_curve_matches_published_points_exactly() -> None:
    curve = [CurvePoint(Decimal("1"), Decimal("4.0")), CurvePoint(Decimal("2"), Decimal("5.0"))]
    assert interpolate_curve(curve, Decimal("1")) == Decimal("4.0")
    assert interpolate_curve(curve, Decimal("2")) == Decimal("5.0")
    assert interpolate_curve(curve, Decimal("1.5")) == Decimal("4.5")


def test_interpolate_curve_clamps_outside_published_range() -> None:
    curve = [CurvePoint(Decimal("0.5"), Decimal("4.0")), CurvePoint(Decimal("40"), Decimal("5.0"))]
    assert interpolate_curve(curve, Decimal("0.1")) == Decimal("4.0")
    assert interpolate_curve(curve, Decimal("50")) == Decimal("5.0")


def test_dirty_minus_accrued_equals_clean_price() -> None:
    result = model_implied_price(
        coupon_per_100=Decimal("4.25"),
        maturity_date=dt.date(2036, 3, 7),
        settlement_date=dt.date(2026, 9, 15),
        curve=_flat_curve(Decimal("4.5")),
    )
    # Comparing at the test's own (default, 28-digit) Decimal context against
    # values computed inside the implementation's 50-digit localcontext
    # introduces its own ~1E-27 rounding noise here - unrelated to the
    # implementation, which computes clean_price = dirty - accrued directly
    # inside that same 50-digit context. 1E-20 comfortably exceeds that
    # noise while still proving genuine consistency.
    assert abs(
        result.clean_price - (result.dirty_price - result.accrued_interest)
    ) < Decimal("1E-20")
