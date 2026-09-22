"""0026 ai_gateway foundation

P4b AI-001 A0 ("Gateway foundation", exit criterion: "direct-provider
access impossible" - AI-001 §34). Adds a 10th schema beyond the original
9 from migration 0001 (plan §0 didn't give ai_gateway a schema of its own,
since that mapping predated actually reading AI-001 in detail; §27's
DATABASE/REGISTRY CONTRACT makes clear it needs real persistent tables,
not just orchestration logic).

Three tables this slice: ai_provider/ai_model (the registry - AI-001 §5,
"no client-selected model": callers pick a task_type, the registry
resolves the provider/model) and ai_model_execution (the forensic audit
record, AI-001 §18, trimmed to what A0 actually populates - see
app/modules/ai_gateway/models.py's docstring for what's deliberately
deferred to later slices).

Kill switches reuse governance.kill_switch (already exists, migration
0003) rather than a new ai_kill_switch table - see models.py.

Revision ID: 678e8d2c1566
Revises: 59e91ab651d2
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "678e8d2c1566"
down_revision: str | Sequence[str] | None = "59e91ab651d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "talvrin_app"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ai_gateway")
    op.execute(f"GRANT USAGE ON SCHEMA ai_gateway TO {APP_ROLE}")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA ai_gateway "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )

    op.create_table(
        "ai_provider",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        schema="ai_gateway",
    )

    op.create_table(
        "ai_model",
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("model_key", sa.String(length=200), nullable=False),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["provider_id"], ["ai_gateway.ai_provider.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="ai_gateway",
    )
    op.create_index(
        op.f("ix_ai_gateway_ai_model_provider_id"), "ai_model", ["provider_id"],
        unique=False, schema="ai_gateway",
    )
    op.create_index(
        op.f("ix_ai_gateway_ai_model_task_type"), "ai_model", ["task_type"],
        unique=False, schema="ai_gateway",
    )

    op.create_table(
        "ai_model_execution",
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("model_id", sa.UUID(), nullable=False),
        sa.Column("request_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prompt_text", sa.String(), nullable=False),
        sa.Column("response_text", sa.String(), nullable=True),
        sa.Column("finish_reason", sa.String(length=32), nullable=True),
        sa.Column("token_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.String(length=1000), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["provider_id"], ["ai_gateway.ai_provider.id"]),
        sa.ForeignKeyConstraint(["model_id"], ["ai_gateway.ai_model.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="ai_gateway",
    )
    op.create_index(
        op.f("ix_ai_gateway_ai_model_execution_task_type"), "ai_model_execution",
        ["task_type"], unique=False, schema="ai_gateway",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_ai_gateway_ai_model_execution_task_type"),
        table_name="ai_model_execution", schema="ai_gateway",
    )
    op.drop_table("ai_model_execution", schema="ai_gateway")
    op.drop_index(
        op.f("ix_ai_gateway_ai_model_task_type"), table_name="ai_model", schema="ai_gateway",
    )
    op.drop_index(
        op.f("ix_ai_gateway_ai_model_provider_id"), table_name="ai_model", schema="ai_gateway",
    )
    op.drop_table("ai_model", schema="ai_gateway")
    op.drop_table("ai_provider", schema="ai_gateway")
    op.execute("DROP SCHEMA IF EXISTS ai_gateway CASCADE")
