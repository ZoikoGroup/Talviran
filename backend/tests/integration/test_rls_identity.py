"""Proves the RLS policies added in migration 0002 actually isolate rows —
not just that CREATE POLICY ran without error. Requires a running, migrated
Postgres, and must run as the unprivileged `talvrin_app` role: `talvrin` is
a Postgres superuser and superusers bypass RLS outright, even with FORCE
ROW LEVEL SECURITY, so this test would pass meaninglessly against it.

Each phase below is its own top-level transaction (not a SAVEPOINT/
begin_nested) deliberately: `set_config(..., is_local=true)` scopes to the
*outermost* transaction, not to a savepoint nested inside one, so reusing
one outer transaction across "different users" would silently leak context
between them — exactly the bug this test caught on first write.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import Account, Principal


async def _set_account_context(session: AsyncSession, account_id: uuid.UUID) -> None:
    # SET LOCAL doesn't accept bind parameters (it's not a regular DML
    # statement) — set_config() is the parameterized equivalent.
    await session.execute(
        text("SELECT set_config('app.account_id', :v, true)"), {"v": str(account_id)}
    )


async def test_principal_rls_isolates_by_account(db_session: AsyncSession) -> None:
    async with db_session.begin():
        account_a = Account(name="Account A")
        account_b = Account(name="Account B")
        db_session.add_all([account_a, account_b])
        await db_session.flush()
        account_a_id, account_b_id = account_a.id, account_b.id

    async with db_session.begin():
        await _set_account_context(db_session, account_a_id)
        db_session.add(Principal(account_id=account_a_id, email="a@example.com"))

    async with db_session.begin():
        await _set_account_context(db_session, account_b_id)
        db_session.add(Principal(account_id=account_b_id, email="b@example.com"))

    async with db_session.begin():
        await _set_account_context(db_session, account_a_id)
        rows = (await db_session.execute(text("SELECT email FROM identity.principal"))).all()
        emails = {r[0] for r in rows}
        assert emails == {"a@example.com"}, "account A must see only its own principal"

    async with db_session.begin():
        # No app.account_id set in this fresh transaction -> current_setting
        # returns NULL -> the policy's `account_id = NULL` is never true ->
        # zero rows, fail-closed.
        rows = (await db_session.execute(text("SELECT email FROM identity.principal"))).all()
        assert rows == [], "with no account context set, RLS must hide every row"
