"""Suppression/status determination for gilt_risk_metrics_v1, per
TAL-FI-GILT-001 Table 13 (docs/Talvrin_Gilt_Analytics_Methodology_Decision.docx).

Scope, honestly bounded: only the cases decidable purely from
`ConventionalGiltInputs`' own fields are implemented here -

  - EX_DIVIDEND tagging: derivable from `next_cash_flow == 0`, the same
    d1=0 convention gilt_price_yield_v1 already uses for ex-dividend
    settlement (see its golden corpus's "-exdiv" cases). Not a suppression -
    Table 13 says "Compute analytics and show 'Ex-dividend'".
  - UNAVAILABLE_FINAL_SETTLEMENT: Table 13's "Final ex-dividend period" -
    "Normal gilt trades cannot settle in the final ex-dividend period
    before maturity" (DMO). Derivable as ex-dividend (next_cash_flow == 0)
    AND the final period (full_quasi_coupon_periods_remaining == 0), since
    n=0 is exactly how gilt_price_yield_v1 already represents "this is the
    last period before redemption".
  - CALCULATION_UNAVAILABLE: Table 13's "Solver/validation failure" -
    derivable by sanity-checking the computed metrics themselves
    (finite and positive, matching gate G3's own "verify positive/finite
    outputs where mathematically expected"). A yield violating the
    mathematical domain (1 + y/f > 0, TAL-FI-GILT-001 §5.1) produces a
    `decimal.InvalidOperation` from a negative base raised to a fractional
    exponent - confirmed empirically, not assumed - which this module
    catches rather than letting propagate or silently returning garbage.

MATURED and NOT_COVERED_BY_METHOD_V1 are also in this enum, but detected in
calculation/pipeline/gilt_risk_metrics_pricing.py, not here - they need the
settlement-date-vs-maturity-date comparison and the reference fact's own
gilt_type field, neither of which `ConventionalGiltInputs` carries. This
module only owns the vocabulary (the enum member) and the cases genuinely
decidable from its own inputs.

Still NOT implemented anywhere, because they need information no code path
in this spec has a wiring path to yet:
  - NO_REFERENCE_PRICE (needs market-observation presence, i.e. an
    accepted_fact lookup - the pricing runner already returns a distinct
    GiltRiskMetricsSkipped for this case today, just not as a persisted
    RiskMetricsStatus, since "no price exists at all" has nothing to
    attach a calculation_result row to)
  - STALE (needs market-observation freshness at DISPLAY time, i.e.
    market/freshness.py's compute_freshness - evidence/service.py's reply
    already surfaces the underlying price fact's own freshness pill
    separately; baking a second, point-in-time-computed STALE flag into
    the persisted calculation_result.value would be wrong the moment
    freshness changes after that write, since staleness is inherently a
    read-time property, not a write-time one)
These belong at a future service/wiring layer, not guessed at here with
fields this pure-math module has no real way to populate correctly.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.modules.calculation.specs.gilt_price_yield_v1.implementation import (
    ConventionalGiltInputs,
)
from app.modules.calculation.specs.gilt_risk_metrics_v1.implementation import (
    RiskMetrics,
    compute_risk_metrics,
)


class RiskMetricsStatus(StrEnum):
    OK = "OK"
    EX_DIVIDEND = "EX_DIVIDEND"
    UNAVAILABLE_FINAL_SETTLEMENT = "UNAVAILABLE_FINAL_SETTLEMENT"
    CALCULATION_UNAVAILABLE = "CALCULATION_UNAVAILABLE"
    #: Detected in gilt_risk_metrics_pricing.py, not here - see module docstring.
    MATURED = "MATURED"
    NOT_COVERED_BY_METHOD_V1 = "NOT_COVERED_BY_METHOD_V1"


@dataclass(frozen=True)
class RiskMetricsOutcome:
    status: RiskMetricsStatus
    metrics: RiskMetrics | None


def _is_sane(metrics: RiskMetrics) -> bool:
    """Gate G3's own validation language: "verify positive/finite outputs
    where mathematically expected". A conventional gilt's duration, DV01
    and convexity are always strictly positive for a valid price/yield
    pair; anything else means the solve went outside its valid domain.
    """
    values = (
        metrics.macaulay_duration,
        metrics.modified_duration,
        metrics.dv01,
        metrics.convexity,
    )
    return all(v.is_finite() and v > 0 for v in values)


def compute_risk_metrics_outcome(
    inputs: ConventionalGiltInputs, yield_decimal: Decimal
) -> RiskMetricsOutcome:
    is_ex_dividend = inputs.next_cash_flow == 0
    is_final_period = inputs.full_quasi_coupon_periods_remaining == 0

    if is_ex_dividend and is_final_period:
        return RiskMetricsOutcome(
            status=RiskMetricsStatus.UNAVAILABLE_FINAL_SETTLEMENT, metrics=None
        )

    try:
        metrics = compute_risk_metrics(inputs, yield_decimal)
    except ArithmeticError:
        return RiskMetricsOutcome(status=RiskMetricsStatus.CALCULATION_UNAVAILABLE, metrics=None)

    if not _is_sane(metrics):
        return RiskMetricsOutcome(status=RiskMetricsStatus.CALCULATION_UNAVAILABLE, metrics=None)

    status = RiskMetricsStatus.EX_DIVIDEND if is_ex_dividend else RiskMetricsStatus.OK
    return RiskMetricsOutcome(status=status, metrics=metrics)
