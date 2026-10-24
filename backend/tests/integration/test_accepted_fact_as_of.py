"""Proves accepted_fact_as_of does what current_accepted_fact_at
structurally cannot: reconstruct the fact Talvrin believed true AS OF a
historical knowledge cutoff, rather than silently surfacing today's
revised state.

reconcile.py never deletes or rewrites a superseded row — it closes the
old row's knowledge_range and flips its status to SUPERSEDED, then inserts
a new ACTIVE row. current_accepted_fact_at only ever looks at ACTIVE rows,
so once a correction lands, asking it about the ORIGINAL day returns the
CORRECTED value — exactly the bug a historical "what did Talvrin know on
<date>" question must not reproduce.
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    SUBJECT_TYPE_YIELD_CURVE_POINT,
    curve_point_subject_id,
)
from app.modules.market.queries import accepted_fact_as_of, current_accepted_fact_at

_TENOR = Decimal("10")
_SUBJECT_ID = curve_point_subject_id(_TENOR)
_VALID_DAY = dt.date(2026, 9, 10)
_VALID_RANGE: Range[dt.datetime] = Range(
    lower=dt.datetime.combine(_VALID_DAY, dt.time.min, tzinfo=dt.UTC),
    upper=dt.datetime.combine(_VALID_DAY, dt.time.min, tzinfo=dt.UTC) + dt.timedelta(days=1),
    bounds="[)",
)
# Ingested same afternoon as the market-effective day - realistic for a
# daily publish, and crucially still before the end of that calendar day.
_INGESTED_AT = dt.datetime(2026, 9, 10, 16, 0, tzinfo=dt.UTC)
# Corrected 5 days later - well after _VALID_DAY has ended.
_CORRECTED_AT = dt.datetime(2026, 9, 15, 9, 0, tzinfo=dt.UTC)


async def _seed_corrected_curve_point(session: AsyncSession) -> None:
    old_fact = AcceptedFact(
        subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT,
        subject_id=_SUBJECT_ID,
        metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
        valid_range=_VALID_RANGE,
        knowledge_range=Range(lower=_INGESTED_AT, upper=_CORRECTED_AT, bounds="[)"),
        value={"tenor_years": "10", "spot_rate_pct": "5.100000"},
        status="SUPERSEDED",
    )
    session.add(old_fact)
    await session.flush()

    new_fact = AcceptedFact(
        subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT,
        subject_id=_SUBJECT_ID,
        metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
        valid_range=_VALID_RANGE,
        knowledge_range=Range(lower=_CORRECTED_AT, upper=None, bounds="[)"),
        value={"tenor_years": "10", "spot_rate_pct": "5.250000"},
        status="ACTIVE",
    )
    session.add(new_fact)
    old_fact.superseded_by_id = new_fact.id
    await session.flush()


async def test_as_of_before_correction_returns_the_original_value(
    db_session: AsyncSession,
) -> None:
    await _seed_corrected_curve_point(db_session)

    result = await accepted_fact_as_of(
        db_session,
        subject_id=_SUBJECT_ID,
        metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
        as_of_date=_VALID_DAY,
    )

    assert result is not None
    assert result.value["spot_rate_pct"] == "5.100000", (
        "asking about this date (before the correction landed) must return "
        "the ORIGINAL value, not the one it was later corrected to"
    )
    assert result.status == "SUPERSEDED"


async def test_as_of_after_correction_returns_the_corrected_value(
    db_session: AsyncSession,
) -> None:
    await _seed_corrected_curve_point(db_session)

    # A later as_of_date, past the correction's own knowledge_time, proves
    # this isn't just "always returns the oldest row" - it genuinely tracks
    # the knowledge-time axis forward, same as asking "by 20 September,
    # what's the most recent value you'd learned?" (the correction landed
    # on the 15th, so the answer is the corrected one).
    result = await accepted_fact_as_of(
        db_session,
        subject_id=_SUBJECT_ID,
        metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
        as_of_date=dt.date(2026, 9, 20),
    )

    assert result is not None
    assert result.value["spot_rate_pct"] == "5.250000"
    assert result.status == "ACTIVE"


async def test_as_of_does_not_leak_a_different_days_fact_for_a_time_series_subject(
    db_session: AsyncSession,
) -> None:
    """A genuine time series (the same subject_id/metric_id across many
    calendar days — see curve_ingest.py) must not have one day's fact leak
    into a query naming a DIFFERENT, earlier day that has no fact at all
    yet. Mirrors the real gap found live, 2026-10-22: the latest ORDER BY
    means a cutoff before this subject's only ingestion must still return
    nothing, not accidentally the (future, not-yet-known) row.
    """
    await _seed_corrected_curve_point(db_session)  # earliest knowledge: 2026-09-10 16:00 UTC

    result = await accepted_fact_as_of(
        db_session,
        subject_id=_SUBJECT_ID,
        metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
        as_of_date=dt.date(2026, 9, 9),  # the day before anything was ever ingested
    )

    assert result is None


async def test_current_accepted_fact_at_structurally_cannot_see_the_original_value(
    db_session: AsyncSession,
) -> None:
    """The regression this whole feature exists to fix: a naive 'current'
    lookup for the historical day, called AFTER the correction has already
    landed, silently returns today's revised value - current_accepted_fact_at
    was never wrong for its own (non-historical) purpose, but it is the
    wrong primitive for "what did Talvrin know back then".
    """
    await _seed_corrected_curve_point(db_session)

    naive_result = await current_accepted_fact_at(
        db_session,
        subject_id=_SUBJECT_ID,
        metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
        at=dt.datetime.combine(_VALID_DAY, dt.time.min, tzinfo=dt.UTC),
    )
    historical_result = await accepted_fact_as_of(
        db_session,
        subject_id=_SUBJECT_ID,
        metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
        as_of_date=_VALID_DAY,
    )

    assert naive_result is not None
    assert naive_result.value["spot_rate_pct"] == "5.250000", (
        "current_accepted_fact_at only ever sees ACTIVE rows, so it shows "
        "the CORRECTED value even when asked about the original day"
    )
    assert historical_result is not None
    assert historical_result.value["spot_rate_pct"] == "5.100000"
    assert naive_result.value != historical_result.value


async def test_as_of_with_no_fact_at_all_returns_none(db_session: AsyncSession) -> None:
    result = await accepted_fact_as_of(
        db_session,
        subject_id=uuid.uuid4(),
        metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
        as_of_date=_VALID_DAY,
    )
    assert result is None
