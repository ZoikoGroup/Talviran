"""0029 ai_model priority

P4b AI-001 A3 ("routing", AI-001 §34): multiple PRODUCTION AIModel rows
may now share a task_type - `priority` (lower tried first) lets
gateway.py's routing loop order candidate routes deterministically. See
app/modules/ai_gateway/models.py's docstring.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_model",
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        schema="ai_gateway",
    )
    op.alter_column("ai_model", "priority", server_default=None, schema="ai_gateway")


def downgrade() -> None:
    op.drop_column("ai_model", "priority", schema="ai_gateway")
