"""Per-metric FreshnessProfile (DATA-002 §14.1) — mirrors
pipeline/reconciliation_policy.py's per-metric registry shape for the same
reason: thresholds are a property of the metric (how often it's actually
expected to change), never a global constant.

Before this module existed, every evidence citation's freshness pill was
hardcoded to `"CURRENT"` regardless of how old the underlying accepted_fact
actually was (evidence/service.py) — a direct violation of D-15
(fail-loud-on-staleness): a BoE curve fetch that silently stopped working
for a week would still have shown "CURRENT" forever. compute_freshness()
is what closes that gap.

DATA-002's own state table:

    CURRENT     | Within configured freshness SLO.
    DELAYED     | Beyond SLO but within delay tolerance.
    STALE       | Beyond stale threshold.
    UNAVAILABLE | No usable source or rights withdrawn.
    SUSPENDED   | Required monitoring input cannot be evaluated within
                  coverage SLO (PLT-MON-001 dead-man semantics).

SUSPENDED is deliberately not computed here: it is explicitly a monitoring-
coverage concept (PLT-MON-001), and no monitoring module exists yet (P3).
"No usable source or rights withdrawn" (the other half of UNAVAILABLE) is
also not this module's job — a withdrawn/denied rights profile is already
handled upstream by the PDP before evidence assembly ever reaches a
citation. What this module DOES own is the purely elapsed-time half of
UNAVAILABLE: a value old enough that showing it "STALE" is no longer
honest either.

The four thresholds are read as ascending, cumulative boundaries — the
DMO/DATA-002 table doesn't pin down the exact edges between DELAYED/STALE/
UNAVAILABLE beyond "beyond X", so this is a documented interpretation
(the standard multi-tier-threshold reading), not a literal transcription:

    age <= freshness_slo                       -> CURRENT
    freshness_slo < age <= delayed_after        -> DELAYED
    delayed_after < age <= stale_after          -> STALE
    stale_after < age <= unavailable_after      -> STALE (extended tolerance)
    age > unavailable_after (if configured)     -> UNAVAILABLE

unavailable_after is optional: some metrics (e.g. gilt reference terms —
coupon/maturity essentially never change) have no meaningful "too old to
show at all" cutoff and should stay STALE indefinitely rather than
disappear.

Deliberately NOT modelled yet (DATA-002's fuller FreshnessProfile schema
also has market_hours_rule/holiday_calendar_id/expected_publish_schedule/
coverage_expectation): this is elapsed-wall-clock-time only. A BoE curve
published Friday is not really "DELAYED" purely for being a calendar
weekend old — that nuance needs DATA-002 §15's source-health/coverage
tracking, which doesn't exist yet either. Flagged here rather than
silently assumed correct.
"""

import datetime as dt
from dataclasses import dataclass

STATE_CURRENT = "CURRENT"
STATE_DELAYED = "DELAYED"
STATE_STALE = "STALE"
STATE_UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class FreshnessProfile:
    metric_id: str
    freshness_slo: dt.timedelta
    delayed_after: dt.timedelta
    stale_after: dt.timedelta
    unavailable_after: dt.timedelta | None = None


GILT_REFERENCE_TERMS_FRESHNESS = FreshnessProfile(
    metric_id="GILT_REFERENCE_TERMS",
    # Coupon/maturity/day-count don't change day to day - a multi-month SLO
    # is correct here, not an oversight copied from a daily price feed.
    freshness_slo=dt.timedelta(days=30),
    delayed_after=dt.timedelta(days=90),
    stale_after=dt.timedelta(days=365),
    unavailable_after=None,
)

UK_GILT_NOMINAL_SPOT_CURVE_FRESHNESS = FreshnessProfile(
    metric_id="UK_GILT_NOMINAL_SPOT_CURVE",
    # BoE publishes this once per UK business day.
    freshness_slo=dt.timedelta(days=1),
    delayed_after=dt.timedelta(days=3),
    stale_after=dt.timedelta(days=7),
    unavailable_after=dt.timedelta(days=30),
)

MODEL_IMPLIED_CLEAN_PRICE_FRESHNESS = FreshnessProfile(
    metric_id="MODEL_IMPLIED_CLEAN_PRICE",
    # Tracks the curve it's derived from - same cadence/thresholds.
    freshness_slo=dt.timedelta(days=1),
    delayed_after=dt.timedelta(days=3),
    stale_after=dt.timedelta(days=7),
    unavailable_after=dt.timedelta(days=30),
)

