"""Shared accepted_fact read queries used by more than one module -
consolidated here instead of re-copied per caller, since this exact
query's correctness already caused a real bug once (see memory
"talvrin-reconcile-time-series-gotcha": a naive "current" lookup needs
valid_range-overlap scoping, not just status == ACTIVE).
"""

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.models import AcceptedFact


async def current_accepted_fact_at(
    session: AsyncSession, *, subject_id: uuid.UUID, metric_id: str, at: dt.datetime
) -> AcceptedFact | None:
    """The one ACTIVE accepted_fact for (subject_id, metric_id) whose
    valid_range contains `at` - "what do we currently believe is true for
    this subject/metric as of a point in time". Previously duplicated
    verbatim in evidence/service.py and calculation/pipeline/
    curve_pricing.py; consolidated here rather than adding a third copy
    for monitoring/rule_engine.py.

    Wrong for a metric published once per calendar day (e.g. a yield curve
    point): its valid_range is scoped to exactly that day, so `at` must
    literally fall inside it - the day after ingestion, every call here
    for that subject/metric returns None even though a perfectly good
    latest value exists. Callers wanting "the latest known value
    regardless of what day it is now" (freshness.py's compute_freshness is
    how staleness gets surfaced, not this query) need latest_accepted_fact
    instead - see its docstring for the real bug this distinction fixed.
    """
    return (
        await session.execute(
            select(AcceptedFact).where(
                AcceptedFact.subject_id == subject_id,
                AcceptedFact.metric_id == metric_id,
                AcceptedFact.status == "ACTIVE",
                AcceptedFact.valid_range.contains(at),
            )
        )
    ).scalar_one_or_none()


async def latest_accepted_fact(
    session: AsyncSession, *, subject_id: uuid.UUID, metric_id: str
) -> AcceptedFact | None:
    """The most-recently-valid-as-of ACTIVE fact for (subject_id, metric_id)
    - mirrors evidence/service.py's _latest_curve_date + fetch-at-that-date
    pattern, generalized to a single subject.

    Found via a real bug: monitoring/rule_engine.py originally used
    current_accepted_fact_at(at=now) to pick "the current value" for
    crossing detection. A rule watching a yield-curve point silently
    stopped evaluating anything the calendar day after the curve was last
    ingested - "no current accepted_fact", forever, since that day's own
    valid_range no longer contained the literal present moment - even
    though the most recent published value was still perfectly good
    evidence. A periodic sweep wants the latest known value, not a value
    proven valid at this exact instant.
    """
    return (
        await session.execute(
            select(AcceptedFact)
            .where(
                AcceptedFact.subject_id == subject_id,
                AcceptedFact.metric_id == metric_id,
                AcceptedFact.status == "ACTIVE",
            )
            .order_by(func.lower(AcceptedFact.valid_range).desc())
            .limit(1)
        )
    ).scalar_one_or_none()
