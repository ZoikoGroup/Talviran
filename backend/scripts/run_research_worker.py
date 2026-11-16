"""The evaluator process for research.research_job (UAT gap-analysis G15) -
claims one QUEUED job at a time (FOR UPDATE SKIP LOCKED, same discipline
as calculation/pipeline/job_queue.py) and runs the same composition logic
POST /api/v1/research uses synchronously
(app.modules.api.v1.research.compose_and_persist_research_answer), so a
slow or stuck research request has a real "running" state to show and a
real cancellation point instead of an open HTTP connection the client can
only give up on.

Cancellation is cooperative, checked at the one safe point that actually
exists: after the answer is fully composed (every write flushed to this
session) but before it is committed. A cancel requested before that point
discards the whole attempt - the user's own message and the composed
reply are rolled back together, so a canceled job never leaves a half
reply sitting in a conversation. A cancel requested after commit is
already too late to mean anything (the same "a canceled browser
subscription is not proof the server job stopped" acknowledgment
jobs_service.request_cancel's own docstring makes) - this worker does not
pretend otherwise.

Same per-account iteration shape as run_monitoring_worker.py and the same
reason: research.research_job is account-scoped (FORCE ROW LEVEL
SECURITY), but nothing schedules which account's queue to check next, so
every sweep walks every account looking for its next queued job.

Run once (a cron target):

    uv run python -m scripts.run_research_worker

Run continuously with a poll interval (what a real deployment would run):

    uv run python -m scripts.run_research_worker --loop --poll-seconds 5
"""

import argparse
import asyncio
import logging
import sys
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.core.http_client import get_http_client
from app.modules.api.v1.research import compose_and_persist_research_answer
from app.modules.identity.models import Account, Principal
from app.modules.identity.service import apply_rls_context
from app.modules.research import jobs_service
from app.modules.research.keys import get_key_wrapper
from app.modules.research.service import account_dek

logger = logging.getLogger(__name__)


async def _process_one_job(session: AsyncSession, job: jobs_service.ResearchJob) -> None:
    if job.status == jobs_service.STATUS_CANCELED:
        # claim_next_queued_job already resolved this one: it was
        # cancelled while still QUEUED, never actually claimed for real
        # work, so there is nothing left to do (its own UPDATE already set
        # completed_at). Composing an answer for it now would be pure
        # waste - and would itself violate "late results must not appear
        # in another conversation" by writing a reply nobody can see.
        return

    dek = await account_dek(session, account_id=job.account_id, wrapper=get_key_wrapper())

    if await jobs_service.is_cancel_requested(session, job_id=job.id):
        # A RUNNING job (genuinely claimed by this call) whose cancel
        # arrived between claim_next_queued_job's commit and this check -
        # nothing has been written yet, so nothing to roll back either.
        await jobs_service.mark_canceled(session, job_id=job.id)
        await session.commit()
        return

    try:
        result = await compose_and_persist_research_answer(
            session,
            account_id=job.account_id,
            principal_id=job.principal_id,
            conversation_id=job.conversation_id,
            query=job.query(dek=dek),
            model=job.model,
            dek=dek,
            http=get_http_client(),
            request_id=str(job.id),
        )
    except Exception as exc:  # noqa: BLE001 - must never crash the sweep loop
        await session.rollback()
        logger.exception("research_job %s failed during composition", job.id)
        await apply_rls_context(session, account_id=job.account_id, principal_id=job.principal_id)
        await jobs_service.mark_failed(
            session, job_id=job.id, error_message=f"{type(exc).__name__}: research failed"
        )
        await session.commit()
        return

    if await jobs_service.is_cancel_requested(session, job_id=job.id):
        # The only point that matters: everything compose_and_persist_
        # research_answer flushed (the user's message, the assistant's
        # reply, the evidence bundle link) is still uncommitted here - a
        # rollback discards all of it together, so a late cancel never
        # leaves a half-visible answer in the conversation.
        await session.rollback()
        await apply_rls_context(session, account_id=job.account_id, principal_id=job.principal_id)
        await jobs_service.mark_canceled(session, job_id=job.id)
        await session.commit()
        return

    await jobs_service.mark_completed(
        session,
        job_id=job.id,
        conversation_id=job.conversation_id,
        result_message_id=result.message_id,
        result_payload=result.model_dump(mode="json"),
        dek=dek,
    )
    await session.commit()


async def _sweep_account(
    session: AsyncSession, *, account_id: uuid.UUID, principal_id: uuid.UUID
) -> int:
    processed = 0
    while True:
        # Re-applied every iteration, not just once per account: each
        # commit inside _process_one_job ends the transaction that held it
        # (SET LOCAL is transaction-scoped), so claim_next_queued_job would
        # otherwise run with no RLS context from the second job onward and
        # silently find nothing - the exact bug class this codebase has
        # already hit and fixed elsewhere (monitoring/service.py,
        # run_monitoring_worker.py's own per-rule re-apply).
        await apply_rls_context(session, account_id=account_id, principal_id=principal_id)
        job = await jobs_service.claim_next_queued_job(session)
        if job is None:
            break
        await session.commit()
        await apply_rls_context(session, account_id=account_id, principal_id=principal_id)
        await _process_one_job(session, job)
        processed += 1
    return processed


async def sweep_once() -> int:
    factory = get_session_factory()
    total = 0
    async with factory() as session:
        account_ids = (await session.execute(select(Account.id))).scalars().all()
        for account_id in account_ids:
            await apply_rls_context(session, account_id=account_id, principal_id=account_id)
            principal_id = (
                await session.execute(
                    select(Principal.id).where(Principal.account_id == account_id).limit(1)
                )
            ).scalar_one_or_none()
            if principal_id is None:
                continue
            total += await _sweep_account(
                session, account_id=account_id, principal_id=principal_id
            )
    return total


async def run(*, loop: bool, poll_seconds: float) -> int:
    processed = await sweep_once()
    print(f"Processed {processed} research job(s).")
    if not loop:
        return 0

    print(f"Polling every {poll_seconds}s (Ctrl+C to stop)...")
    try:
        while True:
            await asyncio.sleep(poll_seconds)
            processed = await sweep_once()
            if processed:
                print(f"Processed {processed} research job(s).")
    except KeyboardInterrupt:
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop", action="store_true", help="keep polling instead of exiting")
    parser.add_argument(
        "--poll-seconds", type=float, default=5.0, help="seconds between sweeps in --loop mode"
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run(loop=args.loop, poll_seconds=args.poll_seconds)))


if __name__ == "__main__":
    main()
