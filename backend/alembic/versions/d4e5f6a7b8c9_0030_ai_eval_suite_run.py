"""0030 ai_eval_suite, ai_eval_run

P4b AI-001 A4 ("evaluation", AI-001 §34): a named eval suite identity
and one row per real execution against a live task_type/provider route -
see app/modules/ai_gateway/eval_suite.py.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_eval_suite",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="ai_gateway",
    )

    op.create_table(
        "ai_eval_run",
        sa.Column("ai_eval_suite_id", sa.UUID(), nullable=False),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("failed_cases", sa.Integer(), nullable=False),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ai_eval_suite_id"], ["ai_gateway.ai_eval_suite.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="ai_gateway",
    )
    op.create_index(
        op.f("ix_ai_gateway_ai_eval_run_ai_eval_suite_id"), "ai_eval_run",
        ["ai_eval_suite_id"], unique=False, schema="ai_gateway",
    )
    op.create_index(
        op.f("ix_ai_gateway_ai_eval_run_task_type"), "ai_eval_run",
        ["task_type"], unique=False, schema="ai_gateway",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_ai_gateway_ai_eval_run_task_type"), table_name="ai_eval_run",
        schema="ai_gateway",
    )
    op.drop_index(
        op.f("ix_ai_gateway_ai_eval_run_ai_eval_suite_id"), table_name="ai_eval_run",
        schema="ai_gateway",
    )
    op.drop_table("ai_eval_run", schema="ai_gateway")
    op.drop_table("ai_eval_suite", schema="ai_gateway")
