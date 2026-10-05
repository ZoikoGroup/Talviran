"""Production implementation of conventional-gilt risk metrics (Macaulay
duration, modified duration, DV01, convexity) — FIN-001 §11.

No DMO-published source exists for these metrics: the DMO's own pinned
methodology document ("Formulae for Calculating Gilt Prices from Yields",
4th edition, 18 Dec 2024 — M-UK-01) covers only price/yield conversion,
dividend-payment calculation, and accrued interest (Sections One–Three) —
confirmed by fetching and text-searching that document directly, not
assumed. FIN-001 §11 anticipates exactly this: "no universal denominator
hard-coded" for modified duration, and convexity's bump size/formula are
"specification-owned", not sourced from an external worked example.

Method: full repricing (FIN-001 §11's own stated preference for DV01 -
"deterministic full repricing under the same approved price model for a
+1bp/-1bp yield perturbation... unless a pack pins a different market
definition") against gilt_price_yield_v1's own golden-approved
`dirty_price_from_yield` — central finite differences at y-Δ/y/y+Δ, not
a hand-derived closed-form second derivative, so this implementation
never has to independently re-derive the price formula's calculus.

BUMP_SIZE is versioned here (FIN-001 §29 anti-pattern #5: "unversioned...
solver tolerances") — 1bp (0.0001) is the standard market convention for
DV01/PV01, and is small enough that the central-difference approximation
error is negligible against the golden tolerances in golden/v1/corpus.json
(cross-checked there against the independent analytical implementation in
shadow_implementation.py, not just asserted here).
"""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from app.modules.calculation.specs.gilt_price_yield_v1.implementation import (
    ConventionalGiltInputs,
    dirty_price_from_yield,
)

_PRECISION = 50
#: 1bp - the standard DV01/PV01 market convention. Exported (not
#: `_`-prefixed): shadow_implementation.py reuses this exact same bump
#: size for its own DV01 estimate (a shared constant/convention, not the
#: calculation logic itself, same "share data, not the dual-implemented
#: calculation" boundary schedule.py's helpers draw for gilt_price_yield_v1).
BUMP_SIZE = Decimal("0.0001")


@dataclass(frozen=True)
class RiskMetrics:
    macaulay_duration: Decimal  # years
    modified_duration: Decimal  # years
    dv01: Decimal  # price change per 1bp, same units as dirty_price
    convexity: Decimal  # years^2


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
