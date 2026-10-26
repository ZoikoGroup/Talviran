"""Per-metric materiality rules (PRD roadmap item #3, "what changed in the
market") — mirrors freshness.py's and reconciliation_policy.py's own
per-metric registry shape for the same reason: what counts as a material
change is a property of the metric (how much it normally moves, and
whether "any change at all" is itself the noteworthy thing), never a
global constant.

Deliberately pure, DB-independent logic (classify_materiality takes two
plain value dicts, nothing else) — this is the "core comparison logic
working independently of the LLM" the roadmap item asks for: it's plain
Python arithmetic and string formatting, not a model call, and keeps
working correctly with the AI Gateway fully disabled (AI-001's own
"AI is fully removable" invariant).
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

#: "ANY_CHANGE": any field differing at all is material - correct for a
#: reference-terms-style metric (coupon/maturity/etc.), where there is no
#: meaningful "how much did the maturity date move" numeric scale and a
#: revision is rare enough that it's always noteworthy regardless of which
#: field changed.
#: "NUMERIC_THRESHOLD": only compare_field is compared, numerically,
#: against threshold - correct for a metric that moves continuously
#: (a yield, a price, an FX rate) where small day-to-day noise is expected
#: and NOT every change is interesting.
MODE_ANY_CHANGE = "ANY_CHANGE"
MODE_NUMERIC_THRESHOLD = "NUMERIC_THRESHOLD"


@dataclass(frozen=True)
class MaterialityRule:
    metric_id: str
    mode: str
    # Required when mode == NUMERIC_THRESHOLD; ignored otherwise.
    compare_field: str | None = None
    threshold: Decimal | None = None
    # True: threshold is a fraction of the old value (e.g. 0.02 = 2% move).
    # False: threshold is an absolute delta in the field's own units.
    relative: bool = False


GILT_REFERENCE_TERMS_MATERIALITY = MaterialityRule(
    metric_id="GILT_REFERENCE_TERMS", mode=MODE_ANY_CHANGE
)
TREASURY_SECURITY_REFERENCE_TERMS_MATERIALITY = MaterialityRule(
    metric_id="TREASURY_SECURITY_REFERENCE_TERMS", mode=MODE_ANY_CHANGE
)
UK_GILT_NOMINAL_SPOT_CURVE_MATERIALITY = MaterialityRule(
    metric_id="UK_GILT_NOMINAL_SPOT_CURVE", mode=MODE_NUMERIC_THRESHOLD,
    # 5 basis points - a common institutional "that's a real move, not
    # noise" convention for a single day's change in a benchmark yield.
    compare_field="spot_rate_pct", threshold=Decimal("0.05"), relative=False,
)
US_TREASURY_PAR_YIELD_CURVE_MATERIALITY = MaterialityRule(
    metric_id="US_TREASURY_PAR_YIELD_CURVE", mode=MODE_NUMERIC_THRESHOLD,
    compare_field="par_yield_pct", threshold=Decimal("0.05"), relative=False,
)
FX_SPOT_RATE_MATERIALITY = MaterialityRule(
    metric_id="FX_SPOT_RATE", mode=MODE_NUMERIC_THRESHOLD,
    compare_field="rate", threshold=Decimal("0.005"), relative=True,
)
MACRO_CPI_MATERIALITY = MaterialityRule(
    metric_id="MACRO_CPI", mode=MODE_NUMERIC_THRESHOLD,
    compare_field="value", threshold=Decimal("0.1"), relative=False,
)
MACRO_GDP_MATERIALITY = MaterialityRule(
    metric_id="MACRO_GDP", mode=MODE_NUMERIC_THRESHOLD,
    compare_field="value", threshold=Decimal("1"), relative=True,
)
EQUITY_EOD_PRICE_MATERIALITY = MaterialityRule(
    metric_id="EQUITY_EOD_PRICE", mode=MODE_NUMERIC_THRESHOLD,
    compare_field="close_price", threshold=Decimal("0.02"), relative=True,
)
GILT_MARKET_CLOSE_PRICE_MATERIALITY = MaterialityRule(
    metric_id="GILT_MARKET_CLOSE_PRICE", mode=MODE_NUMERIC_THRESHOLD,
    compare_field="clean_price", threshold=Decimal("0.005"), relative=True,
)

DEFAULT_MATERIALITY_RULES: dict[str, MaterialityRule] = {
    rule.metric_id: rule
    for rule in (
        GILT_REFERENCE_TERMS_MATERIALITY,
        TREASURY_SECURITY_REFERENCE_TERMS_MATERIALITY,
        UK_GILT_NOMINAL_SPOT_CURVE_MATERIALITY,
        US_TREASURY_PAR_YIELD_CURVE_MATERIALITY,
        FX_SPOT_RATE_MATERIALITY,
        MACRO_CPI_MATERIALITY,
        MACRO_GDP_MATERIALITY,
        EQUITY_EOD_PRICE_MATERIALITY,
        GILT_MARKET_CLOSE_PRICE_MATERIALITY,
    )
}


def classify_materiality(
    old_value: dict[str, Any], new_value: dict[str, Any], rule: MaterialityRule | None
) -> tuple[bool, str]:
    """Pure function: no DB, no network, no model call - every branch is
    plain arithmetic or string formatting, by design (see module
    docstring). Returns (is_material, a plain-language explanation that
    names the actual numbers, never just a verdict).
    """
    if old_value == new_value:
        return False, "No change in value."

    if rule is None:
        return (
            True,
            "Value changed; no materiality rule is configured for this metric yet, "
            "so any change is treated as material.",
        )

    if rule.mode == MODE_ANY_CHANGE:
        all_keys = {*old_value.keys(), *new_value.keys()}
        changed_fields = sorted(k for k in all_keys if old_value.get(k) != new_value.get(k))
        fields_text = ", ".join(changed_fields)
        return True, f"Reference terms changed ({fields_text}) - always material for this metric."

    assert rule.compare_field is not None  # NUMERIC_THRESHOLD always sets this
    try:
        old_num = Decimal(str(old_value.get(rule.compare_field)))
        new_num = Decimal(str(new_value.get(rule.compare_field)))
    except (InvalidOperation, TypeError):
        return (
            True,
            f"'{rule.compare_field}' changed and could not be compared numerically - "
            "treated as material.",
        )

    delta = new_num - old_num
    sign = "+" if delta >= 0 else ""
    if rule.relative:
        if old_num == 0:
            return True, f"{rule.compare_field} moved from 0 to {new_num} - treated as material."
        move = abs(delta) / abs(old_num)
        is_material = rule.threshold is not None and move >= rule.threshold
        threshold_text = (
            f"{rule.threshold:.2%}" if rule.threshold is not None else "none configured"
        )
        return is_material, (
            f"{rule.compare_field} moved from {old_num} to {new_num} ({sign}{delta}, "
            f"{move:.2%} relative) — {'material' if is_material else 'within normal noise'} "
            f"(threshold: {threshold_text} relative move)."
        )

    is_material = rule.threshold is not None and abs(delta) >= rule.threshold
    threshold_text = str(rule.threshold) if rule.threshold is not None else "none configured"
    return is_material, (
        f"{rule.compare_field} moved from {old_num} to {new_num} ({sign}{delta}) — "
        f"{'material' if is_material else 'within normal noise'} (threshold: {threshold_text})."
    )
