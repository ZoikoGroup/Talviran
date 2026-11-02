"""0036_organization_and_invitations

Adds:
1. role column to identity.principal (default 'admin' for primary user, supporting 'analyst' and 'viewer')
2. identity.organization_invitation table for inviting teammates with token hash, role, expiration, and status
3. RLS policy on identity.organization_invitation scoped to account_id

Revision ID: 1cca38a83d92
Revises: 5a81e9b207df
Create Date: 2026-11-02 17:34:48.468618

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1cca38a83d92"
down_revision: str | Sequence[str] | None = "5a81e9b207df"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Add role column to identity.principal
    op.add_column(
        "principal",
        sa.Column(
            "role",
            sa.String(length=32),
            server_default="admin",
            nullable=False,
        ),
        schema="identity",
    )

    # 2. Create identity.organization_invitation table
    op.create_table(
        "organization_invitation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.account.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "invited_by_principal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.principal.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=32), server_default="analyst", nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="identity",
    )
    op.create_index(
        "ix_identity_invitation_account_email",
        "organization_invitation",
        ["account_id", "email"],
        unique=False,
        schema="identity",
    )

    # 3. Enable and enforce RLS on organization_invitation
    op.execute("ALTER TABLE identity.organization_invitation ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE identity.organization_invitation FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY invitation_account_isolation ON identity.organization_invitation
        USING (account_id = NULLIF(current_setting('app.account_id', true), '')::uuid)
        WITH CHECK (account_id = NULLIF(current_setting('app.account_id', true), '')::uuid)
        """
    )

    # 4. Update lookup_session_by_token and lookup_principal_by_supabase_id to include role
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
    op.execute("REVOKE ALL ON FUNCTION identity.lookup_principal_by_supabase_id(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION identity.lookup_principal_by_supabase_id(uuid) TO talvrin_app")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS invitation_account_isolation ON identity.organization_invitation")
    op.drop_index(
        "ix_identity_invitation_account_email",
        table_name="organization_invitation",
        schema="identity",
    )
    op.drop_table("organization_invitation", schema="identity")
    op.drop_column("principal", "role", schema="identity")
