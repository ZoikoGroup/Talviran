"""Shadow (validation-only) implementation of the cross-market spread —
FIN-001's dual-implementation gate. Computes via a genuinely different
intermediate representation (basis points first, converting back to
percentage points afterward) rather than literally repeating the
production path's own arithmetic order — this is what actually exercises
a different rounding path, not just a copy-pasted formula with a new name.
"""

from app.modules.calculation.specs.gilt_treasury_spread_v1.implementation import (
    SpreadInputs,
    SpreadResult,
)


def compute_spread(inputs: SpreadInputs) -> SpreadResult:
    uk_bp = inputs.uk_yield_pct * 100
    us_bp = inputs.us_yield_pct * 100
    spread_bp = uk_bp - us_bp
    spread_pct = spread_bp / 100
    return SpreadResult(spread_pct=spread_pct, spread_bp=spread_bp)
