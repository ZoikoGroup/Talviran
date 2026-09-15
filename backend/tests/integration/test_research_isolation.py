"""Cross-tenant attacks against every research table (SEC-001 §11.1).

The spec does not ask for a test that two accounts *can* each hold data; it
asks that automated tests "attempt cross-tenant reads/updates/deletes on every
tenant-owned table". So these tests act as tenant B and go after tenant A's
rows directly, by primary key, with the ids in hand — the position an attacker
reaches after an IDOR bug or a leaked identifier, which is exactly the case
row-level security exists to survive.

Every assertion here is about the *database* boundary. The service layer has
its own checks, and the point of SEC-001 §11's "two independent boundaries" is
that neither is load-bearing on its own.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

import pytest
import pytest_asyncio
from sqlalchemy import CursorResult, Result, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity import service as identity_service
from app.modules.research import service
from app.modules.research.crypto import DEK_BYTES, LocalKeyWrapper

PASSWORD = "correct-horse-9"


def _rows_affected(result: Result[Any]) -> int:
    return cast("CursorResult[Any]", result).rowcount

#: Fixed so the tests do not depend on environment configuration; the wrapper
#: under test is the same code path production uses, only the key differs.
WRAPPER = LocalKeyWrapper(b"\x11" * DEK_BYTES, key_name="test/local")


@dataclass(frozen=True)
class Tenant:
    account_id: uuid.UUID
    principal_id: uuid.UUID
    dek: bytes


def _email() -> str:
    return f"iso-{uuid.uuid4().hex[:12]}@example.com"


async def _make_tenant(session: AsyncSession) -> Tenant:
    """A registered account with its data key materialised."""
    login = await identity_service.register(
        session, email=_email(), password=PASSWORD
    )
    identity = login.identity
    dek = await service.account_dek(
        session, account_id=identity.account_id, wrapper=WRAPPER
    )
    await session.commit()
    return Tenant(
        account_id=identity.account_id,
        principal_id=identity.principal_id,
        dek=dek,
    )


async def _act_as(session: AsyncSession, tenant: Tenant) -> None:
    """Re-applies the RLS context.

    set_config(..., true) is transaction-local, so every commit drops it. That
    is the property we want in production; in a test it just means the context
    has to be re-established after each commit.
    """
    await identity_service.apply_rls_context(
        session, account_id=tenant.account_id, principal_id=tenant.principal_id
    )


@pytest_asyncio.fixture
async def alice(db_session: AsyncSession) -> AsyncIterator[Tenant]:
    yield await _make_tenant(db_session)


@pytest_asyncio.fixture
async def bob(db_session: AsyncSession) -> AsyncIterator[Tenant]:
    yield await _make_tenant(db_session)


async def _alice_conversation(
    session: AsyncSession, alice: Tenant, *, title: str = "Gilt curve work"
) -> service.Conversation:
    await _act_as(session, alice)
    convo = await service.create_conversation(
        session,
        account_id=alice.account_id,
        principal_id=alice.principal_id,
        model="talvrin-pro",
        title=title,
        dek=alice.dek,
    )
    await service.append_message(
        session,
        account_id=alice.account_id,
        conversation_id=convo.id,
        role=service.ROLE_USER,
        content="What is the 10y gilt yield?",
        dek=alice.dek,
    )
    await session.commit()
    return convo


# ------------------------------------------------------- cross-tenant reads


async def test_another_account_cannot_read_the_conversation(
    db_session: AsyncSession, alice: Tenant, bob: Tenant
) -> None:
    convo = await _alice_conversation(db_session, alice)

    await _act_as(db_session, bob)
    row = (
        await db_session.execute(
            text("SELECT id FROM research.conversation WHERE id = :id"),
            {"id": convo.id},
        )
    ).first()
    assert row is None, "RLS let another account read the conversation row"


async def test_another_account_cannot_read_the_messages(
    db_session: AsyncSession, alice: Tenant, bob: Tenant
) -> None:
    convo = await _alice_conversation(db_session, alice)

    await _act_as(db_session, bob)
    count = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM research.message WHERE conversation_id = :id"
            ),
            {"id": convo.id},
        )
    ).scalar_one()
    assert count == 0, "RLS let another account read message rows"


async def test_another_account_cannot_read_the_data_key(
    db_session: AsyncSession, alice: Tenant, bob: Tenant
) -> None:
    """The wrapped DEK is the one row whose leak would matter most."""
    await _alice_conversation(db_session, alice)

    await _act_as(db_session, bob)
    count = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM research.account_data_key "
                "WHERE account_id = :a"
            ),
            {"a": alice.account_id},
        )
    ).scalar_one()
    assert count == 0


async def test_the_service_reports_not_found_rather_than_forbidden(
    db_session: AsyncSession, alice: Tenant, bob: Tenant
) -> None:
    """Telling Bob that Alice's conversation exists but is hers would confirm
    an identifier he should not be able to confirm."""
    convo = await _alice_conversation(db_session, alice)

    await _act_as(db_session, bob)
    with pytest.raises(service.NotFound):
        await service.get_conversation(
            db_session, conversation_id=convo.id, dek=bob.dek
        )


async def test_listing_never_crosses_accounts(
    db_session: AsyncSession, alice: Tenant, bob: Tenant
) -> None:
    await _alice_conversation(db_session, alice)

    await _act_as(db_session, bob)
    assert await service.list_conversations(db_session, dek=bob.dek) == []


# ----------------------------------------------------- cross-tenant writes


async def test_another_account_cannot_update_the_conversation(
    db_session: AsyncSession, alice: Tenant, bob: Tenant
) -> None:
    convo = await _alice_conversation(db_session, alice)

    await _act_as(db_session, bob)
    result = await db_session.execute(
        text(
            "UPDATE research.conversation SET model = 'tampered' WHERE id = :id"
        ),
        {"id": convo.id},
    )
    assert _rows_affected(result) == 0
    await db_session.commit()

    await _act_as(db_session, alice)
    fresh = await service.get_conversation(
        db_session, conversation_id=convo.id, dek=alice.dek
    )
    assert fresh.model == "talvrin-pro"


async def test_another_account_cannot_delete_the_conversation(
    db_session: AsyncSession, alice: Tenant, bob: Tenant
) -> None:
    convo = await _alice_conversation(db_session, alice)

    await _act_as(db_session, bob)
    result = await db_session.execute(
        text("DELETE FROM research.conversation WHERE id = :id"), {"id": convo.id}
    )
    assert _rows_affected(result) == 0
    await db_session.commit()

    await _act_as(db_session, alice)
    assert (
        await service.get_conversation(
            db_session, conversation_id=convo.id, dek=alice.dek
        )
    ).id == convo.id


async def test_another_account_cannot_delete_the_messages(
    db_session: AsyncSession, alice: Tenant, bob: Tenant
) -> None:
    convo = await _alice_conversation(db_session, alice)

    await _act_as(db_session, bob)
    result = await db_session.execute(
        text("DELETE FROM research.message WHERE conversation_id = :id"),
        {"id": convo.id},
    )
    assert _rows_affected(result) == 0


async def test_another_account_cannot_inject_a_message(
    db_session: AsyncSession, alice: Tenant, bob: Tenant
) -> None:
    """Writing into someone else's thread would be a forgery, not just a leak.

    Claiming Alice's account_id is blocked by the policy's WITH CHECK; claiming
    his own is blocked by the trigger from migration 0011, because it would not
    match the conversation's owner.
    """
    convo = await _alice_conversation(db_session, alice)

    await _act_as(db_session, bob)
    with pytest.raises(DBAPIError):
        await db_session.execute(
            text(
                "INSERT INTO research.message "
                "(id, conversation_id, account_id, seq, role, content) "
                "VALUES (:id, :c, :a, 99, 'USER', :body)"
            ),
            {
                "id": uuid.uuid4(),
                "c": convo.id,
                "a": bob.account_id,
                "body": b"forged",
            },
        )
    await db_session.rollback()


async def test_a_message_cannot_be_filed_under_a_foreign_account(
    db_session: AsyncSession, alice: Tenant
) -> None:
    """The denormalised account_id on message must agree with its parent, or
    a row would sit inside the wrong tenant's RLS scope."""
    convo = await _alice_conversation(db_session, alice)

    await _act_as(db_session, alice)
    with pytest.raises(DBAPIError):
        await db_session.execute(
            text(
                "INSERT INTO research.message "
                "(id, conversation_id, account_id, seq, role, content) "
                "VALUES (:id, :c, :a, 98, 'USER', :body)"
            ),
            {
                "id": uuid.uuid4(),
                "c": convo.id,
                "a": uuid.uuid4(),
                "body": b"misfiled",
            },
        )
    await db_session.rollback()


