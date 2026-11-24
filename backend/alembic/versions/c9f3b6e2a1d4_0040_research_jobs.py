"""0040_research_jobs

Closes UAT gap G15: "Recovery, source outages and async cancellation were
not established. Define typed states, safe retry and rollback... Show
queued/running/completed/failed/cancel-requested/canceled states
accurately. A canceled browser subscription is not proof that the server
job stopped. Retry must be idempotent; late results must not appear in
another conversation."

Before this, POST /api/v1/research was a single synchronous request:
compose the answer inline, commit, return it - no job exists to cancel,
no typed state to show while it runs, and a slow/stuck AI Gateway call
had no recovery path except the client giving up. research.research_job
is a real, durable, typed-state record of one research request, processed
by scripts/run_research_worker.py (same FOR UPDATE SKIP LOCKED discipline
as calculation.calculation_job) rather than inline in the request thread -
the only way "cancel-requested" can mean anything real rather than just
hiding a spinner client-side.

Column choices mirror research.message's own precedent exactly (same
module, same sensitivity): encrypted_query/encrypted_result are envelope-
encrypted under the account's DEK with the conversation as AAD, not
plaintext - this table holds the same class of user research content
message does. idempotency_key + the partial unique index is the same
shape support.ticket's (migration 0038) already uses, adapted for a
table where account_id is never NULL (no anonymous caller here - every
caller of POST /api/v1/research/jobs is already signed in).

Revision ID: c9f3b6e2a1d4
Revises: b4e7a1c9d3f6
Create Date: 2026-11-16 11:40:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9f3b6e2a1d4"
down_revision: str | Sequence[str] | None = "b4e7a1c9d3f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "research_job",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("principal_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
        sa.Column("encrypted_query", sa.LargeBinary(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="QUEUED"
        ),
        sa.Column("encrypted_result", sa.LargeBinary(), nullable=True),
        sa.Column("result_message_id", sa.UUID(), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', "
            "'CANCEL_REQUESTED', 'CANCELED')",
            name="ck_research_job_status",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["identity.account.id"]),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["research.conversation.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["result_message_id"], ["research.message.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="research",
    )
    op.create_index(
        "ix_research_research_job_account_status",
        "research_job", ["account_id", "status"], unique=False, schema="research",
    )
    op.create_index(
        "ix_research_research_job_conversation",
        "research_job", ["conversation_id"], unique=False, schema="research",
    )
    # Claiming queries filter on status alone ("any account's next queued
    # job"), scoped afterward by whichever account's RLS context the worker
    # has already applied - see run_research_worker.py's per-account loop,
    # the same shape run_monitoring_worker.py already uses for exactly this
    # "platform-wide work, account-scoped tables" shape.
    op.create_index(
        "ix_research_research_job_status_created",
        "research_job", ["status", "created_at"], unique=False, schema="research",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ix_research_job_idempotency
        ON research.research_job (account_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )

    op.execute("ALTER TABLE research.research_job ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE research.research_job FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY research_job_isolation ON research.research_job
        USING (account_id = NULLIF(current_setting('app.account_id', true), '')::uuid)
        WITH CHECK (account_id = NULLIF(current_setting('app.account_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS research_job_isolation ON research.research_job")
    op.execute("DROP INDEX IF EXISTS research.ix_research_job_idempotency")
    op.drop_index(
        "ix_research_research_job_status_created", table_name="research_job", schema="research",
    )
    op.drop_index(
        "ix_research_research_job_conversation", table_name="research_job", schema="research",
    )
    op.drop_index(
        "ix_research_research_job_account_status", table_name="research_job", schema="research",
    )
    op.drop_table("research_job", schema="research")