FX_SPOT_RATE_FRESHNESS = FreshnessProfile(
    metric_id="FX_SPOT_RATE",
    # Frankfurter (ECB reference rates) publishes once per EU business day,
    # not intraday - same cadence/thresholds as the BoE curve.
    freshness_slo=dt.timedelta(days=1),
    delayed_after=dt.timedelta(days=3),
    stale_after=dt.timedelta(days=7),
    unavailable_after=dt.timedelta(days=14),
)

MACRO_GDP_FRESHNESS = FreshnessProfile(
    metric_id="MACRO_GDP",
    # Quarterly national-accounts data with real publication lag; revisions
    # arrive on their own schedule, so this should never flip to
    # UNAVAILABLE just because a new quarter hasn't printed yet.
    freshness_slo=dt.timedelta(days=100),
    delayed_after=dt.timedelta(days=150),
    stale_after=dt.timedelta(days=400),
    unavailable_after=None,
)

MACRO_CPI_FRESHNESS = FreshnessProfile(
    metric_id="MACRO_CPI",
    # Monthly cadence - a much shorter SLO than GDP.
    freshness_slo=dt.timedelta(days=35),
    delayed_after=dt.timedelta(days=60),
    stale_after=dt.timedelta(days=120),
    unavailable_after=None,
)

EQUITY_EOD_PRICE_FRESHNESS = FreshnessProfile(
    metric_id="EQUITY_EOD_PRICE",
    # Free-tier Twelve Data is end-of-day only - "one trading day old" is
    # CURRENT, mirroring the curve profile rather than a live-tick SLO.
    freshness_slo=dt.timedelta(days=1),
    delayed_after=dt.timedelta(days=3),
    stale_after=dt.timedelta(days=7),
    unavailable_after=dt.timedelta(days=30),
)

GILT_MARKET_CLOSE_PRICE_FRESHNESS = FreshnessProfile(
    metric_id="GILT_MARKET_CLOSE_PRICE",
    # Tradeweb publishes one EOD close per UK business day - same cadence
    # as the curve/model-implied profiles it sits alongside in a reply.
    freshness_slo=dt.timedelta(days=1),
    delayed_after=dt.timedelta(days=3),
    stale_after=dt.timedelta(days=7),
    unavailable_after=dt.timedelta(days=30),
)

DEFAULT_PROFILES: dict[str, FreshnessProfile] = {
    profile.metric_id: profile
    for profile in (
        GILT_REFERENCE_TERMS_FRESHNESS,
        UK_GILT_NOMINAL_SPOT_CURVE_FRESHNESS,
        MODEL_IMPLIED_CLEAN_PRICE_FRESHNESS,
        FX_SPOT_RATE_FRESHNESS,
        MACRO_GDP_FRESHNESS,
        MACRO_CPI_FRESHNESS,
        EQUITY_EOD_PRICE_FRESHNESS,
        GILT_MARKET_CLOSE_PRICE_FRESHNESS,
    )
}


def compute_freshness(
    *, metric_id: str, knowledge_time: dt.datetime, now: dt.datetime | None = None
) -> str:
    """knowledge_time is when the fact became known to Talvrin (an
    accepted_fact's knowledge_range lower bound) - per DATA-002's own
    bitemporal model, freshness is about how current OUR knowledge is, not
    how current the real-world state being described is.

    No registered profile for a metric is a configuration gap, not a
    reason to silently claim CURRENT - raises, matching D-15's fail-loud
    intent rather than defaulting to the best-case state.
    """
    profile = DEFAULT_PROFILES.get(metric_id)
    if profile is None:
        raise KeyError(f"no FreshnessProfile registered for metric_id={metric_id!r}")

    moment = now or dt.datetime.now(dt.UTC)
    age = moment - knowledge_time

    if age <= profile.freshness_slo:
        return STATE_CURRENT
    if age <= profile.delayed_after:
        return STATE_DELAYED
    if age <= profile.stale_after:
        return STATE_STALE
    if profile.unavailable_after is not None and age > profile.unavailable_after:
        return STATE_UNAVAILABLE
    return STATE_STALE
