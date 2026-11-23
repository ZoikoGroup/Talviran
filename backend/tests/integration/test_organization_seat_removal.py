"""G16: seat removal had no test confirming the removed member's access is
actually revoked - only that it disappears from the member list. Exercises
`app.modules.api.v1.organization.remove_member` end-to-end against a real
migrated Postgres (not mocked), because the removal path's real behaviour
depends on how RLS on identity.principal and identity.session interact -
something a mocked session can't surface at all, and which turns out to
matter: see the finding documented at the end of the test below.
"""

import datetime as dt
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.core.uuid7 import new_uuid7
from app.modules.api.v1.organization import get_organization, remove_member
from app.modules.identity import service as identity_service
from app.modules.identity import tokens as identity_tokens
from app.modules.identity.models import Account, Principal
from app.modules.identity.service import Identity


async def _insert_member_session(
    db: AsyncSession, *, account_id: uuid.UUID, member_id: uuid.UUID, raw_token: str
) -> None:
    """Inserts a live session row the way a real login actually would:
    scoped to the member's OWN RLS context. identity.session's RLS policy
    (migration 0002) checks `app.principal_id` (the acting principal), not
    `app.account_id` - unlike identity.principal, which is account-scoped.
    That distinction is exactly what this test is about."""
    now = dt.datetime.now(dt.UTC)
    async with db.begin():
        await identity_service.apply_rls_context(
            db, account_id=account_id, principal_id=member_id
        )
        await db.execute(
            text(
                "INSERT INTO identity.session "
                "(id, principal_id, expires_at, idle_expires_at, revoked_at, token_hash) "
                "VALUES (:id, :pid, :exp, :idle, NULL, :th)"
            ),
            {
                "id": new_uuid7(),
                "pid": member_id,
                "exp": now + dt.timedelta(days=1),
                "idle": now + dt.timedelta(hours=2),
                "th": identity_tokens.hash_token(raw_token),
            },
        )


