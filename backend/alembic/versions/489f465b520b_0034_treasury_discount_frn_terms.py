"""0034 treasury discount and FRN terms tables

Adds the two asset-adapter tables needed to onboard US Treasury Bills
(incl. Cash Management Bills) and Floating Rate Notes as real reference
instruments - FiSovereignTerms' fixed-coupon shape doesn't fit either
(see reference/models.py's own docstrings on both new tables).

Revision ID: 489f465b520b
Revises: 9599f2c8716d
Create Date: 2026-10-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "489f465b520b"
down_revision: str | Sequence[str] | None = "9599f2c8716d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "fi_sovereign_discount_terms",
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("high_rate", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("investment_rate", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("is_cash_management_bill", sa.Boolean(), nullable=False),
        sa.Column("day_count_convention", sa.String(length=32), nullable=False),
        sa.Column("first_issue_date", sa.Date(), nullable=False),
        sa.Column("maturity_date", sa.Date(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["reference.instrument.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instrument_id"),
        schema="reference",
    )
    op.create_table(
        "fi_sovereign_frn_terms",
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("spread", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("index_determination_rate", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("frequency_of_interest_payments", sa.String(length=16), nullable=False),
        sa.Column("day_count_convention", sa.String(length=32), nullable=False),
        sa.Column("first_issue_date", sa.Date(), nullable=False),
        sa.Column("maturity_date", sa.Date(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["reference.instrument.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instrument_id"),
        schema="reference",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("fi_sovereign_frn_terms", schema="reference")
    op.drop_table("fi_sovereign_discount_terms", schema="reference")
