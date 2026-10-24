"""0033_account_commercial_stripe

Adds commercial plan and Stripe customer / subscription columns to identity.account:
- plan_tier: Active subscription tier (explorer, research, professional, teams, enterprise)
- billing_cadence: Billing frequency (monthly, annual)
- seat_count: Allowed user seats allocated to the account
- current_period_end: Timestamp when the active billing cycle ends or renews
- stripe_customer_id: Stripe Customer object ID (cus_...)
- stripe_subscription_id: Stripe Subscription object ID (sub_...)
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9599f2c8716d"
down_revision: str | Sequence[str] | None = "8488f1b7dc0a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "account",
        sa.Column("plan_tier", sa.String(length=32), server_default="professional", nullable=False),
        schema="identity",
    )
    op.add_column(
        "account",
        sa.Column("billing_cadence", sa.String(length=32), server_default="annual", nullable=False),
        schema="identity",
    )
    op.add_column(
        "account",
        sa.Column("seat_count", sa.Integer(), server_default="1", nullable=False),
        schema="identity",
    )
    op.add_column(
        "account",
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        schema="identity",
    )
    op.add_column(
        "account",
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        schema="identity",
    )
    op.add_column(
        "account",
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
        schema="identity",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("account", "stripe_subscription_id", schema="identity")
    op.drop_column("account", "stripe_customer_id", schema="identity")
    op.drop_column("account", "current_period_end", schema="identity")
    op.drop_column("account", "seat_count", schema="identity")
    op.drop_column("account", "billing_cadence", schema="identity")
    op.drop_column("account", "plan_tier", schema="identity")
