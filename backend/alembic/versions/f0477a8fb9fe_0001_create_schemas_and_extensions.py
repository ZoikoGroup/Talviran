"""0001 create schemas and extensions

The 9 Postgres schemas from DATA-001, one per owning module-group (plan §0):
identity, reference, market, evidence, calculation, monitoring, governance
(rights+policy), commercial, audit. Also enables btree_gist, required by the
bitemporal GiST exclusion constraint on market.accepted_fact (P1 week 9).

Also grants the unprivileged `talvrin_app` role (created by
infra/init-db/01-roles.sql, applied outside migrations since role creation
is cluster-wide, not per-database DDL) USAGE on every schema, plus default
SELECT/INSERT/UPDATE/DELETE privileges on tables created from here on —
migrations themselves always run as the superuser (see
alembic/env.py:admin_database_url), but the app and RLS policies only mean
something if the app connects as a non-superuser (superusers bypass RLS
outright, even with FORCE ROW LEVEL SECURITY).

Revision ID: f0477a8fb9fe
Revises:
Create Date: 2026-09-10 14:14:14.334662

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0477a8fb9fe"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMAS = [
    "identity",
    "reference",
    "market",
    "evidence",
    "calculation",
    "monitoring",
    "governance",
    "commercial",
    "audit",
]

APP_ROLE = "talvrin_app"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    for schema in SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        op.execute(f"GRANT USAGE ON SCHEMA {schema} TO {APP_ROLE}")
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
        )


def downgrade() -> None:
    for schema in reversed(SCHEMAS):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
