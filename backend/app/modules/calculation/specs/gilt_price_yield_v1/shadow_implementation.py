"""Second, independently-derived implementation of the same DMO conventional
gilt price/yield formula (FIN-001's dual-implementation requirement) —
computes price as an explicit list of discrete discounted cash flows rather
than `implementation.py`'s closed-form geometric-series reduction. The two
approaches share no code and no algebraic simplification step, so a
transcription error in either (e.g. the closed form's `(1-v^(n-1))/(1-v)`
identity, or an off-by-one in this module's cash-flow list) shows up as a
disagreement between them, not just a shared bug.

Honest limitation: both implementations were authored by the same agent in
the same session, not by a second engineer working independently from the
DMO document as FIN-001 envisions. This still catches real bugs (a wrong
term, a sign error, an off-by-one) but is not a substitute for a genuinely
independent second author before this spec is used for anything with real
financial consequences.
"""

from decimal import Decimal, localcontext

from app.modules.calculation.specs.gilt_price_yield_v1.implementation import (
    ConventionalGiltInputs,
)

_PRECISION = 50


def _discount_factor(yield_decimal: Decimal, f: int) -> Decimal:
    return 1 / (1 + yield_decimal / f)


def _cash_flow_schedule(inputs: ConventionalGiltInputs) -> list[Decimal]:
    """cash_flows[k] is the amount due at discount exponent k (i.e. k full
    quasi-coupon periods beyond the initial r/s stub) — index 0 is d1, index
    1 is d2, indices 2..n-1 are the regular coupon, and index n carries the
    regular coupon PLUS the £100 redemption (they fall due on the same
    date: maturity).
    """
    n = inputs.full_quasi_coupon_periods_remaining
    coupon = inputs.coupon_per_100 / inputs.coupons_per_year
    schedule = [inputs.next_cash_flow, inputs.next_but_one_cash_flow]
    schedule.extend([coupon] * (n - 2))
    schedule.append(coupon + Decimal(100))
    return schedule


def dirty_price_from_yield(inputs: ConventionalGiltInputs, yield_decimal: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        f = inputs.coupons_per_year
        r = Decimal(inputs.days_to_next_quasi_coupon)
        s = Decimal(inputs.days_in_quasi_coupon_period)
        n = inputs.full_quasi_coupon_periods_remaining
        v = _discount_factor(yield_decimal, f)

        if n == 0:
            return v ** (r / s) * (inputs.next_cash_flow + 100)

        stub_factor = v ** (r / s)
        schedule = _cash_flow_schedule(inputs)
        total = sum(
            (cash_flow * v**exponent for exponent, cash_flow in enumerate(schedule)),
            start=Decimal(0),
        )
        return stub_factor * total
