"""0035_account_cancel_at_period_end

Adds cancel_at_period_end boolean column to identity.account to support graceful
cancellation preserving paid tier benefits until current billing cycle concludes.

Revision ID: 5a81e9b207df
Revises: 489f465b520b
Create Date: 2026-10-31 20:34:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5a81e9b207df"
down_revision: str | Sequence[str] | None = "489f465b520b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "account",
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        schema="identity",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("account", "cancel_at_period_end", schema="identity")
