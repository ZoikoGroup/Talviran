"""Second, independently-derived implementation of conventional-gilt risk
metrics - validation-only per TAL-FI-GILT-001 §5.1 (see
docs/Talvrin_Gilt_Analytics_Methodology_Decision.docx): "Production
derivatives should come from the closed-form/analytical implementation or
automatic differentiation over the same pricing function. Finite
differences are validation only." This module is that finite-difference
check, not a candidate production path - `implementation.py` (the
analytical cash-flow-weighted-sum method) is production.

Method: central finite-difference bump-and-reprice against
gilt_price_yield_v1's own golden-approved `dirty_price_from_yield` - central
differences at y-Δ/y/y+Δ, not a hand-derived closed-form second derivative,
so this module never has to independently re-derive the price formula's
calculus. The two approaches (this one, and implementation.py's exact
calculus over the cash-flow schedule) share no calculation code and no
calculus step, so a transcription error in either (a wrong central-
difference formula, an off-by-one in implementation.py's time-weighting)
shows up as a disagreement between them, not just a shared bug - FIN-001's
dual-implementation gate is satisfied by that cross-check even though only
one of the two (implementation.py) is the designated production path.

Honest limitation, same as gilt_price_yield_v1's own shadow_implementation:
both implementations here were authored by the same agent in the same
session, not by a second engineer working independently - this still
catches real transcription/off-by-one bugs, but is not a substitute for a
genuinely independent second author before this spec is used for anything
with real financial consequences.
"""

from decimal import Decimal, localcontext

from app.modules.calculation.specs.gilt_price_yield_v1.implementation import (
    ConventionalGiltInputs,
    dirty_price_from_yield,
)
from app.modules.calculation.specs.gilt_risk_metrics_v1.implementation import (
    BUMP_SIZE,
    RiskMetrics,
)

_PRECISION = 50


def compute_risk_metrics(
    inputs: ConventionalGiltInputs, yield_decimal: Decimal
) -> RiskMetrics:
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        f = inputs.coupons_per_year

        price = dirty_price_from_yield(inputs, yield_decimal)
        price_down = dirty_price_from_yield(inputs, yield_decimal - BUMP_SIZE)
        price_up = dirty_price_from_yield(inputs, yield_decimal + BUMP_SIZE)

        # DV01: price change for a 1bp DOWN move (the market convention this
        # figure is quoted under) - a central difference, not price_down -
        # price (a one-sided/forward difference), since the central estimate
        # is the more accurate approximation to the true derivative and
        # costs nothing extra (both prices are already computed for
        # convexity below).
        dv01 = (price_down - price_up) / 2

        # Modified duration = -(1/P)(dP/dy), estimated by the same central
        # difference, divided by the bump size to get a per-unit-yield
        # sensitivity rather than a per-1bp price change.
        modified_duration = (price_down - price_up) / (2 * price * BUMP_SIZE)

        # Macaulay duration = modified duration * (1 + y/f) - the standard
        # relationship between the two under periodic compounding
        # (FIN-001 §11: "Modified duration ... derived from Macaulay
        # duration and the specified yield/compounding convention").
        macaulay_duration = modified_duration * (1 + yield_decimal / f)

        # Convexity = (1/P)(d^2P/dy^2), estimated by the standard
        # three-point central second difference.
        convexity = (price_up + price_down - 2 * price) / (price * BUMP_SIZE**2)

        return RiskMetrics(
            macaulay_duration=macaulay_duration,
            modified_duration=modified_duration,
            dv01=dv01,
            convexity=convexity,
        )