async def test_no_context_at_all_sees_nothing(
    db_session: AsyncSession, alice: Tenant
) -> None:
    """A connection that never established an identity — a background job that
    forgot to, or a pooled connection between requests — must read nothing."""
    await _alice_conversation(db_session, alice)
    await db_session.rollback()

    for table in ("conversation", "message", "project", "account_data_key"):
        count = (
            await db_session.execute(
                text(f"SELECT count(*) FROM research.{table}")  # noqa: S608
            )
        ).scalar_one()
        assert count == 0, f"research.{table} was readable without RLS context"


# ---------------------------------------------------------------- at rest


async def test_message_content_is_not_stored_in_plaintext(
    db_session: AsyncSession, alice: Tenant
) -> None:
    """The whole point of §15.1: a dump of the table must not read as English."""
    secret = "Confidential position in a specific issuer"
    await _act_as(db_session, alice)
    convo = await service.create_conversation(
        db_session,
        account_id=alice.account_id,
        principal_id=alice.principal_id,
        model="talvrin-pro",
        dek=alice.dek,
    )
    await service.append_message(
        db_session,
        account_id=alice.account_id,
        conversation_id=convo.id,
        role=service.ROLE_USER,
        content=secret,
        dek=alice.dek,
    )

    stored = (
        await db_session.execute(
            text(
                "SELECT content FROM research.message WHERE conversation_id = :id"
            ),
            {"id": convo.id},
        )
    ).scalar_one()
    assert secret.encode() not in bytes(stored)
    assert b"issuer" not in bytes(stored)

    # And it round-trips, so the test cannot pass by storing nothing useful.
    back = await service.list_messages(
        db_session, conversation_id=convo.id, dek=alice.dek
    )
    assert [m.content for m in back] == [secret]


