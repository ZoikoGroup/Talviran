"""0011 research conversations, sharing and envelope encryption

Adds the `research` schema: conversations, their messages, the projects that
group them, per-account data keys, and revocable share links.

**Why a tenth schema.** DATA-001 §17.2 lists nine canonical schemas and none
of them owns a conversation. §12.2 names the category — "persistent research
state" — but enumerates only watchlists, saved comparisons and bookmarks.
`monitoring` is rules/evaluations/alerts and `evidence` is source artefacts;
putting chats in either would overload a schema whose meaning is already
fixed. `research` keeps the neutral-technical-name rule of §4.3 and leaves the
nine canonical schemas untouched.

**Isolation.** Every table here is tenant-owned, so every table carries
`account_id` and runs `FORCE ROW LEVEL SECURITY` against the session-local
`app.account_id` GUC — the same pattern and the same `NULLIF(...)` care as
migration 0002, for the same pooled-connection reason documented there.
SEC-001 §11 wants two independent boundaries; this is the second one, so a
missed check in application code cannot become a cross-account read.

**Encryption.** Message bodies and conversation titles are stored as AES-256-GCM
ciphertext under a per-account data key, itself wrapped by KMS
(app.modules.research.crypto, SEC-001 §15.1). Titles are encrypted as well as
bodies because a title like "short thesis on <issuer>" leaks the research
intent even when the body does not. The cost is that neither can be searched
or sorted in SQL; ordering therefore uses `last_message_at`, which is
deliberately left in clear.

**Sharing.** A share is a capability: possession of the token grants read
access to one conversation, bounded at the message sequence current when the
link was created, so later messages in a still-active chat are not
retroactively exposed. Only the token's SHA-256 digest is stored, exactly as
for sessions in 0009. Because a viewer has no account context, the read path
runs through two SECURITY DEFINER functions rather than a relaxed policy —
and those functions re-check revocation and expiry themselves, so a share
stays closed even if a caller forgets to.

`lookup_shared_conversation` also returns the owner's *wrapped* data key. It
has to: the shared messages are ciphertext under that key, and the viewer has
no account context to read `account_data_key` through policy. What comes back
is still wrapped, so it is inert without the KMS unwrap permission the
application holds — and it is reachable only by presenting a live share token.

Revision ID: c7e4a1b9d602
Revises: dc5d1ca5a93d
Create Date: 2026-09-15 10:22:04.118293

Renumbered from 0010 to 0011 and rebased onto dc5d1ca5a93d: both this
migration and Ravi Reddy's calculation-schema migration were written
independently against the same parent (b41c7f2ad905) and both claimed
"0010" — a genuine branch point, not a textual merge conflict. This one
yields; the calculation schema keeps its original id and slots in ahead.

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7e4a1b9d602"
down_revision: str | Sequence[str] | None = "dc5d1ca5a93d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "talvrin_app"

#: Tables that are tenant-owned and therefore RLS-scoped by account.
ACCOUNT_SCOPED = (
    "project",
    "conversation",
    "message",
    "conversation_share",
    "account_data_key",
)


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE SCHEMA IF NOT EXISTS research")

    # --- per-account data keys (SEC-001 §15.1) -------------------------------
    # One row per account. The plaintext DEK never lands here; only its wrapped
    # form. Deleting this row is the §15.2 cryptographic erase for the account.
    op.create_table(
        "account_data_key",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("wrapped_dek", sa.LargeBinary(), nullable=False),
        sa.Column("key_name", sa.String(length=400), nullable=False),
        sa.Column("envelope_version", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["identity.account.id"]),
        sa.PrimaryKeyConstraint("account_id"),
        schema="research",
    )

    # --- projects -----------------------------------------------------------
    op.create_table(
        "project",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("principal_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["identity.account.id"]),
        sa.ForeignKeyConstraint(["principal_id"], ["identity.principal.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="research",
    )
    op.create_index(
        "ix_research_project_account_id",
        "project",
        ["account_id", "created_at"],
        unique=False,
        schema="research",
    )

    # --- conversations ------------------------------------------------------
    op.create_table(
        "conversation",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("principal_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        # Ciphertext; NULL until the conversation earns a title.
        sa.Column("title", sa.LargeBinary(), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Left in clear: list ordering has to happen in SQL, and a timestamp
        # discloses far less than a title would.
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["identity.account.id"]),
        sa.ForeignKeyConstraint(["principal_id"], ["identity.principal.id"]),
        sa.ForeignKeyConstraint(
            ["project_id"], ["research.project.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="research",
    )
    op.create_index(
        "ix_research_conversation_account_recent",
        "conversation",
        ["account_id", "last_message_at"],
        unique=False,
        schema="research",
    )
    op.create_index(
        "ix_research_conversation_project",
        "conversation",
        ["project_id"],
        unique=False,
        schema="research",
    )

    # --- messages -----------------------------------------------------------
    # account_id is denormalised from the parent conversation so the RLS policy
    # can be evaluated without a join (DATA-001 §17: account_id-leading indexes
    # on RLS-scoped hot paths). The trigger below keeps it honest.
    op.create_table(
        "message",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('USER', 'ASSISTANT', 'SYSTEM')", name="ck_message_role"
        ),
        sa.CheckConstraint("seq > 0", name="ck_message_seq_positive"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["research.conversation.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["account_id"], ["identity.account.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "seq", name="uq_message_conversation_seq"),
        schema="research",
    )
    op.create_index(
        "ix_research_message_account_conversation",
        "message",
        ["account_id", "conversation_id", "seq"],
        unique=False,
        schema="research",
    )

    # A message must never carry a different account_id from its conversation:
    # that would place a row inside another tenant's RLS scope. A foreign key
    # cannot express it, so enforce it in the database rather than trusting
    # every future write path to get it right.
    op.execute(
        """
        CREATE FUNCTION research.assert_message_account_matches()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = research, pg_catalog
        AS $$
        DECLARE
            owner_account uuid;
        BEGIN
            SELECT c.account_id INTO owner_account
            FROM research.conversation AS c
            WHERE c.id = NEW.conversation_id;

            IF owner_account IS NULL THEN
                RAISE EXCEPTION 'conversation % not visible', NEW.conversation_id;
            END IF;

            IF owner_account <> NEW.account_id THEN
                RAISE EXCEPTION
                    'message account_id % does not match conversation account %',
                    NEW.account_id, owner_account;
            END IF;

            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_message_account_matches
        BEFORE INSERT OR UPDATE ON research.message
        FOR EACH ROW EXECUTE FUNCTION research.assert_message_account_matches()
        """
    )

    # The same hole exists one level up, and is easy to miss: a foreign key is
    # checked by the system and therefore ignores RLS, so `project_id` pointing
    # at another tenant's project satisfies the constraint perfectly well. The
    # policy's WITH CHECK only constrains the row's own account_id, not what it
    # references. Without this trigger an account can file its conversations
    # into a stranger's project.
    op.execute(
        """
        CREATE FUNCTION research.assert_conversation_project_matches()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = research, pg_catalog
        AS $$
        DECLARE
            owner_account uuid;
        BEGIN
            IF NEW.project_id IS NULL THEN
                RETURN NEW;
            END IF;

            SELECT p.account_id INTO owner_account
            FROM research.project AS p
            WHERE p.id = NEW.project_id;

            IF owner_account IS NULL OR owner_account <> NEW.account_id THEN
                RAISE EXCEPTION
                    'project % is not owned by account %',
                    NEW.project_id, NEW.account_id;
            END IF;

            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_conversation_project_matches
        BEFORE INSERT OR UPDATE ON research.conversation
        FOR EACH ROW EXECUTE FUNCTION research.assert_conversation_project_matches()
        """
    )

    # --- share links --------------------------------------------------------
    op.create_table(
        "conversation_share",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("created_by_principal_id", sa.UUID(), nullable=False),
        # Digest only — the usable token exists in the link and nowhere else.
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        # The share is a snapshot: messages after this sequence stay private
        # even as the conversation continues.
        sa.Column("shared_up_to_seq", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["research.conversation.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["account_id"], ["identity.account.id"]),
        sa.ForeignKeyConstraint(
            ["created_by_principal_id"], ["identity.principal.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="research",
    )
    op.create_index(
        "uq_research_conversation_share_token",
        "conversation_share",
        ["token_hash"],
        unique=True,
        schema="research",
    )
    op.create_index(
        "ix_research_conversation_share_conversation",
        "conversation_share",
        ["account_id", "conversation_id"],
        unique=False,
        schema="research",
    )

    # --- row level security -------------------------------------------------
    # See migration 0002 for why NULLIF(current_setting(..., true), '') is
    # required rather than a bare cast: a pooled connection that set the GUC
    # for an earlier request reads '' afterwards, and ''::uuid is a hard error
    # instead of a clean "no rows".
    for table in ACCOUNT_SCOPED:
        op.execute(f"ALTER TABLE research.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE research.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_isolation ON research.{table}
            USING (account_id = NULLIF(current_setting('app.account_id', true), '')::uuid)
            WITH CHECK (account_id = NULLIF(current_setting('app.account_id', true), '')::uuid)
            """
        )

    # --- share resolution (SECURITY DEFINER, like 0009) ---------------------
    # A viewer holding a share link has no account context, so ordinary policy
    # would correctly return nothing. These two functions are the only way
    # through, and they enforce revocation, expiry, deletion and the sequence
    # bound themselves — the application checks the same things, and neither
    # relies on the other (SEC-001 §11, two independent boundaries).
    op.execute(
        """
        CREATE FUNCTION research.lookup_shared_conversation(p_token_hash text)
        RETURNS TABLE (
            conversation_id uuid,
            title bytea,
            model varchar,
            account_id uuid,
            shared_up_to_seq integer,
            created_at timestamptz,
            wrapped_dek bytea,
            key_name varchar,
            envelope_version smallint
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = research, pg_catalog
        AS $$
            SELECT c.id, c.title, c.model, c.account_id,
                   s.shared_up_to_seq, c.created_at,
                   k.wrapped_dek, k.key_name, k.envelope_version
            FROM research.conversation_share AS s
            JOIN research.conversation AS c ON c.id = s.conversation_id
            JOIN research.account_data_key AS k ON k.account_id = c.account_id
            WHERE s.token_hash = p_token_hash
              AND s.revoked_at IS NULL
              AND (s.expires_at IS NULL OR s.expires_at > now())
              AND c.deleted_at IS NULL
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION research.lookup_shared_messages(p_token_hash text)
        RETURNS TABLE (
            message_id uuid,
            conversation_id uuid,
            seq integer,
            role varchar,
            content bytea,
            created_at timestamptz
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = research, pg_catalog
        AS $$
            SELECT m.id, m.conversation_id, m.seq, m.role, m.content, m.created_at
            FROM research.conversation_share AS s
            JOIN research.conversation AS c ON c.id = s.conversation_id
            JOIN research.message AS m
              ON m.conversation_id = s.conversation_id
             AND m.seq <= s.shared_up_to_seq
            WHERE s.token_hash = p_token_hash
              AND s.revoked_at IS NULL
              AND (s.expires_at IS NULL OR s.expires_at > now())
              AND c.deleted_at IS NULL
            ORDER BY m.seq
        $$
        """
    )

    # PUBLIC includes every role; a definer function left open to it is a
    # privilege-escalation path, so the grant is explicit and minimal.
    for fn in (
        "research.lookup_shared_conversation(text)",
        "research.lookup_shared_messages(text)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {APP_ROLE}")

    # --- grants -------------------------------------------------------------
    # Migration 0001 set USAGE and default privileges for the nine schemas it
    # created; a schema added later needs its own.
    op.execute(f"GRANT USAGE ON SCHEMA research TO {APP_ROLE}")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA research "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )
    for table in ACCOUNT_SCOPED:
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON research.{table} TO {APP_ROLE}"
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP FUNCTION IF EXISTS research.lookup_shared_messages(text)")
    op.execute("DROP FUNCTION IF EXISTS research.lookup_shared_conversation(text)")
    for table in ACCOUNT_SCOPED:
        op.execute(f"DROP POLICY IF EXISTS {table}_isolation ON research.{table}")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_conversation_project_matches "
        "ON research.conversation"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS research.assert_conversation_project_matches()"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_message_account_matches ON research.message"
    )
    op.execute("DROP FUNCTION IF EXISTS research.assert_message_account_matches()")
    op.drop_table("conversation_share", schema="research")
    op.drop_table("message", schema="research")
    op.drop_table("conversation", schema="research")
    op.drop_table("project", schema="research")
    op.drop_table("account_data_key", schema="research")
    op.execute("DROP SCHEMA IF EXISTS research CASCADE")
