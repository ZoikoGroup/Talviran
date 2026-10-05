"""Second, independently-derived implementation of conventional-gilt risk
metrics — computes Macaulay duration, modified duration, and convexity
directly from the discrete cash-flow schedule (a time-weighted present-value
sum), rather than `implementation.py`'s finite-difference bump-and-reprice
against the closed-form price formula. The two approaches share no
calculation code and no calculus step (only the pure cash-flow-schedule
data from gilt_price_yield_v1's own shadow_implementation, the same "share
data, not the dual-implemented calculation" boundary schedule.py already
draws), so a transcription error in either (a wrong central-difference
formula, an off-by-one in this module's time-weighting) shows up as a
disagreement between them, not just a shared bug.

Derivation (worked from first principles, since no external published
source exists for these metrics — see implementation.py's own docstring):
for a discrete cash-flow schedule CF_k paid at time t_k years from
settlement, discounted at v = 1/(1+y/f):

    P           = sum_k[ CF_k * v^(t_k * f) ]                      (dirty price)
    dP/dy       = -v * sum_k[ t_k * PV_k ]                          where PV_k = CF_k * v^(t_k*f)
    d^2P/dy^2   = v^2 * ( sum_k[t_k*PV_k]/f + sum_k[t_k^2*PV_k] )

Dividing by P and negating the first derivative gives modified duration;
Macaulay duration is modified duration * (1+y/f) (undoing the v factor);
convexity = (1/P)(d^2P/dy^2) reduces to the standard textbook form:

    convexity = (1/(P*(1+y/f)^2)) * sum_k[ PV_k * t_k * (t_k + 1/f) ]

This is the same standard discrete-cash-flow convexity formula found in
fixed-income references (e.g. Fabozzi, "Bond Markets, Analysis, and
Strategies") — re-derived here via calculus rather than transcribed from
memory, and cross-checked against implementation.py's independent
finite-difference estimate in the golden test. DV01 has no separate
analytical form on this path; it's recovered from modified duration
(DV01 = modified_duration * price * BUMP_SIZE), consistent with how the
two are related on the numerical path too.

Honest limitation, same as gilt_price_yield_v1's own shadow_implementation:
both implementations here were authored by the same agent in the same
session, not by a second engineer working independently — this still
catches real transcription/off-by-one bugs, but is not a substitute for a
genuinely independent second author before this spec is used for anything
with real financial consequences.
"""

from decimal import Decimal, localcontext

from app.modules.calculation.specs.gilt_price_yield_v1.implementation import (
    ConventionalGiltInputs,
)
from app.modules.calculation.specs.gilt_price_yield_v1.shadow_implementation import (
    cash_flow_schedule,
    discount_factor,
)
from app.modules.calculation.specs.gilt_risk_metrics_v1.implementation import (
    BUMP_SIZE,
    RiskMetrics,
)

_PRECISION = 50


def _time_years(inputs: ConventionalGiltInputs, exponent: int) -> Decimal:
    """Time in years from settlement to the cash flow at this schedule
    exponent - the stub period (r/s of one quasi-coupon period) plus
    `exponent` full periods, all divided by the number of periods per
    year. Matches the exact same r/s/exponent structure the price sum
    itself discounts by (v^(r/s) * v^exponent), just expressed as years
    rather than as a discount power.
    """
    f = inputs.coupons_per_year
    r = Decimal(inputs.days_to_next_quasi_coupon)
    s = Decimal(inputs.days_in_quasi_coupon_period)
    return (r / s + exponent) / f


def compute_risk_metrics(
    inputs: ConventionalGiltInputs, yield_decimal: Decimal
) -> RiskMetrics:
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        f = inputs.coupons_per_year
        n = inputs.full_quasi_coupon_periods_remaining
        v = discount_factor(yield_decimal, f)
        one_plus_y_over_f = 1 + yield_decimal / f

        if n == 0:
            # A single cash flow (d1 + 100) at the stub time t0 - a lone
            # cash flow's Macaulay duration is trivially its own time
            # (there is nothing else to weight against), and the standard
            # t*(t+1/f) convexity term is still well-defined for it, so
            # no separate convexity formula is needed on this path either.
            r = Decimal(inputs.days_to_next_quasi_coupon)
            s = Decimal(inputs.days_in_quasi_coupon_period)
            price = v ** (r / s) * (inputs.next_cash_flow + 100)
            t0 = _time_years(inputs, 0)
            macaulay_duration = t0
            modified_duration = macaulay_duration / one_plus_y_over_f
            convexity = t0 * (t0 + Decimal(1) / f) / one_plus_y_over_f**2
            dv01 = modified_duration * price * BUMP_SIZE
            return RiskMetrics(
                macaulay_duration=macaulay_duration,
                modified_duration=modified_duration,
                dv01=dv01,
                convexity=convexity,
            )

        r = Decimal(inputs.days_to_next_quasi_coupon)
        s = Decimal(inputs.days_in_quasi_coupon_period)
        stub_factor = v ** (r / s)
        schedule = cash_flow_schedule(inputs)

        price = Decimal(0)
        weighted_by_time = Decimal(0)  # sum_k[t_k * PV_k]
        weighted_by_time_squared = Decimal(0)  # sum_k[t_k^2 * PV_k]
        for exponent, cash_flow in enumerate(schedule):
            pv_k = stub_factor * cash_flow * v**exponent
            t_k = _time_years(inputs, exponent)
            price += pv_k
            weighted_by_time += t_k * pv_k
            weighted_by_time_squared += t_k * t_k * pv_k

        macaulay_duration = weighted_by_time / price
        modified_duration = macaulay_duration / one_plus_y_over_f
        convexity = (weighted_by_time / f + weighted_by_time_squared) / (
            price * one_plus_y_over_f**2
        )
        dv01 = modified_duration * price * BUMP_SIZE

        return RiskMetrics(
            macaulay_duration=macaulay_duration,
            modified_duration=modified_duration,
            dv01=dv01,
            convexity=convexity,
        )