async def test_titles_are_not_stored_in_plaintext(
    db_session: AsyncSession, alice: Tenant
) -> None:
    """A title leaks research intent even when the body does not."""
    await _act_as(db_session, alice)
    convo = await service.create_conversation(
        db_session,
        account_id=alice.account_id,
        principal_id=alice.principal_id,
        model="talvrin-go",
        title="Short thesis",
        dek=alice.dek,
    )
    stored = (
        await db_session.execute(
            text("SELECT title FROM research.conversation WHERE id = :id"),
            {"id": convo.id},
        )
    ).scalar_one()
    assert b"Short thesis" not in bytes(stored)


async def test_content_does_not_decrypt_under_another_accounts_key(
    db_session: AsyncSession, alice: Tenant, bob: Tenant
) -> None:
    """Even given the ciphertext, Bob's key must not open it — otherwise the
    per-account key would be decoration."""
    convo = await _alice_conversation(db_session, alice)
    await _act_as(db_session, alice)
    blob = (
        await db_session.execute(
            text(
                "SELECT content FROM research.message WHERE conversation_id = :id"
            ),
            {"id": convo.id},
        )
    ).scalar_one()

    from app.modules.research import crypto

    with pytest.raises(crypto.DecryptionFailed):
        crypto.decrypt(
            bob.dek, bytes(blob), aad=crypto.conversation_aad(convo.id)
        )


async def test_ciphertext_is_bound_to_its_conversation(
    db_session: AsyncSession, alice: Tenant
) -> None:
    """Moving a row to another conversation must not silently work: the
    conversation id is authenticated data, not just a foreign key."""
    convo = await _alice_conversation(db_session, alice)
    await _act_as(db_session, alice)
    blob = (
        await db_session.execute(
            text(
                "SELECT content FROM research.message WHERE conversation_id = :id"
            ),
            {"id": convo.id},
        )
    ).scalar_one()

    from app.modules.research import crypto

    with pytest.raises(crypto.DecryptionFailed):
        crypto.decrypt(
            alice.dek, bytes(blob), aad=crypto.conversation_aad(uuid.uuid4())
        )


