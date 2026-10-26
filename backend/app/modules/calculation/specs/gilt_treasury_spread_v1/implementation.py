"""Production implementation of the UK-gilt-vs-US-Treasury cross-market
yield spread — Talvrin's own comparison methodology, not a DMO or
TreasuryDirect publication (neither market publishes a combined
cross-market spread series; this is a straightforward, standard
market-convention comparison, not a novel or proprietary formula).

Method: plain subtraction of two already-published, already-reconciled
benchmark yields at matching tenors — spread_pct = uk_yield - us_yield,
spread_bp = spread_pct * 100 (the standard bp-per-pp convention). There is
no derivative or iterative solve here, unlike gilt_risk_metrics_v1 — the
"methodology" is the choice of sign convention and tenor-matching scope,
not a formula that could itself be wrong in a subtle way. FIN-001's
dual-implementation gate still applies (see shadow_implementation.py),
exercised via a genuinely different intermediate representation
(basis-point space) rather than a token restatement of the same
subtraction.

Scope: only the 6 tenors both curves publish as whole-year points (1Y,
2Y, 5Y, 10Y, 20Y, 30Y) — the UK curve's own benchmark subset
(evidence/service.py's _BENCHMARK_TENORS) and the matching whole-year
subset of the Treasury curve's tenors (excluding its sub-1-year
bill-equivalent points, which the UK benchmark set has no counterpart for
in this comparison).
"""

from dataclasses import dataclass
from decimal import Decimal

#: The only tenors both curves publish as whole-year benchmark points -
#: see module docstring for why the Treasury curve's sub-1-year points are
#: out of scope for this specific comparison.
COMPARABLE_TENORS_YEARS: tuple[int, ...] = (1, 2, 5, 10, 20, 30)


@dataclass(frozen=True)
class SpreadInputs:
    uk_yield_pct: Decimal
    us_yield_pct: Decimal


@dataclass(frozen=True)
class SpreadResult:
    spread_pct: Decimal  # uk - us, in percentage points
    spread_bp: Decimal  # the same difference, in basis points (market convention)


def compute_spread(inputs: SpreadInputs) -> SpreadResult:
    spread_pct = inputs.uk_yield_pct - inputs.us_yield_pct
    spread_bp = spread_pct * 100
    return SpreadResult(spread_pct=spread_pct, spread_bp=spread_bp)