@pytest.mark.asyncio
async def test_remove_member_decrements_seats_and_revokes_access(
    db_session: AsyncSession,
) -> None:
    raw_token = f"test-session-token-{uuid.uuid4().hex}"

    async with db_session.begin():
        account = Account(name="Seat Removal Test Account", seat_count=3)
        db_session.add(account)
        await db_session.flush()
        account_id = account.id

    async with db_session.begin():
        # principal_isolation (identity.principal's RLS policy) checks only
        # app.account_id, so any principal_id placeholder is fine here.
        await identity_service.apply_rls_context(
            db_session, account_id=account_id, principal_id=uuid.uuid4()
        )
        admin = Principal(
            account_id=account_id,
            email=f"admin-{uuid.uuid4().hex}@example.com",
            supabase_user_id=uuid.uuid4(),
            role="admin",
        )
        member = Principal(
            account_id=account_id,
            email=f"member-{uuid.uuid4().hex}@example.com",
            supabase_user_id=uuid.uuid4(),
            role="analyst",
        )
        db_session.add_all([admin, member])
        await db_session.flush()
        admin_id, member_id = admin.id, member.id

    await _insert_member_session(
        db_session, account_id=account_id, member_id=member_id, raw_token=raw_token
    )

    admin_identity = Identity(
        principal_id=admin_id,
        account_id=account_id,
        email="admin@example.com",
        role="admin",
    )

    # Pre-condition: the member's session is genuinely live before removal -
    # resolve_session is the exact code path a real authenticated request
    # goes through (not a hand-rolled stand-in for it).
    async with db_session.begin():
        pre_identity = await identity_service.resolve_session(db_session, token=raw_token)
    assert pre_identity is not None
    assert pre_identity.principal_id == member_id

    # Seat count before removal: admin + member = 2 used seats.
    async with db_session.begin():
        await identity_service.apply_rls_context(
            db_session, account_id=account_id, principal_id=admin_id
        )
        overview_before = await get_organization(db=db_session, identity=admin_identity)
    assert overview_before.used_seats == 2
    assert overview_before.available_seats == 1

    # The removal under test.
    async with db_session.begin():
        await identity_service.apply_rls_context(
            db_session, account_id=account_id, principal_id=admin_id
        )
        await remove_member(db=db_session, identity=admin_identity, member_id=member_id)

    # Seat count decrements.
    async with db_session.begin():
        await identity_service.apply_rls_context(
            db_session, account_id=account_id, principal_id=admin_id
        )
        overview_after = await get_organization(db=db_session, identity=admin_identity)
    assert overview_after.used_seats == 1
    assert overview_after.available_seats == 2
    assert all(m.id != member_id for m in overview_after.members)

    # Access is actually revoked, not merely hidden from the member list:
    # the removed member's existing cookie must stop authenticating.
    async with db_session.begin():
        post_identity = await identity_service.resolve_session(db_session, token=raw_token)
    assert post_identity is None, (
        "a removed member's existing session must stop authenticating requests"
    )

    # --- A real, narrow finding this test surfaced ------------------------
    # remove_member's own `UPDATE identity.session SET revoked_at = now()
    # WHERE principal_id = :pid` (organization.py) runs under
    # identity.session's RLS policy, which restricts visibility/writes to
    # `principal_id = current_setting('app.principal_id')` - i.e. the
    # ACTING principal (the admin who is removing someone), never the
    # target being removed. So that UPDATE silently affects zero rows
    # whenever an admin removes someone else (it only works when a
    # principal revokes their own sessions, e.g. change-password). Access
    # is nonetheless correctly revoked above, but only because
    # resolve_session separately gates on `principal_status != 'ACTIVE'`
    # via the SECURITY DEFINER lookup function, which is not RLS-scoped.
    # Fail-closed behaviour holds end-to-end; the explicit revocation line
    # in remove_member is dead code on this path. Confirmed here via a
    # superuser connection that deliberately bypasses RLS to see ground
    # truth - the same reasoning test_rls_identity.py documents for why
    # this suite's admin engine exists at all.
    admin_engine = create_async_engine(get_settings().test_admin_database_url)
    try:
        async with admin_engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT revoked_at FROM identity.session WHERE principal_id = :pid"),
                    {"pid": member_id},
                )
            ).first()
        assert row is not None
        assert row.revoked_at is None, (
            "if this starts failing, remove_member's session-revocation UPDATE has "
            "started actually taking effect (e.g. the RLS policy changed) - update "
            "this assertion and the docstring above, don't just delete it; either way "
            "re-verify resolve_session still denies the removed member (the assertion "
            "above), since that's the real security property, not this one"
        )
    finally:
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_remove_member_rejects_non_admin(db_session: AsyncSession) -> None:
    """Fail-closed on the authorization side too: a non-admin can't remove
    anyone, regardless of what the frontend's own role check does or
    doesn't enforce."""
    from fastapi import HTTPException

    async with db_session.begin():
        account = Account(name="Seat Removal Authz Test Account")
        db_session.add(account)
        await db_session.flush()
        account_id = account.id

    async with db_session.begin():
        await identity_service.apply_rls_context(
            db_session, account_id=account_id, principal_id=uuid.uuid4()
        )
        viewer = Principal(
            account_id=account_id,
            email=f"viewer-{uuid.uuid4().hex}@example.com",
            supabase_user_id=uuid.uuid4(),
            role="viewer",
        )
        target = Principal(
            account_id=account_id,
            email=f"target-{uuid.uuid4().hex}@example.com",
            supabase_user_id=uuid.uuid4(),
            role="analyst",
        )
        db_session.add_all([viewer, target])
        await db_session.flush()
        viewer_id, target_id = viewer.id, target.id

    viewer_identity = Identity(
        principal_id=viewer_id, account_id=account_id, email="viewer@example.com", role="viewer"
    )

    async with db_session.begin():
        await identity_service.apply_rls_context(
            db_session, account_id=account_id, principal_id=viewer_id
        )
        with pytest.raises(HTTPException) as exc_info:
            await remove_member(db=db_session, identity=viewer_identity, member_id=target_id)
    assert exc_info.value.status_code == 403


def test_remove_member_endpoint_declares_no_content_response() -> None:
    """Pins the route's declared response shape (204, no body) - what the
    frontend's `api.removeMember` actually expects - in one place, since
    every functional test above calls `remove_member` directly rather than
    through the router."""
    from fastapi.routing import APIRoute

    from app.modules.api.v1.organization import router

    remove_route = next(
        r
        for r in router.routes
        if getattr(r, "path", None) == "/organization/members/{member_id}"
        and "DELETE" in getattr(r, "methods", set())
    )
    # router.routes is typed as the generic Starlette BaseRoute, which has no
    # status_code - every route FastAPI actually registers is an APIRoute,
    # so this narrows the type instead of asserting/ignoring it past mypy.
    assert isinstance(remove_route, APIRoute)
    assert remove_route.status_code == 204