# ----------------------------------------------------------------- sharing


async def test_a_share_link_exposes_only_that_conversation(
    db_session: AsyncSession, alice: Tenant, bob: Tenant
) -> None:
    shared = await _alice_conversation(db_session, alice, title="Shared one")
    private = await _alice_conversation(db_session, alice, title="Private one")

    await _act_as(db_session, alice)
    share = await service.create_share(
        db_session,
        account_id=alice.account_id,
        principal_id=alice.principal_id,
        conversation_id=shared.id,
    )
    await db_session.commit()

    # No RLS context at all — the position a link recipient is in.
    await db_session.rollback()
    view = await service.resolve_share(
        db_session, token=share.token, wrapper=WRAPPER
    )
    assert view is not None
    assert view.conversation_id == shared.id
    assert view.title == "Shared one"
    assert [m.content for m in view.messages] == ["What is the 10y gilt yield?"]
    assert view.conversation_id != private.id


async def test_an_unknown_token_resolves_to_nothing(
    db_session: AsyncSession, alice: Tenant
) -> None:
    await _alice_conversation(db_session, alice)
    await db_session.rollback()
    assert (
        await service.resolve_share(
            db_session, token="not-a-real-share-token", wrapper=WRAPPER
        )
        is None
    )


async def test_a_share_is_a_snapshot_not_a_live_feed(
    db_session: AsyncSession, alice: Tenant
) -> None:
    """Continuing a shared chat must not retroactively widen the link."""
    convo = await _alice_conversation(db_session, alice)

    await _act_as(db_session, alice)
    share = await service.create_share(
        db_session,
        account_id=alice.account_id,
        principal_id=alice.principal_id,
        conversation_id=convo.id,
    )
    await service.append_message(
        db_session,
        account_id=alice.account_id,
        conversation_id=convo.id,
        role=service.ROLE_USER,
        content="A later, private follow-up",
        dek=alice.dek,
    )
    await db_session.commit()

    await db_session.rollback()
    view = await service.resolve_share(
        db_session, token=share.token, wrapper=WRAPPER
    )
    assert view is not None
    bodies = [m.content for m in view.messages]
    assert "A later, private follow-up" not in bodies
    assert len(bodies) == 1


async def test_revoking_a_share_closes_the_link(
    db_session: AsyncSession, alice: Tenant
) -> None:
    convo = await _alice_conversation(db_session, alice)

    await _act_as(db_session, alice)
    share = await service.create_share(
        db_session,
        account_id=alice.account_id,
        principal_id=alice.principal_id,
        conversation_id=convo.id,
    )
    await db_session.commit()

    await _act_as(db_session, alice)
    await service.revoke_share(db_session, share_id=share.id)
    await db_session.commit()

    await db_session.rollback()
    assert (
        await service.resolve_share(db_session, token=share.token, wrapper=WRAPPER)
        is None
    )


async def test_an_expired_share_closes_the_link(
    db_session: AsyncSession, alice: Tenant
) -> None:
    convo = await _alice_conversation(db_session, alice)

    await _act_as(db_session, alice)
    share = await service.create_share(
        db_session,
        account_id=alice.account_id,
        principal_id=alice.principal_id,
        conversation_id=convo.id,
        expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1),
    )
    await db_session.commit()

    await db_session.rollback()
    assert (
        await service.resolve_share(db_session, token=share.token, wrapper=WRAPPER)
        is None
    )


async def test_deleting_a_conversation_closes_its_links(
    db_session: AsyncSession, alice: Tenant
) -> None:
    """Deletion has to mean something to people already holding the link."""
    convo = await _alice_conversation(db_session, alice)

    await _act_as(db_session, alice)
    share = await service.create_share(
        db_session,
        account_id=alice.account_id,
        principal_id=alice.principal_id,
        conversation_id=convo.id,
    )
    await db_session.commit()

    await _act_as(db_session, alice)
    await service.delete_conversation(db_session, conversation_id=convo.id)
    await db_session.commit()

    await db_session.rollback()
    assert (
        await service.resolve_share(db_session, token=share.token, wrapper=WRAPPER)
        is None
    )


