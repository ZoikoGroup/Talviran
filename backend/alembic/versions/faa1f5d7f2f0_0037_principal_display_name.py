"""0037_principal_display_name

Adds display_name to identity.principal (bug T10: Settings -> Account ->
Display name previously had no backend column at all and was stored only in
a global, non-account-scoped browser localStorage key - lost on a fresh
sign-in and, worse, not scoped per account on a shared browser. Nullable:
null means "derive it from the email" (identity/service.py's
default_display_name), matching this product's existing behaviour for every
principal that has never customised it, so no backfill is needed.

Revision ID: faa1f5d7f2f0
Revises: 1cca38a83d92
Create Date: 2026-11-13 15:12:46.880481

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'faa1f5d7f2f0'
down_revision: str | Sequence[str] | None = '1cca38a83d92'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "principal",
        sa.Column("display_name", sa.String(length=120), nullable=True),
        schema="identity",
    )

    # Both SECURITY DEFINER lookup functions (0012, extended by 0032's
    # totp_enabled and 0036's role) must also return display_name, or
    # identity.service's per-request Identity can never see it.
    op.execute("DROP FUNCTION IF EXISTS identity.lookup_principal_by_supabase_id(uuid)")
    op.execute(
        """
        CREATE FUNCTION identity.lookup_principal_by_supabase_id(p_supabase_user_id uuid)
        RETURNS TABLE (
            principal_id     uuid,
            account_id       uuid,
            email            varchar,
            status           varchar,
            supabase_user_id uuid,
            totp_enabled     boolean,
            role             varchar,
            display_name     varchar
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = identity, pg_catalog
        AS $$
            SELECT p.id, p.account_id, p.email, p.status, p.supabase_user_id, p.totp_enabled,
                   p.role, p.display_name
            FROM identity.principal AS p
            WHERE p.supabase_user_id = p_supabase_user_id
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION identity.lookup_principal_by_supabase_id(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION identity.lookup_principal_by_supabase_id(uuid) TO talvrin_app")

    op.execute("DROP FUNCTION IF EXISTS identity.lookup_session_by_token(text)")
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
            revoked_at       timestamptz,
            totp_enabled     boolean,
            role             varchar,
            display_name     varchar
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = identity, pg_catalog
        AS $$
            SELECT s.id, s.principal_id, p.account_id, p.email, p.status,
                   s.expires_at, s.idle_expires_at, s.revoked_at, p.totp_enabled, p.role,
                   p.display_name
            FROM identity.session AS s
            JOIN identity.principal AS p ON p.id = s.principal_id
            WHERE s.token_hash = p_token_hash
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION identity.lookup_session_by_token(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION identity.lookup_session_by_token(text) TO talvrin_app")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP FUNCTION IF EXISTS identity.lookup_session_by_token(text)")
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
            revoked_at       timestamptz,
            totp_enabled     boolean,
            role             varchar
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = identity, pg_catalog
        AS $$
            SELECT s.id, s.principal_id, p.account_id, p.email, p.status,
                   s.expires_at, s.idle_expires_at, s.revoked_at, p.totp_enabled, p.role
            FROM identity.session AS s
            JOIN identity.principal AS p ON p.id = s.principal_id
            WHERE s.token_hash = p_token_hash
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION identity.lookup_session_by_token(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION identity.lookup_session_by_token(text) TO talvrin_app")

    op.execute("DROP FUNCTION IF EXISTS identity.lookup_principal_by_supabase_id(uuid)")
    op.execute(
        """
        CREATE FUNCTION identity.lookup_principal_by_supabase_id(p_supabase_user_id uuid)
        RETURNS TABLE (
            principal_id     uuid,
            account_id       uuid,
            email            varchar,
            status           varchar,
            supabase_user_id uuid,
            totp_enabled     boolean,
            role             varchar
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = identity, pg_catalog
        AS $$
            SELECT p.id, p.account_id, p.email, p.status, p.supabase_user_id, p.totp_enabled, p.role
            FROM identity.principal AS p
            WHERE p.supabase_user_id = p_supabase_user_id
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION identity.lookup_principal_by_supabase_id(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION identity.lookup_principal_by_supabase_id(uuid) TO talvrin_app")

    op.drop_column("principal", "display_name", schema="identity")
