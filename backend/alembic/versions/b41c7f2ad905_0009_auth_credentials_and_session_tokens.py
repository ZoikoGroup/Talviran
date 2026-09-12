"""0009 auth credentials and session tokens

Adds what SEC-001 auth needs on top of the P0 identity shape:

  * principal.password_hash — Argon2id PHC string (§7). Nullable, because a
    principal may authenticate by passkey or federation later and never hold
    a password at all; "no password" and "empty password" must stay distinct.
  * session.token_hash — the SHA-256 of the cookie value. The token itself is
    never stored, so a dump of this table cannot authenticate anyone (§8).
  * session.idle_expires_at — §8 requires both bounds. `expires_at` is the
    absolute cap; this is the sliding one.

The interesting part is the two SECURITY DEFINER functions.

identity.principal and identity.session both run FORCE ROW LEVEL SECURITY,
scoped by the `app.account_id` / `app.principal_id` GUCs. That is correct for
every authenticated request and impossible for the two lookups that happen
*before* a request has an identity:

  * sign-in must find a principal by email, with no account context yet;
  * every request must find a session by token hash, with no principal
    context yet.

The alternatives were worse. A permissive `USING (true)` policy would open
the whole table to the app role for every query, not just these two. Running
auth on the superuser connection would bypass RLS everywhere, not just here.
A definer function is a narrow, named, auditable hole: fixed signature, fixed
projection, EXECUTE granted only to talvrin_app, and `search_path` pinned so
the body cannot be hijacked by a caller-controlled path.

Neither function performs any verification — they return the stored hashes
and the application compares them. Keeping the comparison in Python means the
password hash never becomes a SQL predicate, so it cannot leak through query
logs, timing on an indexed lookup, or an error message.

Revision ID: b41c7f2ad905
Revises: 492acb132ee6
Create Date: 2026-09-12 14:20:11.004312

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b41c7f2ad905"
down_revision: str | Sequence[str] | None = "492acb132ee6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "principal",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        schema="identity",
    )
    op.add_column(
        "session",
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        schema="identity",
    )
    op.add_column(
        "session",
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=True),
        schema="identity",
    )
    # Unique so a token hash can never authenticate two principals, and
    # indexed because it is the lookup key on every authenticated request.
    op.create_index(
        "ix_identity_session_token_hash",
        "session",
        ["token_hash"],
        unique=True,
        schema="identity",
    )

    # Case-insensitive uniqueness: "Shiva@zoikogroup.com" and
    # "shiva@zoikogroup.com" must not be able to become two accounts. The
    # existing UNIQUE(email) constraint is case-sensitive and would allow it.
    op.execute(
        "CREATE UNIQUE INDEX ix_identity_principal_email_lower "
        "ON identity.principal (lower(email))"
    )

    op.execute(
        """
        CREATE FUNCTION identity.lookup_principal_for_auth(p_email text)
        RETURNS TABLE (
            principal_id  uuid,
            account_id    uuid,
            email         varchar,
            status        varchar,
            password_hash varchar
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = identity, pg_catalog
        AS $$
            SELECT p.id, p.account_id, p.email, p.status, p.password_hash
            FROM identity.principal AS p
            WHERE lower(p.email) = lower(p_email)
        $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION identity.lookup_session_by_token(p_token_hash text)
        RETURNS TABLE (
            session_id       uuid,
            principal_id     uuid,
            account_id       uuid,
            email            varchar,
            principal_status varchar,
            expires_at       timestamptz,
            idle_expires_at  timestamptz,
            revoked_at       timestamptz
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = identity, pg_catalog
        AS $$
            SELECT s.id, s.principal_id, p.account_id, p.email, p.status,
                   s.expires_at, s.idle_expires_at, s.revoked_at
            FROM identity.session AS s
            JOIN identity.principal AS p ON p.id = s.principal_id
            WHERE s.token_hash = p_token_hash
        $$;
        """
    )

    # PUBLIC includes every role; a definer function left open to it is a
    # privilege-escalation path, so the grant is explicit and minimal.
    for fn in (
        "identity.lookup_principal_for_auth(text)",
        "identity.lookup_session_by_token(text)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO talvrin_app")

    # The app role owns no identity tables, so DML grants are explicit too.
    op.execute("GRANT USAGE ON SCHEMA identity TO talvrin_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON identity.account, identity.principal, "
        "identity.session TO talvrin_app"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP FUNCTION IF EXISTS identity.lookup_session_by_token(text)")
    op.execute("DROP FUNCTION IF EXISTS identity.lookup_principal_for_auth(text)")
    op.execute("DROP INDEX IF EXISTS identity.ix_identity_principal_email_lower")
    op.drop_index(
        "ix_identity_session_token_hash", table_name="session", schema="identity"
    )
    op.drop_column("session", "idle_expires_at", schema="identity")
    op.drop_column("session", "token_hash", schema="identity")
    op.drop_column("principal", "password_hash", schema="identity")
