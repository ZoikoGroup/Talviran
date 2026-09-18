"""0012 supabase-backed credentials

Retires this codebase's own password storage in favour of Supabase Auth
(GoTrue). Two changes to `identity.principal`:

  * `password_hash` is dropped. Argon2id verification, the dummy-hash timing
    guard, and the whole `identity/passwords.py` module are gone with it —
    Supabase now owns hashing, storage and verification of credentials
    entirely; nothing in this codebase ever sees a plaintext password again
    except to hand it to Supabase's own `/auth/v1/signup` and
    `/auth/v1/token` endpoints over TLS.
  * `supabase_user_id uuid NOT NULL UNIQUE` is added — the join key back to
    whichever GoTrue user a principal corresponds to. `identity.session`,
    `identity.account` and everything downstream (governance's FKs into
    `identity.principal`, research's RLS policies) are unchanged: this
    migration only changes *how a principal proves who it is*, not what a
    principal *is* to the rest of the schema.

`lookup_principal_for_auth(text)` (migration 0009) looked a principal up by
email because email was the credential-flow's natural key. It is replaced by
`lookup_principal_by_supabase_id(uuid)` — sign-in now starts from a Supabase
user id (returned by GoTrue after it has already verified the password), not
from an email address the caller merely typed.

The new column is NOT NULL with no default, which requires the table to be
empty when this runs. That is true for this codebase before launch — every
existing local `identity.principal` row was created against the old Argon2id
flow and has no corresponding Supabase user, so there is no value that could
be backfilled into `supabase_user_id` for it regardless. Production has no
rows yet. A team migrating a live table with real users would need a
nullable column, a backfill step, and a later NOT NULL migration instead of
this one-shot version.

Revision ID: 0150dc1bec31
Revises: c7e4a1b9d602
Create Date: 2026-09-16 15:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0150dc1bec31"
down_revision: str | Sequence[str] | None = "c7e4a1b9d602"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "talvrin_app"


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DROP FUNCTION IF EXISTS identity.lookup_principal_for_auth(text)")
    op.drop_column("principal", "password_hash", schema="identity")

    op.add_column(
        "principal",
        sa.Column("supabase_user_id", sa.UUID(), nullable=False),
        schema="identity",
    )
    op.create_index(
        "ix_identity_principal_supabase_user_id",
        "principal",
        ["supabase_user_id"],
        unique=True,
        schema="identity",
    )

    # Same reasoning as the function it replaces (migration 0009): sign-in
    # has to resolve a principal before any RLS context exists, which
    # ordinary policy cannot do. A definer function is a narrow, named,
    # auditable hole rather than a permissive USING(true) policy.
    op.execute(
        """
        CREATE FUNCTION identity.lookup_principal_by_supabase_id(p_supabase_user_id uuid)
        RETURNS TABLE (
            principal_id     uuid,
            account_id       uuid,
            email            varchar,
            status           varchar,
            supabase_user_id uuid
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = identity, pg_catalog
        AS $$
            SELECT p.id, p.account_id, p.email, p.status, p.supabase_user_id
            FROM identity.principal AS p
            WHERE p.supabase_user_id = p_supabase_user_id
        $$;
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION identity.lookup_principal_by_supabase_id(uuid) FROM PUBLIC"
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION identity.lookup_principal_by_supabase_id(uuid) "
        f"TO {APP_ROLE}"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP FUNCTION IF EXISTS identity.lookup_principal_by_supabase_id(uuid)"
    )
    op.drop_index(
        "ix_identity_principal_supabase_user_id",
        table_name="principal",
        schema="identity",
    )
    op.drop_column("principal", "supabase_user_id", schema="identity")

    op.add_column(
        "principal",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        schema="identity",
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
    op.execute("REVOKE ALL ON FUNCTION identity.lookup_principal_for_auth(text) FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION identity.lookup_principal_for_auth(text) TO {APP_ROLE}"
    )
