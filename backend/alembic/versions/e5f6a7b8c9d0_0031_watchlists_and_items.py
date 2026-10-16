"""0031 watchlists table with RLS and item relationships

DATA-001 §12.2 names persistent research state including watchlists.
Tenant-owned with account_id and FORCE ROW LEVEL SECURITY.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d7706a4229b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "talvrin_app"

ACCOUNT_SCOPED = (
    "watchlist",
    "watchlist_item",
)


def upgrade() -> None:
    op.create_table(
        "watchlist",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("principal_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["account_id"], ["identity.account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["principal_id"], ["identity.principal.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="research",
    )
    op.create_index(
        "ix_research_watchlist_account_id",
        "watchlist",
        ["account_id", "created_at"],
        unique=False,
        schema="research",
    )

    op.create_table(
        "watchlist_item",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("watchlist_id", sa.UUID(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("asset_class", sa.String(length=32), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["account_id"], ["identity.account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["watchlist_id"], ["research.watchlist.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["reference.instrument.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_item_symbol"),
        schema="research",
    )
    op.create_index(
        "ix_research_watchlist_item_watchlist",
        "watchlist_item",
        ["account_id", "watchlist_id", "sort_order"],
        unique=False,
        schema="research",
    )

    for table in ACCOUNT_SCOPED:
        op.execute(f"ALTER TABLE research.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE research.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_isolation ON research.{table}
            USING (account_id = NULLIF(current_setting('app.account_id', true), '')::uuid)
            WITH CHECK (account_id = NULLIF(current_setting('app.account_id', true), '')::uuid)
            """
        )
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON research.{table} TO {APP_ROLE}"
        )


def downgrade() -> None:
    for table in ACCOUNT_SCOPED:
        op.execute(f"DROP POLICY IF EXISTS {table}_isolation ON research.{table}")
    op.drop_table("watchlist_item", schema="research")
    op.drop_table("watchlist", schema="research")
