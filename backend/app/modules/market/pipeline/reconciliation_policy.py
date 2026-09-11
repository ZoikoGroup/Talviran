"""Versioned per-metric reconciliation policy (DATA-002) — deliberately NOT
a universal source-authority ranking. A source can be primary for one
metric and secondary for another; authority lives here, scoped per metric,
never on the source's identity itself.

Only one source (uk-dmo) exists as of P1 week 9, so CONFLICT can't yet
happen in production — but the policy and reconcile() logic are built and
tested for the real multi-source case now (tests/unit exercises a
synthetic two-source disagreement), so this isn't retrofitted later under
pressure once a second source actually lands.
"""

from dataclasses import dataclass
from decimal import Decimal

CONFLICT_ACTION_FLAG = "FLAG_CONFLICT"
CONFLICT_ACTION_PREFER_ORDER = "PREFER_ORDER"


@dataclass(frozen=True)
class ReconciliationPolicy:
    metric_id: str
    # Precedence order for this metric specifically — not a global ranking.
    ordered_source_codes: tuple[str, ...]
    # Max acceptable numeric divergence between agreeing sources before
    # they count as disagreeing; None means values must match exactly
    # (appropriate for reference terms like coupon/maturity, not prices).
    tolerance: Decimal | None
    # FLAG_CONFLICT: disagreement always surfaces as CONFLICT, never
    # auto-resolved. PREFER_ORDER: disagreement is resolved by
    # ordered_source_codes precedence, but still recorded as a conflict
    # decision for audit — never a silent, unexplained pick.
    conflict_action: str


GILT_REFERENCE_TERMS_POLICY = ReconciliationPolicy(
    metric_id="GILT_REFERENCE_TERMS",
    ordered_source_codes=("uk-dmo",),
    tolerance=None,
    conflict_action=CONFLICT_ACTION_FLAG,
)

DEFAULT_POLICIES: dict[str, ReconciliationPolicy] = {
    GILT_REFERENCE_TERMS_POLICY.metric_id: GILT_REFERENCE_TERMS_POLICY,
}
