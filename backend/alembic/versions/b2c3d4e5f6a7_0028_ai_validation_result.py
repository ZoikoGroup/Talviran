"""0028 ai_validation_result

P4b AI-001 A2 ("validation", AI-001 §34): one row per validated model
response (up to two per invoke_model call - the original attempt and the
single bounded regeneration on failure, AI-001 §23) - see
app/modules/ai_gateway/validation.py.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_validation_result",
        sa.Column("ai_model_execution_id", sa.UUID(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("failure_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ai_model_execution_id"], ["ai_gateway.ai_model_execution.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="ai_gateway",
    )
    op.create_index(
        op.f("ix_ai_gateway_ai_validation_result_ai_model_execution_id"),
        "ai_validation_result", ["ai_model_execution_id"], unique=False, schema="ai_gateway",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_ai_gateway_ai_validation_result_ai_model_execution_id"),
        table_name="ai_validation_result", schema="ai_gateway",
    )
    op.drop_table("ai_validation_result", schema="ai_gateway")
