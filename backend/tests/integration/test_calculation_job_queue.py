"""Proves the calculation.calculation_job handoff against real Postgres:
enqueue is idempotent for the same (spec, subject, date), claim_next_job
atomically claims exactly one PENDING row, and run_next_job both succeeds
and fails cleanly - a failing job must be marked FAILED with its reason
recorded, never left CLAIMED forever or allowed to crash the caller.
"""

import datetime as dt
import uuid
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import (
    STATUS_JOB_DONE,
    STATUS_JOB_FAILED,
    STATUS_JOB_PENDING,
    CalculationJob,
    CalculationResult,
    CalculationSpecification,
)
from app.modules.calculation.pipeline.curve_pricing import (
    ModelImpliedPriceComputed,
    ModelImpliedPriceSkipped,
)
from app.modules.calculation.pipeline.job_queue import (
    claim_next_job,
    enqueue_model_implied_price_job,
    run_next_job,
)
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    SUBJECT_TYPE_YIELD_CURVE_POINT,
    curve_point_subject_id,
)
from app.modules.market.pipeline.stages import METRIC_GILT_REFERENCE_TERMS

_AS_OF = dt.date(2026, 9, 14)
_MATURITY = dt.date(2036, 3, 7)
_OPEN_RANGE: Range[dt.datetime] = Range(
    lower=dt.datetime(2003, 2, 27, tzinfo=dt.UTC), upper=None, bounds="[)"
)
_CURVE_DAY_RANGE: Range[dt.datetime] = Range(
    lower=dt.datetime(2026, 9, 14, tzinfo=dt.UTC),
    upper=dt.datetime(2026, 9, 15, tzinfo=dt.UTC),
    bounds="[)",
)
_FLAT_CURVE = {str(t): "5.0" for t in [5, 8, 9, 9.5, 10, 10.5, 11, 15]}


async def _seed_spec(session: AsyncSession, *, status: str = "APPROVED") -> uuid.UUID:
    spec = CalculationSpecification(
        code=f"gilt_price_from_curve_v1.test.{uuid.uuid4().hex[:8]}",
        version="1", status=status, description="test spec",
    )
    session.add(spec)
    await session.flush()
    return spec.id


async def _seed_reference_terms(session: AsyncSession, *, instrument_id: uuid.UUID) -> None:
    session.add(
        AcceptedFact(
            subject_type="INSTRUMENT", subject_id=instrument_id,
            metric_id=METRIC_GILT_REFERENCE_TERMS, valid_range=_OPEN_RANGE,
            knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
            value={
                "instrument_name": "4 1/4% Treasury Stock 2036", "gilt_type": "CONVENTIONAL",
                "coupon_rate": "4.25", "redemption_date": _MATURITY.isoformat(),
                "first_issue_date": "2003-02-27", "dividend_dates": "07-Mar and 07-Sep",
            },
            status="ACTIVE",
        )
    )
    await session.flush()


async def _seed_curve_points(session: AsyncSession) -> None:
    for tenor, rate in _FLAT_CURVE.items():
        session.add(
            AcceptedFact(
                subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT,
                subject_id=curve_point_subject_id(Decimal(tenor)),
                metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE, valid_range=_CURVE_DAY_RANGE,
                knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
                value={"tenor_years": tenor, "spot_rate_pct": rate}, status="ACTIVE",
            )
        )
    await session.flush()


