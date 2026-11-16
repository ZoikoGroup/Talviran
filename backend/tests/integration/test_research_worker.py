"""scripts/run_research_worker.py (UAT gap-analysis G15): the state-machine
guarantees that matter are "no duplicate work, wrong-thread results, or
false completion" - proven here the same way G11's monitoring crash/
restart test proves them for the monitoring worker: by actually raising
inside the worker's own call chain and checking what's left in the
database afterward, not by reading the code and trusting it.

"should I buy this gilt?" is used throughout as the query: it resolves to
the advice-redirect reply (NEUTRAL_EDUCATION, no evidence bundle), which
needs only _seed_pdp_prerequisites and makes no AI Gateway call at all
(research.py's own _try_ai_composed_text returns early when
evidence_bundle_id is None) - the fastest, most deterministic path through
compose_and_persist_research_answer, since these tests are about job
state transitions, not answer content.
"""

import datetime as dt
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import scripts.run_research_worker as worker_module
from app.modules.identity import service as identity_service
from app.modules.policy.models import ActivationRecord, CapabilityStatus
from app.modules.research import jobs_service
from app.modules.research import service as research_service
from app.modules.research.crypto import DEK_BYTES, LocalKeyWrapper

_PASSWORD = "correct-horse-9"
_QUERY = "should I buy this gilt?"
_WRAPPER = LocalKeyWrapper(b"\x44" * DEK_BYTES, key_name="test/research-worker")


def _email() -> str:
    return f"research-worker-{uuid.uuid4().hex[:12]}@example.com"


async def _seed_pdp_prerequisites(session: AsyncSession) -> None:
    session.add(
        CapabilityStatus(
            capability_code="research.answer", jurisdiction_code=None, status="AVAILABLE"
        )
    )
    session.add(
        ActivationRecord(
            jurisdiction_code="GB", operating_entity="Test Entity", status="ACTIVE",
            effective_from=dt.datetime.now(dt.UTC) - dt.timedelta(days=1), effective_to=None,
        )
    )
    await session.flush()


async def _setup(
    session: AsyncSession, http: httpx.AsyncClient
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, bytes]:
    """Returns (account_id, principal_id, conversation_id, dek)."""
    login = await identity_service.register(
        session, email=_email(), password=_PASSWORD, http=http
    )
    await session.commit()
    account_id, principal_id = login.identity.account_id, login.identity.principal_id
    await identity_service.apply_rls_context(
        session, account_id=account_id, principal_id=principal_id
    )
    await _seed_pdp_prerequisites(session)
    dek = await research_service.account_dek(session, account_id=account_id, wrapper=_WRAPPER)
    conversation = await research_service.create_conversation(
        session, account_id=account_id, principal_id=principal_id, model="talvrin-go", dek=dek
    )
    await session.commit()
    await identity_service.apply_rls_context(
        session, account_id=account_id, principal_id=principal_id
    )
    return account_id, principal_id, conversation.id, dek


async def test_a_queued_job_is_claimed_composed_and_completed(
    db_session: AsyncSession, supabase_http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker_module, "get_key_wrapper", lambda: _WRAPPER)
    account_id, principal_id, conversation_id, dek = await _setup(db_session, supabase_http)

    job = await jobs_service.create_job(
        db_session, account_id=account_id, principal_id=principal_id,
        conversation_id=conversation_id, query=_QUERY, model=None, dek=dek,
        idempotency_key=f"test-{uuid.uuid4()}",
    )
    await db_session.commit()
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    processed = await worker_module._sweep_account(
        db_session, account_id=account_id, principal_id=principal_id
    )
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    assert processed == 1
    finished = await jobs_service.get_job(db_session, job_id=job.id)
    assert finished is not None
    assert finished.status == jobs_service.STATUS_COMPLETED
    assert finished.result_message_id is not None
    result = finished.result(dek=dek)
    assert result is not None
    assert "can't tell you whether to buy" in result["text"]

    messages = await research_service.list_messages(
        db_session, conversation_id=conversation_id, dek=dek
    )
    assert [m.role for m in messages] == ["USER", "ASSISTANT"]
    assert messages[0].content == _QUERY


async def test_canceling_before_the_worker_ever_claims_it_leaves_no_message(
    db_session: AsyncSession, supabase_http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker_module, "get_key_wrapper", lambda: _WRAPPER)
    account_id, principal_id, conversation_id, dek = await _setup(db_session, supabase_http)

    job = await jobs_service.create_job(
        db_session, account_id=account_id, principal_id=principal_id,
        conversation_id=conversation_id, query=_QUERY, model=None, dek=dek,
        idempotency_key=f"test-{uuid.uuid4()}",
    )
    await db_session.commit()
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )
    status_after_cancel = await jobs_service.request_cancel(db_session, job_id=job.id)
    await db_session.commit()
    assert status_after_cancel == jobs_service.STATUS_CANCEL_REQUESTED
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    await worker_module._sweep_account(
        db_session, account_id=account_id, principal_id=principal_id
    )
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    finished = await jobs_service.get_job(db_session, job_id=job.id)
    assert finished is not None
    assert finished.status == jobs_service.STATUS_CANCELED
    assert finished.result_message_id is None

    messages = await research_service.list_messages(
        db_session, conversation_id=conversation_id, dek=dek
    )
    assert messages == []


