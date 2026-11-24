"""0042_monitoring_rule_notify_email

T28 (2026-11-23 UAT gap analysis): the "Email Alert" channel checkbox in
SetAlertModal.tsx collected an email address and silently discarded it -
monitoring_rule_version had no column to store it, so the real EMAIL
transport delivery.py's deliver_alert() already implemented was never
given a recipient. Adds the one field actually needed to close that gap.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7d4e1f08b26"
down_revision: str | Sequence[str] | None = "e6b1f4a2c9d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "monitoring_rule_version",
        sa.Column("notify_email", sa.String(length=320), nullable=True),
        schema="monitoring",
    )


def downgrade() -> None:
    op.drop_column("monitoring_rule_version", "notify_email", schema="monitoring")
