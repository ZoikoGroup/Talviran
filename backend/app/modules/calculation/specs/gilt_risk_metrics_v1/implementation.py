"""Production implementation of conventional-gilt risk metrics (Macaulay
duration, modified duration, DV01, convexity) — FIN-001 §11, methodology
locked as TAL-FI-GILT-001 v1.0 (see docs/Talvrin_Gilt_Analytics_Methodology_
Decision.docx, §5/§5.1/Table 9/Table 10).

Method: closed-form analytical derivatives over the discrete cash-flow
schedule (a time-weighted present-value sum), not finite-difference
bump-and-reprice. TAL-FI-GILT-001 §5.1 is explicit: "Production derivatives
should come from the closed-form/analytical implementation or automatic
differentiation over the same pricing function. Finite differences are
validation only." `shadow_implementation.py` holds the finite-difference
path for exactly that validation-only role, not as an alternative production
candidate.

No DMO-published source exists for these metrics: the DMO's own pinned
methodology document ("Formulae for Calculating Gilt Prices from Yields",
4th edition, 18 Dec 2024 — M-UK-01) covers only price/yield conversion,
dividend-payment calculation, and accrued interest (Sections One–Three) —
confirmed by fetching and text-searching that document directly, not
assumed. The formulas below are standard discrete-cash-flow fixed-income
analytics (e.g. Fabozzi, "Bond Markets, Analysis, and Strategies"),
re-derived here via calculus rather than transcribed from memory:

for a discrete cash-flow schedule CF_k paid at time t_k years from
settlement, discounted at v = 1/(1+y/f):

    P           = sum_k[ CF_k * v^(t_k * f) ]                      (dirty price)
    dP/dy       = -v * sum_k[ t_k * PV_k ]                          where PV_k = CF_k * v^(t_k*f)
    d^2P/dy^2   = v^2 * ( sum_k[t_k*PV_k]/f + sum_k[t_k^2*PV_k] )

Dividing by P and negating the first derivative gives modified duration;
Macaulay duration is modified duration * (1+y/f) (undoing the v factor);
convexity = (1/P)(d^2P/dy^2) reduces to the standard textbook form:

    convexity = (1/(P*(1+y/f)^2)) * sum_k[ PV_k * t_k * (t_k + 1/f) ]

matching TAL-FI-GILT-001 Table 9's locked definitions exactly: Modified
Duration = -(1/P)*dP/dy; DV01 = |dP/dy| * 0.0001 = Modified Duration * P *
0.0001 (a positive first-order sensitivity, not an exact one-sided 1bp
bumped-price difference); Convexity = (1/P)*d^2P/dy^2 in yr^2, with no
division by 100.

BUMP_SIZE is versioned here (FIN-001 §29 anti-pattern #5: "unversioned...
solver tolerances") as the standard 1bp DV01/PV01 scaling constant used in
the Table 9 formula above - it is not a finite-difference step on this
path (there is no repricing here), only the 0.0001 multiplier the locked
DV01 definition itself specifies. `shadow_implementation.py` reuses this
exact same constant as its own finite-difference bump size, since both
uses happen to be the same market-convention value.
"""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from app.modules.calculation.specs.gilt_price_yield_v1.implementation import (
    ConventionalGiltInputs,
)
from app.modules.calculation.specs.gilt_price_yield_v1.shadow_implementation import (
    cash_flow_schedule,
    discount_factor,
)

_PRECISION = 50
#: 1bp - the standard DV01/PV01 market convention, and TAL-FI-GILT-001's
#: locked DV01 scaling constant. Exported (not `_`-prefixed):
#: shadow_implementation.py reuses this exact same value for its own
#: finite-difference bump size (a shared constant/convention, not the
#: calculation logic itself, same "share data, not the dual-implemented
#: calculation" boundary schedule.py's helpers draw for gilt_price_yield_v1).
BUMP_SIZE = Decimal("0.0001")


@dataclass(frozen=True)
class RiskMetrics:
    macaulay_duration: Decimal  # years
    modified_duration: Decimal  # years
    dv01: Decimal  # price change per 1bp, same units as dirty_price
    convexity: Decimal  # years^2


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