async def test_a_late_cancel_rolls_back_the_whole_composed_attempt(
    db_session: AsyncSession, supabase_http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cancel request arrives AFTER compose_and_persist_research_answer
    has already flushed the user's message and the composed reply, but
    BEFORE the worker's own commit - jobs_service.is_cancel_requested is
    called twice per job (once before composing, once right after); the
    first call must see no cancellation yet, the second must see one that
    arrived in between, simulating the real race without needing two
    concurrent processes."""
    monkeypatch.setattr(worker_module, "get_key_wrapper", lambda: _WRAPPER)
    account_id, principal_id, conversation_id, dek = await _setup(db_session, supabase_http)

    job = await jobs_service.create_job(
        db_session, account_id=account_id, principal_id=principal_id,
        conversation_id=conversation_id, query=_QUERY, model=None, dek=dek,
        idempotency_key=f"test-{uuid.uuid4()}",
    )
    await db_session.commit()
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    real_is_cancel_requested = jobs_service.is_cancel_requested
    call_count = {"n": 0}

    async def _flaky_is_cancel_requested(session: AsyncSession, *, job_id: uuid.UUID) -> bool:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return False  # not yet cancelled - composition proceeds
        return True  # cancel "arrived" while composing

    monkeypatch.setattr(jobs_service, "is_cancel_requested", _flaky_is_cancel_requested)
    try:
        await worker_module._sweep_account(
            db_session, account_id=account_id, principal_id=principal_id
        )
    finally:
        monkeypatch.setattr(jobs_service, "is_cancel_requested", real_is_cancel_requested)
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    assert call_count["n"] == 2
    finished = await jobs_service.get_job(db_session, job_id=job.id)
    assert finished is not None
    assert finished.status == jobs_service.STATUS_CANCELED
    assert finished.result_message_id is None

    # The real guarantee: neither the user's own message nor the composed
    # reply survives - a late cancel must never leave a half-visible answer.
    messages = await research_service.list_messages(
        db_session, conversation_id=conversation_id, dek=dek
    )
    assert messages == []


async def test_a_composition_crash_marks_the_job_failed_with_a_safe_error(
    db_session: AsyncSession, supabase_http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker_module, "get_key_wrapper", lambda: _WRAPPER)
    account_id, principal_id, conversation_id, dek = await _setup(db_session, supabase_http)

    job = await jobs_service.create_job(
        db_session, account_id=account_id, principal_id=principal_id,
        conversation_id=conversation_id, query=_QUERY, model=None, dek=dek,
        idempotency_key=f"test-{uuid.uuid4()}",
    )
    await db_session.commit()
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    async def _boom(*args: object, **kwargs: object) -> object:
        raise RuntimeError(
            "simulated evidence-service outage, with an internal detail: /secret/path"
        )

    monkeypatch.setattr(worker_module, "compose_and_persist_research_answer", _boom)

    await worker_module._sweep_account(
        db_session, account_id=account_id, principal_id=principal_id
    )
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    finished = await jobs_service.get_job(db_session, job_id=job.id)
    assert finished is not None
    assert finished.status == jobs_service.STATUS_FAILED
    assert finished.error_message is not None
    assert "/secret/path" not in finished.error_message
    assert "RuntimeError" in finished.error_message

    messages = await research_service.list_messages(
        db_session, conversation_id=conversation_id, dek=dek
    )
    assert messages == []


async def test_repeat_creation_with_the_same_idempotency_key_returns_the_same_job(
    db_session: AsyncSession, supabase_http: httpx.AsyncClient
) -> None:
    account_id, principal_id, conversation_id, dek = await _setup(db_session, supabase_http)
    key = f"test-{uuid.uuid4()}"

    first = await jobs_service.create_job(
        db_session, account_id=account_id, principal_id=principal_id,
        conversation_id=conversation_id, query=_QUERY, model=None, dek=dek,
        idempotency_key=key,
    )
    await db_session.commit()
    # research.research_job runs under FORCE ROW LEVEL SECURITY - that
    # commit ended the transaction holding app.account_id (SET LOCAL is
    # transaction-scoped), so the lookup below needs it re-applied first.
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    existing = await jobs_service.find_existing_job(
        db_session, account_id=account_id, idempotency_key=key
    )
    assert existing is not None
    assert existing.id == first.id


async def test_two_jobs_in_one_sweep_are_both_processed_exactly_once(
    db_session: AsyncSession, supabase_http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker_module, "get_key_wrapper", lambda: _WRAPPER)
    account_id, principal_id, conversation_id, dek = await _setup(db_session, supabase_http)

    job_a = await jobs_service.create_job(
        db_session, account_id=account_id, principal_id=principal_id,
        conversation_id=conversation_id, query=_QUERY, model=None, dek=dek,
        idempotency_key=f"test-a-{uuid.uuid4()}",
    )
    job_b = await jobs_service.create_job(
        db_session, account_id=account_id, principal_id=principal_id,
        conversation_id=conversation_id, query=_QUERY, model=None, dek=dek,
        idempotency_key=f"test-b-{uuid.uuid4()}",
    )
    await db_session.commit()
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    processed = await worker_module._sweep_account(
        db_session, account_id=account_id, principal_id=principal_id
    )
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    assert processed == 2
    for job in (job_a, job_b):
        finished = await jobs_service.get_job(db_session, job_id=job.id)
        assert finished is not None
        assert finished.status == jobs_service.STATUS_COMPLETED

    messages = await research_service.list_messages(
        db_session, conversation_id=conversation_id, dek=dek
    )
    assert len(messages) == 4  # 2 USER + 2 ASSISTANT, one pair per job