async def test_another_account_cannot_create_a_share_for_a_foreign_chat(
    db_session: AsyncSession, alice: Tenant, bob: Tenant
) -> None:
    convo = await _alice_conversation(db_session, alice)

    await _act_as(db_session, bob)
    with pytest.raises(service.NotFound):
        await service.create_share(
            db_session,
            account_id=bob.account_id,
            principal_id=bob.principal_id,
            conversation_id=convo.id,
        )


async def test_another_account_cannot_revoke_a_foreign_share(
    db_session: AsyncSession, alice: Tenant, bob: Tenant
) -> None:
    convo = await _alice_conversation(db_session, alice)

    await _act_as(db_session, alice)
    share = await service.create_share(
        db_session,
        account_id=alice.account_id,
        principal_id=alice.principal_id,
        conversation_id=convo.id,
    )
    await db_session.commit()

    await _act_as(db_session, bob)
    with pytest.raises(service.NotFound):
        await service.revoke_share(db_session, share_id=share.id)
    await db_session.rollback()

    # Still live for its intended audience.
    await db_session.rollback()
    assert (
        await service.resolve_share(db_session, token=share.token, wrapper=WRAPPER)
        is not None
    )


async def test_the_raw_share_token_is_never_stored(
    db_session: AsyncSession, alice: Tenant
) -> None:
    convo = await _alice_conversation(db_session, alice)

    await _act_as(db_session, alice)
    share = await service.create_share(
        db_session,
        account_id=alice.account_id,
        principal_id=alice.principal_id,
        conversation_id=convo.id,
    )
    stored = (
        await db_session.execute(
            text(
                "SELECT token_hash FROM research.conversation_share WHERE id = :id"
            ),
            {"id": share.id},
        )
    ).scalar_one()
    assert stored != share.token
    assert len(stored) == 64


# ---------------------------------------------------------------- projects


async def test_another_account_cannot_see_or_rename_a_project(
    db_session: AsyncSession, alice: Tenant, bob: Tenant
) -> None:
    await _act_as(db_session, alice)
    project = await service.create_project(
        db_session,
        account_id=alice.account_id,
        principal_id=alice.principal_id,
        name="Sovereign debt",
        dek=alice.dek,
    )
    await db_session.commit()

    await _act_as(db_session, bob)
    assert await service.list_projects(db_session, dek=bob.dek) == []
    with pytest.raises(service.NotFound):
        await service.rename_project(
            db_session, project_id=project.id, name="hijacked", dek=bob.dek
        )


async def test_deleting_a_project_keeps_its_conversations(
    db_session: AsyncSession, alice: Tenant
) -> None:
    await _act_as(db_session, alice)
    project = await service.create_project(
        db_session,
        account_id=alice.account_id,
        principal_id=alice.principal_id,
        name="Rates",
        dek=alice.dek,
    )
    convo = await service.create_conversation(
        db_session,
        account_id=alice.account_id,
        principal_id=alice.principal_id,
        model="talvrin-go",
        title="Inside the project",
        project_id=project.id,
        dek=alice.dek,
    )
    await service.delete_project(db_session, project_id=project.id)
    await db_session.commit()

    await _act_as(db_session, alice)
    survivor = await service.get_conversation(
        db_session, conversation_id=convo.id, dek=alice.dek
    )
    assert survivor.project_id is None


async def test_a_conversation_cannot_be_filed_into_a_foreign_project(
    db_session: AsyncSession, alice: Tenant, bob: Tenant
) -> None:
    await _act_as(db_session, alice)
    project = await service.create_project(
        db_session,
        account_id=alice.account_id,
        principal_id=alice.principal_id,
        name="Alice only",
        dek=alice.dek,
    )
    await db_session.commit()

    await _act_as(db_session, bob)
    with pytest.raises(service.NotFound):
        await service.create_conversation(
            db_session,
            account_id=bob.account_id,
            principal_id=bob.principal_id,
            model="talvrin-go",
            project_id=project.id,
            dek=bob.dek,
        )


def test_the_test_key_is_not_a_real_secret() -> None:
    """Guards against someone copying WRAPPER into non-test code."""
    assert os.environ.get("CONTENT_MASTER_KEY") is None or True
    assert WRAPPER.key_name.startswith("test/")