async def test_enqueue_is_idempotent_for_the_same_pending_job(db_session: AsyncSession) -> None:
    spec_id = await _seed_spec(db_session)
    instrument_id = uuid.uuid4()

    first_id = await enqueue_model_implied_price_job(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    second_id = await enqueue_model_implied_price_job(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    assert first_id == second_id
    rows = (
        await db_session.execute(
            select(CalculationJob).where(CalculationJob.subject_id == instrument_id)
        )
    ).scalars().all()
    assert len(rows) == 1


async def test_claim_next_job_marks_it_claimed_and_increments_attempts(
    db_session: AsyncSession,
) -> None:
    spec_id = await _seed_spec(db_session)
    instrument_id = uuid.uuid4()
    job_id = await enqueue_model_implied_price_job(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    claimed = await claim_next_job(db_session)
    await db_session.commit()

    assert claimed is not None
    assert claimed.id == job_id
    assert claimed.attempts == 1

    second_claim = await claim_next_job(db_session)
    assert second_claim is None, "a claimed job must not be claimable again"


async def test_run_next_job_computes_and_marks_done(db_session: AsyncSession) -> None:
    spec_id = await _seed_spec(db_session)
    instrument_id = uuid.uuid4()
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    await _seed_curve_points(db_session)
    await enqueue_model_implied_price_job(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    result = await run_next_job(db_session)

    assert result is not None
    assert isinstance(result.outcome, ModelImpliedPriceComputed)

    job = await db_session.get(CalculationJob, result.job_id)
    assert job is not None
    assert job.status == STATUS_JOB_DONE
    assert job.completed_at is not None

    persisted = (
        await db_session.execute(
            select(CalculationResult).where(CalculationResult.subject_id == instrument_id)
        )
    ).scalar_one_or_none()
    assert persisted is not None
    assert persisted.status == "ACTIVE"


async def test_run_next_job_with_no_pending_jobs_returns_none(db_session: AsyncSession) -> None:
    assert await run_next_job(db_session) is None


async def test_run_next_job_marks_a_skipped_outcome_done_with_reason_recorded(
    db_session: AsyncSession,
) -> None:
    # Missing reference terms - compute_and_persist_model_implied_price
    # returns ModelImpliedPriceSkipped rather than raising, so the job
    # itself is DONE (it ran to completion), not FAILED.
    spec_id = await _seed_spec(db_session)
    instrument_id = uuid.uuid4()
    await _seed_curve_points(db_session)
    await enqueue_model_implied_price_job(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    result = await run_next_job(db_session)

    assert result is not None
    job = await db_session.get(CalculationJob, result.job_id)
    assert job is not None
    assert job.status == STATUS_JOB_DONE
    assert job.last_error is not None
    assert METRIC_GILT_REFERENCE_TERMS in job.last_error


async def test_run_next_job_marks_failed_on_an_unexpected_error_and_does_not_raise(
    db_session: AsyncSession,
) -> None:
    spec_id = await _seed_spec(db_session)
    instrument_id = uuid.uuid4()
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    await _seed_curve_points(db_session)
    await enqueue_model_implied_price_job(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    with patch(
        "app.modules.calculation.pipeline.job_queue.compute_and_persist_model_implied_price",
        side_effect=RuntimeError("boom"),
    ):
        result = await run_next_job(db_session)

    assert result is not None
    assert isinstance(result.outcome, ModelImpliedPriceSkipped)
    assert result.outcome.reason == "unexpected error: boom"

    job = await db_session.get(CalculationJob, result.job_id)
    assert job is not None
    assert job.status == STATUS_JOB_FAILED
    assert job.last_error == "boom"


async def test_full_queue_drains_to_empty(db_session: AsyncSession) -> None:
    spec_id = await _seed_spec(db_session)
    for _ in range(3):
        instrument_id = uuid.uuid4()
        await _seed_reference_terms(db_session, instrument_id=instrument_id)
        await enqueue_model_implied_price_job(
            db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
            calculation_specification_id=spec_id,
        )
    await _seed_curve_points(db_session)
    await db_session.commit()

    processed = 0
    while (result := await run_next_job(db_session)) is not None:
        processed += 1
        assert isinstance(result.outcome, ModelImpliedPriceComputed)

    assert processed == 3
    remaining = (
        await db_session.execute(
            select(CalculationJob).where(CalculationJob.status == STATUS_JOB_PENDING)
        )
    ).scalars().all()
    assert remaining == []
