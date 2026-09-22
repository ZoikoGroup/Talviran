"""0027 ai_model_execution evidence_bundle_id

P4b AI-001 A1 ("evidence path", AI-001 §34): every model invocation now
carries the id of the EvidenceBundle it was grounded on - see
app/modules/ai_gateway/evidence_path.py. Not a FK (see models.py's
docstring on this column) - the owning schema (evidence) isn't guaranteed
loaded first in every process, and this forensic row must survive a later
bundle purge.

Existing ai_model_execution rows predate this column and are exclusively
A0 proof-call data (live-verification smoke tests against Gemini/Groq,
not product data) - safe to clear rather than backfill.

Revision ID: a1b2c3d4e5f6
Revises: 678e8d2c1566
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "678e8d2c1566"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("TRUNCATE ai_gateway.ai_model_execution")
    op.add_column(
        "ai_model_execution",
        sa.Column("evidence_bundle_id", sa.UUID(), nullable=False),
        schema="ai_gateway",
    )


def downgrade() -> None:
    op.drop_column("ai_model_execution", "evidence_bundle_id", schema="ai_gateway")
