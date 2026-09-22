"""0025 document chunk embedding

EVID-001 E3 (retrieval), semantic half: enables pgvector and adds
document_chunk.embedding, a vector(768) column - the counterpart to
migration 00215e4bf234's search_vector (lexical/FTS half). §12.1's launch
retrieval stack is explicit: "PostgreSQL full-text search plus pgvector
for the licence-constrained corpus... A separate vector store is
deferred" - this is that pgvector column, not a new database.

768 dimensions, not Gemini's `gemini-embedding-001` default of 3072:
requested via the API's own `outputDimensionality` parameter (a real,
documented truncation feature - confirmed live against the actual API
before choosing this number, not guessed), chosen because pgvector's HNSW
index has practical performance/memory tradeoffs well past a few thousand
dimensions, and 768 is a well-supported, conventional embedding size.

embedding is nullable: unlike search_vector (a STORED generated column,
computed synchronously for free), an embedding requires an external API
call - chunks are embedded by a separate pipeline step
(evidence/pipeline/embed.py), not automatically at insert time. A chunk
with embedding IS NULL simply isn't part of semantic search results yet,
same "real if present, absent if not run yet" pattern as every other
async/job-fed column in this codebase (e.g. calculation_job's own
pending-until-claimed rows).

HNSW (not IVFFlat): no training/list-count tuning needed, and this
project's own doctrine is "prove it in Postgres first" at a scale where
build time doesn't matter yet - HNSW is pgvector's own recommended
default for that situation. Cosine distance (vector_cosine_ops): Gemini's
own embedding documentation recommends cosine similarity for its
embedding models.

Revision ID: 59e91ab651d2
Revises: 00215e4bf234
Create Date: 2026-09-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "59e91ab651d2"
down_revision: str | Sequence[str] | None = "00215e4bf234"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE evidence.document_chunk ADD COLUMN embedding vector(768)")
    op.execute(
        """
        CREATE INDEX ix_evidence_document_chunk_embedding
        ON evidence.document_chunk
        USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX evidence.ix_evidence_document_chunk_embedding")
    op.execute("ALTER TABLE evidence.document_chunk DROP COLUMN embedding")
    # Deliberately does not DROP EXTENSION vector - another migration or a
    # concurrently-added table may depend on it; extension lifecycle is
    # managed at the database level, not tied to one column's migration.
