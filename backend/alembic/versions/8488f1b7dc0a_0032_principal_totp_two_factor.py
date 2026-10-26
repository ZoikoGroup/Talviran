"""0032_principal_totp_two_factor

Adds TOTP two-factor authentication columns and lookup to identity.principal.
- totp_secret: Encrypted or masked Base32 secret for authenticator apps (Google Auth, 1Password)
- totp_enabled: Boolean flag indicating if 2FA verification is enforced on login
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8488f1b7dc0a"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "talvrin_app"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "principal",
        sa.Column("totp_secret", sa.String(length=128), nullable=True),
        schema="identity",
    )
    op.add_column(
        "principal",
        sa.Column("totp_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        schema="identity",
    )

    # Recreate lookup_principal_by_supabase_id to return totp_enabled
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
            totp_enabled     boolean
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = identity, pg_catalog
        AS $$
            SELECT p.id, p.account_id, p.email, p.status, p.supabase_user_id, p.totp_enabled
            FROM identity.principal AS p
            WHERE p.supabase_user_id = p_supabase_user_id
        $$;
        """
    )
    # Recreate lookup_session_by_token to return totp_enabled
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
            totp_enabled     boolean
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = identity, pg_catalog
        AS $$
            SELECT s.id, s.principal_id, p.account_id, p.email, p.status,
                   s.expires_at, s.idle_expires_at, s.revoked_at, p.totp_enabled
            FROM identity.session AS s
            JOIN identity.principal AS p ON p.id = s.principal_id
            WHERE s.token_hash = p_token_hash
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION identity.lookup_session_by_token(text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION identity.lookup_session_by_token(text) TO {APP_ROLE}")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP FUNCTION IF EXISTS identity.lookup_principal_by_supabase_id(uuid)")
    op.drop_column("principal", "totp_enabled", schema="identity")
    op.drop_column("principal", "totp_secret", schema="identity")
