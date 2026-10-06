"""P2's job-table handoff: enqueue_model_implied_price_job()/
enqueue_gilt_risk_metrics_job() are what a request/ingest path should call
instead of invoking a compute_and_persist_* function directly in its own
transaction (ENG-ARCH-003 risk #9 - "calling calculation.implementation
directly/synchronously ... hardens into a dependency nobody wants to
refactor later"). claim_next_job()/run_next_job() are what a real
out-of-process worker (scripts/run_calculation_worker.py) uses to drain
the queue.

Deliberately a plain Postgres queue - `FOR UPDATE SKIP LOCKED` gives
correct concurrent claiming across multiple worker processes with no
broker, matching this pack's actual scale (ENG-ARCH-003 risk #7: nowhere
near the ~5,000 events/min threshold that would justify Kafka/Temporal).

claim_next_job() claims ANY pending job regardless of which spec it's for
(calculation_job has no spec-specific columns to filter on) - so run_next_
job() below MUST dispatch on the claimed job's own calculation_specification
code rather than assume a single compute function, or a second job type
sharing this same queue would risk the wrong compute function running
against the wrong job's data. Dispatch is a plain if/else, not a
pre-built dict keyed by function reference - a dict captured at import
time would silently stop working with
test_calculation_job_queue.py's own `patch("...job_queue.compute_and_
persist_model_implied_price", ...)`, since patching a module attribute
doesn't retroactively change a reference already stored in a dict. Two
compute functions doesn't yet justify a real pluggable registry
(ENG-ARCH-003 risk #7's "prove it in Postgres first" applies here too,
not just to the broker-vs-no-broker choice).
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
    CalculationSpecification,
)
from app.modules.calculation.pipeline.curve_pricing import (
    ModelImpliedPriceComputed,
    ModelImpliedPriceSkipped,
    compute_and_persist_model_implied_price,
)
from app.modules.calculation.pipeline.gilt_risk_metrics_pricing import (
    GiltRiskMetricsComputed,
    GiltRiskMetricsSkipped,
    compute_and_persist_gilt_risk_metrics,
)

#: Spec codes in dev/test fixtures carry a `.test.<hash>` suffix
#: (e.g. "gilt_risk_metrics_v1.test.ab12cd34") - matching on this prefix,
#: not an exact string, is what makes dispatch work identically in both
#: a seeded-dev spec row and a test's own throwaway spec row.
_GILT_RISK_METRICS_SPEC_PREFIX = "gilt_risk_metrics_v1"


async def _enqueue_job(
    session: AsyncSession,
    *,
    instrument_id: uuid.UUID,
    as_of_date: dt.date,
    calculation_specification_id: uuid.UUID,
) -> uuid.UUID:
    """Idempotent: an existing PENDING or CLAIMED job for the same
    (spec, subject, date) is reused rather than duplicated - re-enqueuing
    after, say, a second curve publish for the same day must not pile up
    redundant work ahead of a slow worker. Generic across specs -
    calculation_job carries no spec-specific columns - so both
    enqueue_model_implied_price_job and enqueue_gilt_risk_metrics_job
    below are thin, clearly-named wrappers over this one implementation.
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


async def enqueue_model_implied_price_job(
    session: AsyncSession,
    *,
    instrument_id: uuid.UUID,
    as_of_date: dt.date,
    calculation_specification_id: uuid.UUID,
) -> uuid.UUID:
    return await _enqueue_job(
        session,
        instrument_id=instrument_id,
        as_of_date=as_of_date,
        calculation_specification_id=calculation_specification_id,
    )


async def enqueue_gilt_risk_metrics_job(
    session: AsyncSession,
    *,
    instrument_id: uuid.UUID,
    as_of_date: dt.date,
    calculation_specification_id: uuid.UUID,
) -> uuid.UUID:
    return await _enqueue_job(
        session,
        instrument_id=instrument_id,
        as_of_date=as_of_date,
        calculation_specification_id=calculation_specification_id,
    )


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


JobOutcome = (
    ModelImpliedPriceComputed
    | ModelImpliedPriceSkipped
    | GiltRiskMetricsComputed
    | GiltRiskMetricsSkipped
)


@dataclass(frozen=True)
class JobRun:
    job_id: uuid.UUID
    outcome: JobOutcome


async def run_next_job(session: AsyncSession) -> JobRun | None:
    """Claims and runs exactly one job, committing internally so each job
    owns its own transaction - callers (the worker script) should give
    this a dedicated session per call, not interleave it with other
    uncommitted work on the same session.

    Dispatches on the claimed job's own calculation_specification.code -
    see this module's own docstring for why that must be a plain if/else
    here, not a dict built at import time.

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
    spec = await session.get(CalculationSpecification, job.calculation_specification_id)
    is_risk_metrics = spec is not None and spec.code.startswith(_GILT_RISK_METRICS_SPEC_PREFIX)

    try:
        if is_risk_metrics:
            outcome: JobOutcome = await compute_and_persist_gilt_risk_metrics(
                session,
                instrument_id=job.subject_id,
                as_of_date=job.as_of_date,
                calculation_specification_id=job.calculation_specification_id,
            )
        else:
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
        skipped: JobOutcome = (
            GiltRiskMetricsSkipped(reason=f"unexpected error: {exc}")
            if is_risk_metrics
            else ModelImpliedPriceSkipped(reason=f"unexpected error: {exc}")
        )
        return JobRun(job_id=job_id, outcome=skipped)

    last_error = (
        outcome.reason[:1000]
        if isinstance(outcome, ModelImpliedPriceSkipped | GiltRiskMetricsSkipped)
        else None
    )
    await session.execute(
        update(CalculationJob)
        .where(CalculationJob.id == job_id)
        .values(status=STATUS_JOB_DONE, completed_at=dt.datetime.now(dt.UTC), last_error=last_error)
    )
    await session.commit()
    return JobRun(job_id=job_id, outcome=outcome)
