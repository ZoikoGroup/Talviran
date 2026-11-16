"""0039_correction_events_and_reassessment

Closes UAT gap G12: "Corrections create a new version and a
material-change link; affected saved research and monitors are marked
for reassessment." Two things land together, both required before
anything can flag a stale answer:

1. market.correction_event - one row per real value-change correction to
   an accepted_fact, written immediately after reconcile.py sets the
   superseded row's superseded_by_id (the existing correction path - this
   migration adds nothing to how a correction is detected, only a durable
   record of it, with the per-metric materiality.py verdict attached).
   Always written, whether or not the change is material - a correction's
   full history must be reconstructable even for changes nobody needed to
   act on; only a *material* one propagates further (point 2).

2. research.message.reassessment_correction_id and
   monitoring.alert.reassessment_correction_id - nullable pointers set by
   market/pipeline/correction_propagation.py when a material correction's
   old accepted_fact is found (via evidence.evidence_member) inside the
   evidence bundle that backed a saved answer or a delivered alert.
   research.message gets a plain indexed column, not an FK - matching
   evidence.evidence_bundle.research_message_id's own precedent (migration
   0012's docstring): research.message is raw-SQL/encrypted-content owned
   by the research module, not an ORM table evidence.* or market.* should
   take a hard schema dependency on. monitoring.alert already has a real
   cross-schema FK to evidence.evidence_bundle.id, so a matching FK to
   market.correction_event.id here is consistent with that table's own
   existing convention, not a new one.

Both research.message and monitoring.alert run under FORCE ROW LEVEL
SECURITY, account-scoped. Reconciliation (where a correction is detected
and propagated) is platform-wide and sets no account context - and a
single correction can legitimately span many different accounts' saved
research at once, so there is no single account context to set even in
principle. A plain UPDATE from that pipeline would silently affect zero
rows under either table's policy. Both propagation writes therefore go
through a SECURITY DEFINER function, the same pattern this schema already
uses for exactly this class of problem (research.lookup_shared_conversation,
migration 0011) - narrow, auditable, and the only way through by design,
not a relaxed policy.

Revision ID: b4e7a1c9d3f6
Revises: 90c66b2353ef
Create Date: 2026-11-16 10:05:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4e7a1c9d3f6"
down_revision: str | Sequence[str] | None = "90c66b2353ef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "talvrin_app"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "correction_event",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column("metric_id", sa.String(length=64), nullable=False),
        sa.Column("old_fact_id", sa.UUID(), nullable=False),
        sa.Column("new_fact_id", sa.UUID(), nullable=False),
        sa.Column("is_material", sa.Boolean(), nullable=False),
        sa.Column("explanation", sa.String(length=1000), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["old_fact_id"], ["market.accepted_fact.id"]),
        sa.ForeignKeyConstraint(["new_fact_id"], ["market.accepted_fact.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="market",
    )
    op.create_index(
        op.f("ix_market_correction_event_subject_id"),
        "correction_event", ["subject_id"], unique=False, schema="market",
    )
    op.create_index(
        op.f("ix_market_correction_event_metric_id"),
        "correction_event", ["metric_id"], unique=False, schema="market",
    )
    op.create_index(
        op.f("ix_market_correction_event_old_fact_id"),
        "correction_event", ["old_fact_id"], unique=False, schema="market",
    )
    op.create_index(
        op.f("ix_market_correction_event_new_fact_id"),
        "correction_event", ["new_fact_id"], unique=False, schema="market",
    )

    op.add_column(
        "message",
        sa.Column("reassessment_correction_id", sa.UUID(), nullable=True),
        schema="research",
    )
    op.create_index(
        op.f("ix_research_message_reassessment_correction_id"),
        "message", ["reassessment_correction_id"], unique=False, schema="research",
    )

    op.add_column(
        "alert",
        sa.Column("reassessment_correction_id", sa.UUID(), nullable=True),
        schema="monitoring",
    )
    op.create_foreign_key(
        "fk_alert_reassessment_correction",
        "alert", "correction_event",
        ["reassessment_correction_id"], ["id"],
        source_schema="monitoring", referent_schema="market",
    )
    op.create_index(
        op.f("ix_monitoring_alert_reassessment_correction_id"),
        "alert", ["reassessment_correction_id"], unique=False, schema="monitoring",
    )

    # SECURITY DEFINER: see this migration's own docstring for why a plain
    # UPDATE from the (account-agnostic) reconciliation pipeline cannot
    # reach either FORCE-RLS table directly. Owned by whichever role runs
    # migrations (matching research.lookup_shared_conversation's own
    # precedent, migration 0011) - EXECUTE is the only privilege handed to
    # the app role, not table-level UPDATE.
    op.execute(
        """
        CREATE FUNCTION research.mark_messages_for_reassessment(
            p_message_ids uuid[], p_correction_event_id uuid
        )
        RETURNS integer
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = research, pg_catalog
        AS $$
            WITH updated AS (
                UPDATE research.message
                SET reassessment_correction_id = p_correction_event_id
                WHERE id = ANY(p_message_ids)
                RETURNING 1
            )
            SELECT count(*)::integer FROM updated
        $$
        """
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION research.mark_messages_for_reassessment(uuid[], uuid) "
        f"TO {APP_ROLE}"
    )

    op.execute(
        """
        CREATE FUNCTION monitoring.mark_alerts_for_reassessment(
            p_evidence_bundle_ids uuid[], p_correction_event_id uuid
        )
        RETURNS integer
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = monitoring, pg_catalog
        AS $$
            WITH updated AS (
                UPDATE monitoring.alert
                SET reassessment_correction_id = p_correction_event_id
                WHERE evidence_bundle_id = ANY(p_evidence_bundle_ids)
                RETURNING 1
            )
            SELECT count(*)::integer FROM updated
        $$
        """
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION monitoring.mark_alerts_for_reassessment(uuid[], uuid) "
        f"TO {APP_ROLE}"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP FUNCTION IF EXISTS monitoring.mark_alerts_for_reassessment(uuid[], uuid)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS research.mark_messages_for_reassessment(uuid[], uuid)"
    )

    op.drop_index(
        op.f("ix_monitoring_alert_reassessment_correction_id"),
        table_name="alert", schema="monitoring",
    )
    op.drop_constraint(
        "fk_alert_reassessment_correction", "alert", schema="monitoring", type_="foreignkey"
    )
    op.drop_column("alert", "reassessment_correction_id", schema="monitoring")

    op.drop_index(
        op.f("ix_research_message_reassessment_correction_id"),
        table_name="message", schema="research",
    )
    op.drop_column("message", "reassessment_correction_id", schema="research")

    op.drop_index(
        op.f("ix_market_correction_event_new_fact_id"),
        table_name="correction_event", schema="market",
    )
    op.drop_index(
        op.f("ix_market_correction_event_old_fact_id"),
        table_name="correction_event", schema="market",
    )
    op.drop_index(
        op.f("ix_market_correction_event_metric_id"),
        table_name="correction_event", schema="market",
    )
    op.drop_index(
        op.f("ix_market_correction_event_subject_id"),
        table_name="correction_event", schema="market",
    )
    op.drop_table("correction_event", schema="market")
