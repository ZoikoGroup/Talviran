"""P2's job-table handoff: enqueue_model_implied_price_job() is what a
request/ingest path should call instead of invoking
curve_pricing.compute_and_persist_model_implied_price directly in its own
transaction (ENG-ARCH-003 risk #9 - "calling calculation.implementation
directly/synchronously ... hardens into a dependency nobody wants to
refactor later"). claim_next_job()/run_next_job() are what a real
out-of-process worker (scripts/run_calculation_worker.py) uses to drain
the queue.

Deliberately a plain Postgres queue - `FOR UPDATE SKIP LOCKED` gives
correct concurrent claiming across multiple worker processes with no
broker, matching this pack's actual scale (ENG-ARCH-003 risk #7: nowhere
near the ~5,000 events/min threshold that would justify Kafka/Temporal).
"""

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import (
    STATUS_JOB_CLAIMED,
    STATUS_JOB_DONE,
    STATUS_JOB_FAILED,
    STATUS_JOB_PENDING,
    CalculationJob,
)
from app.modules.calculation.pipeline.curve_pricing import (
    ModelImpliedPriceComputed,
    ModelImpliedPriceSkipped,
    compute_and_persist_model_implied_price,
)


async def enqueue_model_implied_price_job(
    session: AsyncSession,
    *,
    instrument_id: uuid.UUID,
    as_of_date: dt.date,
    calculation_specification_id: uuid.UUID,
) -> uuid.UUID:
    """Idempotent: an existing PENDING or CLAIMED job for the same
    (spec, subject, date) is reused rather than duplicated - re-enqueuing
    after, say, a second curve publish for the same day must not pile up
    redundant work ahead of a slow worker.
    """
    existing = (
        await session.execute(
            select(CalculationJob).where(
                CalculationJob.calculation_specification_id == calculation_specification_id,
                CalculationJob.subject_id == instrument_id,
                CalculationJob.as_of_date == as_of_date,
                CalculationJob.status.in_([STATUS_JOB_PENDING, STATUS_JOB_CLAIMED]),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id

    job = CalculationJob(
        calculation_specification_id=calculation_specification_id,
        subject_type="INSTRUMENT",
        subject_id=instrument_id,
        as_of_date=as_of_date,
        status=STATUS_JOB_PENDING,
    )
    session.add(job)
    await session.flush()
    return job.id


async def claim_next_job(session: AsyncSession) -> CalculationJob | None:
    """Atomically claims one PENDING job for this worker - `SKIP LOCKED`
    means a second, concurrently-running worker moves on to the next row
    instead of blocking on this one.
    """
    job = (
        await session.execute(
            select(CalculationJob)
            .where(CalculationJob.status == STATUS_JOB_PENDING)
            .order_by(CalculationJob.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    ).scalar_one_or_none()
    if job is None:
        return None

    job.status = STATUS_JOB_CLAIMED
    job.claimed_at = dt.datetime.now(dt.UTC)
    job.attempts += 1
    await session.flush()
    return job


@dataclass(frozen=True)
class JobRun:
    job_id: uuid.UUID
    outcome: ModelImpliedPriceComputed | ModelImpliedPriceSkipped


async def run_next_job(session: AsyncSession) -> JobRun | None:
    """Claims and runs exactly one job, committing internally so each job
    owns its own transaction - callers (the worker script) should give
    this a dedicated session per call, not interleave it with other
    uncommitted work on the same session.

    Never lets compute_and_persist's own exception escape past this
    boundary: a single bad job (a corrupted fact, an unexpected
    implementation error) must mark itself FAILED with the reason
    recorded and let the worker move on, not crash a loop that may be
    partway through draining many other jobs. A raised exception also
    leaves the session's transaction unusable until rolled back, so the
    FAILED write happens as a fresh statement after that rollback, keyed
    by the job's id rather than the (now possibly stale) ORM object.
    """
    job = await claim_next_job(session)
    if job is None:
        return None
    # Make the claim durable before attempting the compute - if the
    # compute step fails, only its own work should be rolled back below,
    # never this claim.
    await session.commit()

    job_id = job.id
    try:
        outcome = await compute_and_persist_model_implied_price(
            session,
            instrument_id=job.subject_id,
            as_of_date=job.as_of_date,
            calculation_specification_id=job.calculation_specification_id,
        )
    except Exception as exc:  # noqa: BLE001 - deliberately broad: see docstring
        await session.rollback()
        await session.execute(
            update(CalculationJob)
            .where(CalculationJob.id == job_id)
            .values(
                status=STATUS_JOB_FAILED,
                last_error=str(exc)[:1000],
                completed_at=dt.datetime.now(dt.UTC),
            )
        )
        await session.commit()
        return JobRun(
            job_id=job_id,
            outcome=ModelImpliedPriceSkipped(reason=f"unexpected error: {exc}"),
        )

    last_error = outcome.reason[:1000] if isinstance(outcome, ModelImpliedPriceSkipped) else None
    await session.execute(
        update(CalculationJob)
        .where(CalculationJob.id == job_id)
        .values(status=STATUS_JOB_DONE, completed_at=dt.datetime.now(dt.UTC), last_error=last_error)
    )
    await session.commit()
    return JobRun(job_id=job_id, outcome=outcome)
