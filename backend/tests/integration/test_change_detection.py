"""Integration tests for the before/after diff engine (PRD roadmap item
#3, "what changed in the market") — proves detect_change finds the right
"before" state for both real shapes: a correction (via superseded_by_id)
and a genuine time-series step (the two most recent ACTIVE facts), and
that it honestly reports when there's nothing to compare against yet.
"""

import datetime as dt
import uuid

from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.change_detection import DetectedChange, NoChangeDetected, detect_change
from app.modules.market.models import AcceptedFact

_METRIC = "TEST_METRIC"


async def _seed_corrected_fact(session: AsyncSession, *, subject_id: uuid.UUID) -> None:
    """Same valid_range across both versions - a genuine correction, not a
    new real-world period (mirrors reconcile.py's own correction shape).
    """
    valid_range: Range[dt.datetime] = Range(
        lower=dt.datetime(2026, 9, 10, tzinfo=dt.UTC),
        upper=dt.datetime(2026, 9, 11, tzinfo=dt.UTC),
        bounds="[)",
    )
    old_fact = AcceptedFact(
        subject_type="TEST_SUBJECT", subject_id=subject_id, metric_id=_METRIC,
        valid_range=valid_range,
        knowledge_range=Range(
            lower=dt.datetime(2026, 9, 10, 16, 0, tzinfo=dt.UTC),
            upper=dt.datetime(2026, 9, 15, 9, 0, tzinfo=dt.UTC), bounds="[)",
        ),
        value={"spot_rate_pct": "5.100000"}, status="SUPERSEDED",
    )
    session.add(old_fact)
    await session.flush()
    new_fact = AcceptedFact(
        subject_type="TEST_SUBJECT", subject_id=subject_id, metric_id=_METRIC,
        valid_range=valid_range,
        knowledge_range=Range(
            lower=dt.datetime(2026, 9, 15, 9, 0, tzinfo=dt.UTC), upper=None, bounds="[)"
        ),
        value={"spot_rate_pct": "5.250000"}, status="ACTIVE",
    )
    session.add(new_fact)
    await session.flush()  # new_fact.id must exist before being assigned below
    old_fact.superseded_by_id = new_fact.id
    await session.flush()


async def _seed_time_series_pair(session: AsyncSession, *, subject_id: uuid.UUID) -> None:
    """Different valid_range, both ACTIVE, neither supersedes the other -
    a genuine time series (e.g. a yield-curve tenor, one row per real-world
    day — mirrors curve_ingest.py's own shape).
    """
    for day, rate in [(9, "5.000000"), (10, "5.400000")]:
        valid_range: Range[dt.datetime] = Range(
            lower=dt.datetime(2026, 9, day, tzinfo=dt.UTC),
            upper=dt.datetime(2026, 9, day + 1, tzinfo=dt.UTC), bounds="[)",
        )
        session.add(
            AcceptedFact(
                subject_type="TEST_SUBJECT", subject_id=subject_id, metric_id=_METRIC,
                valid_range=valid_range,
                knowledge_range=Range(
                    lower=dt.datetime(2026, 9, day, 16, 0, tzinfo=dt.UTC), upper=None, bounds="[)"
                ),
                value={"spot_rate_pct": rate}, status="ACTIVE",
            )
        )
    await session.flush()


async def test_detect_change_via_correction(db_session: AsyncSession) -> None:
    subject_id = uuid.uuid4()
    await _seed_corrected_fact(db_session, subject_id=subject_id)

    result = await detect_change(db_session, subject_id=subject_id, metric_id=_METRIC)

    assert isinstance(result, DetectedChange)
    assert result.old_value["spot_rate_pct"] == "5.100000"
    assert result.new_value["spot_rate_pct"] == "5.250000"
    assert result.is_material is True  # no rule registered for TEST_METRIC -> defaults material
    assert "no materiality rule" in result.explanation


async def test_detect_change_via_time_series_step(db_session: AsyncSession) -> None:
    subject_id = uuid.uuid4()
    await _seed_time_series_pair(db_session, subject_id=subject_id)

    result = await detect_change(db_session, subject_id=subject_id, metric_id=_METRIC)

    assert isinstance(result, DetectedChange)
    assert result.old_value["spot_rate_pct"] == "5.000000"
    assert result.new_value["spot_rate_pct"] == "5.400000"


async def test_detect_change_with_no_fact_at_all(db_session: AsyncSession) -> None:
    result = await detect_change(db_session, subject_id=uuid.uuid4(), metric_id=_METRIC)

    assert isinstance(result, NoChangeDetected)
    assert "no accepted fact exists" in result.reason


async def test_detect_change_with_only_one_recorded_value(db_session: AsyncSession) -> None:
    subject_id = uuid.uuid4()
    session_fact = AcceptedFact(
        subject_type="TEST_SUBJECT", subject_id=subject_id, metric_id=_METRIC,
        valid_range=Range(
            lower=dt.datetime(2026, 9, 10, tzinfo=dt.UTC),
            upper=dt.datetime(2026, 9, 11, tzinfo=dt.UTC), bounds="[)",
        ),
        knowledge_range=Range(
            lower=dt.datetime(2026, 9, 10, tzinfo=dt.UTC), upper=None, bounds="[)"
        ),
        value={"spot_rate_pct": "5.000000"}, status="ACTIVE",
    )
    db_session.add(session_fact)
    await db_session.flush()

    result = await detect_change(db_session, subject_id=subject_id, metric_id=_METRIC)

    assert isinstance(result, NoChangeDetected)
    assert "only one recorded value" in result.reason


async def test_detect_change_uses_the_real_registered_materiality_rule(
    db_session: AsyncSession,
) -> None:
    """Same time-series shape as above, but under a real metric_id with a
    registered rule (UK_GILT_NOMINAL_SPOT_CURVE, 5bp threshold) - the 40bp
    move seeded here must be classified material using the REAL rule, not
    the "no rule configured" default the other tests exercise.
    """
    real_metric_id = "UK_GILT_NOMINAL_SPOT_CURVE"
    subject_id = uuid.uuid4()
    for day, rate in [(9, "5.000000"), (10, "5.400000")]:
        db_session.add(
            AcceptedFact(
                subject_type="TEST_SUBJECT", subject_id=subject_id, metric_id=real_metric_id,
                valid_range=Range(
                    lower=dt.datetime(2026, 9, day, tzinfo=dt.UTC),
                    upper=dt.datetime(2026, 9, day + 1, tzinfo=dt.UTC), bounds="[)",
                ),
                knowledge_range=Range(
                    lower=dt.datetime(2026, 9, day, 16, 0, tzinfo=dt.UTC), upper=None, bounds="[)"
                ),
                value={"spot_rate_pct": rate}, status="ACTIVE",
            )
        )
    await db_session.flush()

    result = await detect_change(db_session, subject_id=subject_id, metric_id=real_metric_id)

    assert isinstance(result, DetectedChange)
    assert result.is_material is True
    assert "5.000000" in result.explanation
    assert "5.400000" in result.explanation
