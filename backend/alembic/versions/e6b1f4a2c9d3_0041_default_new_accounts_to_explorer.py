"""0041_default_new_accounts_to_explorer

New accounts were being created on the paid Professional tier because the
schema default introduced in 0033 was "professional". Change the server-side
default to the free Explorer tier so signups are free until a verified Stripe
checkout (or an explicit dev-only plan change) upgrades them.

Existing rows are deliberately left untouched: a stored "professional" value
may be a legitimately purchased plan, and this migration must never revoke a
paid subscriber's access. It only changes what *future* INSERTs get when the
caller omits plan_tier / billing_cadence.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6b1f4a2c9d3"
down_revision: str | Sequence[str] | None = "c9f3b6e2a1d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Default every newly created account to the free Explorer tier."""
    op.alter_column(
        "account",
        "plan_tier",
        existing_type=sa.String(length=32),
        server_default="explorer",
        existing_nullable=False,
        schema="identity",
    )
    op.alter_column(
        "account",
        "billing_cadence",
        existing_type=sa.String(length=32),
        server_default="monthly",
        existing_nullable=False,
        schema="identity",
    )


def downgrade() -> None:
    """Restore the old (incorrect) paid-by-default behaviour."""
    op.alter_column(
        "account",
        "billing_cadence",
        existing_type=sa.String(length=32),
        server_default="annual",
        existing_nullable=False,
        schema="identity",
    )
    op.alter_column(
        "account",
        "plan_tier",
        existing_type=sa.String(length=32),
        server_default="professional",
        existing_nullable=False,
        schema="identity",
    )
