"""0029 index unindexed FK columns

Adds indexes on several foreign-key/lookup columns that were missing
one, found during a backend audit: evidence.evidence_member's five
member-kind FKs (accepted_fact_id, calculation_result_id,
document_chunk_id, citation_locator_id, source_artifact_id) -
evidence_bundle_id was already indexed, but a future "find every
evidence_member citing this fact/chunk/result" query (e.g. a
purge/cascade-check before deleting an AcceptedFact or DocumentChunk)
would otherwise be an unindexed scan; market.reconciliation_decision.
accepted_fact_id, to match its already-indexed subject_id/metric_id
siblings on the same table; ai_gateway.ai_model_execution.provider_id
and .model_id - this table is the forensic audit row the Gateway writes
on every single call (AI-001 §18), so it grows steadily, and an admin
query like "all executions for this model" would otherwise scan it
whole; calculation.calculation_job.calculation_specification_id, to
match calculation_result's already-indexed column of the same name.

None of these are on a request-path WHERE clause today (nothing in this
codebase currently queries evidence_member by these columns, only by
evidence_bundle_id), so this is precautionary/consistency work rather
than fixing an observed slow query - cheap indexes on columns that are
the obvious future lookup key for their table, matching the pattern
every comparable FK elsewhere in the schema already follows.

Revision ID: 7dafc8b52e4b
Revises: b2c3d4e5f6a7
Create Date: 2026-09-24 19:15:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7dafc8b52e4b"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ix_evidence_member_accepted_fact_id",
        "evidence_member",
        ["accepted_fact_id"],
        schema="evidence",
    )
    op.create_index(
        "ix_evidence_member_calculation_result_id",
        "evidence_member",
        ["calculation_result_id"],
        schema="evidence",
    )
    op.create_index(
        "ix_evidence_member_document_chunk_id",
        "evidence_member",
        ["document_chunk_id"],
        schema="evidence",
    )
    op.create_index(
        "ix_evidence_member_citation_locator_id",
        "evidence_member",
        ["citation_locator_id"],
        schema="evidence",
    )
    op.create_index(
        "ix_evidence_member_source_artifact_id",
        "evidence_member",
        ["source_artifact_id"],
        schema="evidence",
    )
    op.create_index(
        "ix_reconciliation_decision_accepted_fact_id",
        "reconciliation_decision",
        ["accepted_fact_id"],
        schema="market",
    )
    op.create_index(
        "ix_ai_model_execution_provider_id",
        "ai_model_execution",
        ["provider_id"],
        schema="ai_gateway",
    )
    op.create_index(
        "ix_ai_model_execution_model_id",
        "ai_model_execution",
        ["model_id"],
        schema="ai_gateway",
    )
    op.create_index(
        "ix_calculation_job_calculation_specification_id",
        "calculation_job",
        ["calculation_specification_id"],
        schema="calculation",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_calculation_job_calculation_specification_id",
        table_name="calculation_job",
        schema="calculation",
    )
    op.drop_index(
        "ix_ai_model_execution_model_id", table_name="ai_model_execution", schema="ai_gateway"
    )
    op.drop_index(
        "ix_ai_model_execution_provider_id", table_name="ai_model_execution", schema="ai_gateway"
    )
    op.drop_index(
        "ix_reconciliation_decision_accepted_fact_id",
        table_name="reconciliation_decision",
        schema="market",
    )
    op.drop_index(
        "ix_evidence_member_source_artifact_id", table_name="evidence_member", schema="evidence"
    )
    op.drop_index(
        "ix_evidence_member_citation_locator_id", table_name="evidence_member", schema="evidence"
    )
    op.drop_index(
        "ix_evidence_member_document_chunk_id", table_name="evidence_member", schema="evidence"
    )
    op.drop_index(
        "ix_evidence_member_calculation_result_id",
        table_name="evidence_member",
        schema="evidence",
    )
    op.drop_index(
        "ix_evidence_member_accepted_fact_id", table_name="evidence_member", schema="evidence"
    )
