"""research.research_job - UAT gap-analysis G15's typed job states for a
research request, processed by scripts/run_research_worker.py rather than
inline in the request thread. Raw SQL throughout, matching
research/service.py's own convention for this module (encrypted content,
no ORM model) rather than introducing a second persistence style for one
table.

State machine (ck_research_job_status, migration 0040):

    QUEUED -> RUNNING -> COMPLETED
                       -> FAILED
    QUEUED            -> CANCEL_REQUESTED -> CANCELED   (never claimed)
             RUNNING  -> CANCEL_REQUESTED -> CANCELED   (claimed, not yet committed)

CANCEL_REQUESTED is a real intermediate state, not cancellation itself -
the worker is the only thing that can safely stop in-flight work (an
AI Gateway call already issued cannot be un-issued from here), so
request_cancel() only ever sets CANCEL_REQUESTED and the worker is
responsible for noticing it and transitioning to CANCELED at a safe
checkpoint (see run_research_worker.py's own docstring for exactly where).
A job already COMPLETED/FAILED/CANCELED is left alone - cancelling is
idempotent, not an error, matching this codebase's "a failed transaction
is safely retryable" doctrine elsewhere (support.py's idempotency key).
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.uuid7 import new_uuid7
from app.modules.research import crypto

STATUS_QUEUED = "QUEUED"
STATUS_RUNNING = "RUNNING"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"
STATUS_CANCEL_REQUESTED = "CANCEL_REQUESTED"
STATUS_CANCELED = "CANCELED"

@dataclass(frozen=True)
class ResearchJob:
    id: uuid.UUID
    account_id: uuid.UUID
    principal_id: uuid.UUID
    conversation_id: uuid.UUID
    model: str | None
    status: str
    result_message_id: uuid.UUID | None
    error_message: str | None
    created_at: dt.datetime
    started_at: dt.datetime | None
    completed_at: dt.datetime | None
    _encrypted_query: bytes
    _encrypted_result: bytes | None

    def query(self, *, dek: bytes) -> str:
        return crypto.decrypt(dek, self._encrypted_query, aad=crypto.conversation_aad(
            self.conversation_id
        ))

    def result(self, *, dek: bytes) -> dict[str, Any] | None:
        if self._encrypted_result is None:
            return None
        decrypted = crypto.decrypt(
            dek, self._encrypted_result, aad=crypto.conversation_aad(self.conversation_id)
        )
        return dict(json.loads(decrypted))


_COLUMNS = (
    "id, account_id, principal_id, conversation_id, model, status, "
    "result_message_id, error_message, created_at, started_at, completed_at, "
    "encrypted_query, encrypted_result"
)


def _row_to_job(row: Any) -> ResearchJob:
    return ResearchJob(
        id=row.id,
        account_id=row.account_id,
        principal_id=row.principal_id,
        conversation_id=row.conversation_id,
        model=row.model,
        status=row.status,
        result_message_id=row.result_message_id,
        error_message=row.error_message,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        _encrypted_query=bytes(row.encrypted_query),
        _encrypted_result=bytes(row.encrypted_result) if row.encrypted_result is not None else None,
    )


async def find_existing_job(
    session: AsyncSession, *, account_id: uuid.UUID, idempotency_key: str
) -> ResearchJob | None:
    """The idempotent-retry lookup for POST /api/v1/research/jobs - a
    repeated request with the same key returns the SAME job (whatever
    state it's reached), never creates a second one. No time window
    (unlike support.ticket's 24h one): a research job's idempotency key is
    scoped to one specific request's lifecycle, not a reusable-later value,
    so staying valid forever is the right default here."""
    row = (
        await session.execute(
            text(
                f"SELECT {_COLUMNS} FROM research.research_job "
                "WHERE account_id = :aid AND idempotency_key = :key"
            ),
            {"aid": account_id, "key": idempotency_key},
        )
    ).first()
    return _row_to_job(row) if row is not None else None


async def create_job(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    principal_id: uuid.UUID,
    conversation_id: uuid.UUID,
    query: str,
    model: str | None,
    dek: bytes,
    idempotency_key: str | None,
) -> ResearchJob:
    """Does not commit - callers commit together with whatever audit/quota
    bookkeeping belongs in the same transaction (get_session's own
    contract: "callers commit explicitly")."""
    job_id = new_uuid7()
    encrypted_query = crypto.encrypt(
        dek, query, aad=crypto.conversation_aad(conversation_id)
    )
    row = (
        await session.execute(
            text(
                "INSERT INTO research.research_job "
                "(id, account_id, principal_id, conversation_id, idempotency_key, "
                " encrypted_query, model, status) "
                "VALUES (:id, :aid, :pid, :cid, :key, :q, :model, :status) "
                f"RETURNING {_COLUMNS}"
            ),
            {
                "id": job_id,
                "aid": account_id,
                "pid": principal_id,
                "cid": conversation_id,
                "key": idempotency_key,
                "q": encrypted_query,
                "model": model,
                "status": STATUS_QUEUED,
            },
        )
    ).one()
    return _row_to_job(row)


async def claim_next_queued_job(session: AsyncSession) -> ResearchJob | None:
    """Claims one QUEUED job for the account already set in this session's
    RLS context (run_research_worker.py applies that context per account
    before calling this, the same per-account loop shape
    run_monitoring_worker.py already uses) and transitions it straight to
    RUNNING in the same statement - no separate read-then-write window for
    two workers to race. FOR UPDATE SKIP LOCKED matches
    calculation/pipeline/job_queue.py's own claim discipline exactly: a
    second worker scanning concurrently skips a row this one already holds
    rather than blocking on it.

    Also resolves a job cancelled before any worker ever claimed it
    (QUEUED -> CANCEL_REQUESTED with started_at still NULL): this function
    is the only place that discovers unclaimed work at all, so without
    this second branch such a job would sit in CANCEL_REQUESTED forever -
    no worker call chain ever looks at it again, since
    is_cancel_requested() is only ever checked from inside a
    _process_one_job call that a claim already started. A RUNNING job that
    becomes CANCEL_REQUESTED mid-flight is a different case entirely and
    must NOT be claimed here: it already has started_at set, so the
    `started_at IS NULL` guard leaves it alone for the worker already
    holding it (via its own is_cancel_requested re-check) to resolve.
    """
    row = (
        await session.execute(
            text(
                f"""
                UPDATE research.research_job SET status = :running, started_at = now()
                WHERE id = (
                    SELECT id FROM research.research_job
                    WHERE status = :queued
                    ORDER BY created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING {_COLUMNS}
                """
            ),
            {"running": STATUS_RUNNING, "queued": STATUS_QUEUED},
        )
    ).first()
    if row is not None:
        return _row_to_job(row)

    row = (
        await session.execute(
            text(
                f"""
                UPDATE research.research_job SET status = :canceled, completed_at = now()
                WHERE id = (
                    SELECT id FROM research.research_job
                    WHERE status = :cancel_requested AND started_at IS NULL
                    ORDER BY created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING {_COLUMNS}
                """
            ),
            {"canceled": STATUS_CANCELED, "cancel_requested": STATUS_CANCEL_REQUESTED},
        )
    ).first()
    return _row_to_job(row) if row is not None else None


async def is_cancel_requested(session: AsyncSession, *, job_id: uuid.UUID) -> bool:
    """A fresh read, not a check against an in-memory ResearchJob - a
    cancel can arrive at any point while the worker is mid-composition, so
    the only safe check is one that hits the database again right before
    the point of no return (run_research_worker.py calls this immediately
    before committing a composed answer)."""
    status = (
        await session.execute(
            text("SELECT status FROM research.research_job WHERE id = :id"), {"id": job_id}
        )
    ).scalar_one_or_none()
    return status == STATUS_CANCEL_REQUESTED


async def request_cancel(session: AsyncSession, *, job_id: uuid.UUID) -> str:
    """Idempotent: returns the job's status AFTER this call, whatever that
    is - a job already terminal is simply left alone and its existing
    terminal status is returned, never an error. Only QUEUED/RUNNING
    actually transition."""
    row = (
        await session.execute(
            text(
                "UPDATE research.research_job SET status = :cr "
                "WHERE id = :id AND status IN (:queued, :running) "
                "RETURNING status"
            ),
            {
                "cr": STATUS_CANCEL_REQUESTED,
                "id": job_id,
                "queued": STATUS_QUEUED,
                "running": STATUS_RUNNING,
            },
        )
    ).first()
    if row is not None:
        return str(row.status)
    current = (
        await session.execute(
            text("SELECT status FROM research.research_job WHERE id = :id"), {"id": job_id}
        )
    ).scalar_one()
    return str(current)


async def mark_completed(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    conversation_id: uuid.UUID,
    result_message_id: uuid.UUID,
    result_payload: dict[str, Any],
    dek: bytes,
) -> None:
    encrypted_result = crypto.encrypt(
        dek, json.dumps(result_payload), aad=crypto.conversation_aad(conversation_id)
    )
    await session.execute(
        text(
            "UPDATE research.research_job "
            "SET status = :status, result_message_id = :mid, encrypted_result = :result, "
            "    completed_at = now() "
            "WHERE id = :id"
        ),
        {
            "status": STATUS_COMPLETED,
            "mid": result_message_id,
            "result": encrypted_result,
            "id": job_id,
        },
    )


async def mark_failed(session: AsyncSession, *, job_id: uuid.UUID, error_message: str) -> None:
    """error_message must already be safe to show a user (no stack traces,
    no internal identifiers) - matching support.py's own "no database
    table names, internal stack traces or secrets appear" discipline."""
    await session.execute(
        text(
            "UPDATE research.research_job "
            "SET status = :status, error_message = :err, completed_at = now() "
            "WHERE id = :id"
        ),
        {"status": STATUS_FAILED, "err": error_message[:1000], "id": job_id},
    )


async def mark_canceled(session: AsyncSession, *, job_id: uuid.UUID) -> None:
    await session.execute(
        text(
            "UPDATE research.research_job "
            "SET status = :status, completed_at = now() "
            "WHERE id = :id"
        ),
        {"status": STATUS_CANCELED, "id": job_id},
    )


async def get_job(session: AsyncSession, *, job_id: uuid.UUID) -> ResearchJob | None:
    row = (
        await session.execute(
            text(f"SELECT {_COLUMNS} FROM research.research_job WHERE id = :id"),
            {"id": job_id},
        )
    ).first()
    return _row_to_job(row) if row is not None else None


__all__ = [
    "STATUS_CANCEL_REQUESTED",
    "STATUS_CANCELED",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_QUEUED",
    "STATUS_RUNNING",
    "ResearchJob",
    "claim_next_queued_job",
    "create_job",
    "find_existing_job",
    "get_job",
    "is_cancel_requested",
    "mark_canceled",
    "mark_completed",
    "mark_failed",
    "request_cancel",
]
