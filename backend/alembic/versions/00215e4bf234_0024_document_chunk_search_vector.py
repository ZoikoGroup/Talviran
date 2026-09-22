"""0024 document chunk search vector

EVID-001 E3 (retrieval), lexical half: adds document_chunk.search_vector,
a STORED generated tsvector column over text_content, plus a GIN index -
this is the whole mechanism §12.1's "PostgreSQL full-text search" launch
implementation needs. Generated (not maintained in application code) so it
can never drift out of sync with text_content; STORED (not VIRTUAL) so the
GIN index has something durable to index.

Semantic (pgvector) search is a separate, later migration - it needs an
embedding provider decision this one doesn't (see evidence/models.py's
own docstring on the column).

document_chunk has real rows now (P4 E2 landed this week), but the
generated column computes from existing text_content on ALTER TABLE, so
no backfill step is needed - Postgres itself does it as part of adding
the column.

Revision ID: 00215e4bf234
Revises: 0023_merge_heads
Create Date: 2026-09-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "00215e4bf234"
down_revision: str | Sequence[str] | None = "0023_merge_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE evidence.document_chunk
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('english', text_content)) STORED
        """
    )
    op.execute(
        """
        CREATE INDEX ix_evidence_document_chunk_search_vector
        ON evidence.document_chunk
        USING gin (search_vector)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX evidence.ix_evidence_document_chunk_search_vector")
    op.execute("ALTER TABLE evidence.document_chunk DROP COLUMN search_vector")
