"""POST /api/v1/research/jobs (UAT gap-analysis G15) - the async,
cancellable counterpart to POST /api/v1/research. That endpoint is
unchanged and still the synchronous path; this one hands back a job_id
immediately and lets scripts/run_research_worker.py do the actual work,
so a slow or stuck research request has something real to show
("queued"/"running") and something real to cancel, instead of a client
just giving up on an open HTTP connection.

research.research_job's RLS policy (migration 0040) already makes "no
such job" and "not your job" indistinguishable - the same not-found
pattern every other account-scoped resource in this codebase uses - so
no extra visibility check is needed beyond the plain lookup.
"""

from __future__ import annotations

import dataclasses
import uuid

from fastapi import APIRouter, Header, status
from pydantic import BaseModel, Field

from app.core.errors import ErrorCode, TalvrinAPIError
from app.modules.api.v1.deps import DekDep, IdentityDep, SessionDep
from app.modules.api.v1.research import CitationOut, FactTableOut, ResearchOut
from app.modules.identity import service as identity_service
from app.modules.research import jobs_service
from app.modules.research import service as research_service

router = APIRouter(tags=["research"])


class ResearchJobIn(BaseModel):
    conversation_id: uuid.UUID
    query: str = Field(min_length=1, max_length=research_service.MAX_MESSAGE_LENGTH)
    model: str | None = None


class ResearchJobOut(BaseModel):
    job_id: uuid.UUID
    status: str
    conversation_id: uuid.UUID
    created_at: str
    started_at: str | None
    completed_at: str | None
    result: ResearchOut | None
    error: str | None


def _not_found() -> TalvrinAPIError:
    return TalvrinAPIError(code=ErrorCode.NOT_FOUND, message="Not found.")


def _job_out(job: jobs_service.ResearchJob, *, dek: bytes) -> ResearchJobOut:
    result_payload = job.result(dek=dek) if job.status == jobs_service.STATUS_COMPLETED else None
    result = None
    if result_payload is not None:
        facts = result_payload.get("facts")
        result = ResearchOut(
            request_id=result_payload["request_id"],
            generated_at=result_payload["generated_at"],
            evidence_bundle_id=result_payload["evidence_bundle_id"],
            allowed_output_type=result_payload["allowed_output_type"],
            message_id=result_payload["message_id"],
            text=result_payload["text"],
            facts=FactTableOut(title=facts["title"], rows=facts["rows"]) if facts else None,
            citations=[CitationOut(**c) for c in result_payload["citations"]],
            note=result_payload["note"],
        )
    return ResearchJobOut(
        job_id=job.id,
        status=job.status,
        conversation_id=job.conversation_id,
        created_at=job.created_at.isoformat(),
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        result=result,
        error=job.error_message,
    )


@router.post(
    "/research/jobs", status_code=status.HTTP_201_CREATED, response_model=ResearchJobOut
)
async def create_research_job(
    body: ResearchJobIn,
    db: SessionDep,
    identity: IdentityDep,
    dek: DekDep,
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> ResearchJobOut:
    """Quota is checked here, once, at job creation - not re-checked by the
    worker - matching the synchronous endpoint's own placement (before any
    real work starts) and avoiding a queued job that's guaranteed to fail
    quota the moment a worker picks it up."""
    from app.modules.commercial.service import QuotaExceededError, enforce_quota_limit

    existing = await jobs_service.find_existing_job(
        db, account_id=identity.account_id, idempotency_key=idempotency_key
    )
    if existing is not None:
        return _job_out(existing, dek=dek)

    try:
        await enforce_quota_limit(
            db, account_id=identity.account_id, quota_key="verified_research_runs_per_month"
        )
    except QuotaExceededError as exc:
        raise TalvrinAPIError(code=ErrorCode.RIGHTS_RESTRICTED, message=str(exc)) from exc

    try:
        job = await jobs_service.create_job(
            db,
            account_id=identity.account_id,
            principal_id=identity.principal_id,
            conversation_id=body.conversation_id,
            query=body.query,
            model=body.model,
            dek=dek,
            idempotency_key=idempotency_key,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        # research.research_job runs under FORCE ROW LEVEL SECURITY - the
        # rollback just above ends the transaction that held app.account_id
        # (SET LOCAL is transaction-scoped) exactly like a commit would, so
        # the lookup below needs it re-applied first or it fails closed
        # and raises the ORIGINAL exception instead of resolving the real
        # winner (the same mistake this file's cancel_research_job made
        # with a commit instead of a rollback - caught live there, fixed
        # here before it shipped the same way).
        await identity_service.apply_rls_context(
            db, account_id=identity.account_id, principal_id=identity.principal_id
        )
        # A concurrent duplicate request racing the exact same idempotency
        # key both pass find_existing_job (neither had committed yet) - the
        # unique index (migration 0040) rejects the loser, which re-resolves
        # by looking the winner's row up, same pattern support.py uses for
        # its own idempotency key.
        resolved = await jobs_service.find_existing_job(
            db, account_id=identity.account_id, idempotency_key=idempotency_key
        )
        if resolved is None:
            raise
        return _job_out(resolved, dek=dek)

    return _job_out(job, dek=dek)


@router.get("/research/jobs/{job_id}", response_model=ResearchJobOut)
async def get_research_job(
    job_id: uuid.UUID, db: SessionDep, identity: IdentityDep, dek: DekDep
) -> ResearchJobOut:
    job = await jobs_service.get_job(db, job_id=job_id)
    await db.commit()
    if job is None:
        raise _not_found()
    return _job_out(job, dek=dek)


@router.post("/research/jobs/{job_id}/cancel", response_model=ResearchJobOut)
async def cancel_research_job(
    job_id: uuid.UUID, db: SessionDep, identity: IdentityDep, dek: DekDep
) -> ResearchJobOut:
    """Idempotent, per jobs_service.request_cancel's own contract: a job
    that already finished is returned unchanged, with its real final
    status, never an error - a canceled browser subscription is not proof
    the server job stopped (UAT gap-analysis G15's own wording), so this
    endpoint can only ever express a request, not a guarantee.

    Deliberately does not commit and then re-fetch: research.research_job
    runs under FORCE ROW LEVEL SECURITY, and a commit ends the transaction
    holding app.account_id (SET LOCAL is transaction-scoped) - an earlier
    version of this endpoint did exactly that and its own second lookup
    then failed closed on every call, returning 404 even though the
    cancel itself had already succeeded (caught live, not by a test:
    curl showed the job really was CANCEL_REQUESTED on a follow-up GET
    from a fresh request, while this endpoint's own response claimed not
    found). request_cancel's only possible effects are the status
    transition itself - result_message_id/error_message/completed_at are
    untouched by a cancel request, only the worker's mark_* functions set
    those - so the already-fetched `job` plus the new status is the
    complete, correct response with no second query needed.
    """
    job = await jobs_service.get_job(db, job_id=job_id)
    if job is None:
        raise _not_found()
    new_status = await jobs_service.request_cancel(db, job_id=job_id)
    await db.commit()
    return _job_out(dataclasses.replace(job, status=new_status), dek=dek)
