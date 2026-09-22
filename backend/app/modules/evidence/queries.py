"""Read-only evidence retrieval queries (EVID-001 §12) - mirrors market/
queries.py and calculation/queries.py's own separation of concerns: pure
reads here, rights/policy checks are the caller's job (evidence/service.py,
or whatever assembles an EvidenceBundle later), not baked into the query
layer itself.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.models import (
    QUALITY_FAILED,
    QUALITY_QUARANTINED,
    STATUS_DOCUMENT_VERSION_WITHDRAWN,
    DocumentChunk,
    DocumentVersion,
    ParsedDocumentVersion,
)


async def search_chunks_by_text(
    session: AsyncSession, *, query_text: str, limit: int = 10
) -> list[DocumentChunk]:
    """Lexical retrieval - EVID-001 §12.1's launch full-text-search
    implementation, ranked by ts_rank against the stored search_vector
    (migration 0024).

    Excludes withdrawn document versions and failed/quarantined parses -
    "withdrawn/quarantined docs excluded from normal retrieval" (§12.2).
    Superseded versions are NOT excluded here: they remain valid
    historical evidence, unlike withdrawn/quarantined content the
    platform has already marked unusable.
    """
    tsquery = func.plainto_tsquery("english", query_text)
    rank = func.ts_rank(DocumentChunk.search_vector, tsquery)
    stmt = (
        select(DocumentChunk)
        .join(
            ParsedDocumentVersion,
            ParsedDocumentVersion.id == DocumentChunk.parsed_document_version_id,
        )
        .join(DocumentVersion, DocumentVersion.id == ParsedDocumentVersion.document_version_id)
        .where(
            DocumentChunk.search_vector.op("@@")(tsquery),
            DocumentVersion.status != STATUS_DOCUMENT_VERSION_WITHDRAWN,
            ParsedDocumentVersion.extraction_quality.not_in([QUALITY_FAILED, QUALITY_QUARANTINED]),
        )
        .order_by(rank.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def search_chunks_by_vector(
    session: AsyncSession,
    *,
    query_embedding: list[float],
    limit: int = 10,
    max_distance: float | None = None,
) -> list[DocumentChunk]:
    """Semantic retrieval - EVID-001 §12.1's pgvector half, ranked by
    cosine distance (migration 59e91ab651d2). Takes an already-computed
    query embedding, not raw text - embedding a query is an external API
    call, which doesn't belong in a pure-read query function (see
    evidence/pipeline/embed.py's search_chunks_by_semantic_query for the
    orchestrating wrapper that does both).

    Only chunks with a non-null embedding can ever match - a chunk that
    hasn't been through the embedding pipeline yet is absent from semantic
    results, not an error. Same withdrawn/quarantined exclusion as
    search_chunks_by_text (§12.2).

    max_distance filters out weak nearest-neighbour matches - vector
    search always returns *a* closest chunk, even for a query with no
    real relationship to anything in the corpus (confirmed live: "hi"
    against the accrued-interest corpus lands at cosine distance ~0.52,
    while genuinely relevant queries land at ~0.23-0.33 - a real,
    measured gap, not a guessed number). None (the default) means no
    filtering, for callers that want raw nearest-neighbour results (e.g.
    a UI that shows a confidence score itself).
    """
    stmt = (
        select(DocumentChunk)
        .join(
            ParsedDocumentVersion,
            ParsedDocumentVersion.id == DocumentChunk.parsed_document_version_id,
        )
        .join(DocumentVersion, DocumentVersion.id == ParsedDocumentVersion.document_version_id)
        .where(
            DocumentChunk.embedding.is_not(None),
            DocumentVersion.status != STATUS_DOCUMENT_VERSION_WITHDRAWN,
            ParsedDocumentVersion.extraction_quality.not_in([QUALITY_FAILED, QUALITY_QUARANTINED]),
        )
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    if max_distance is not None:
        stmt = stmt.where(DocumentChunk.embedding.cosine_distance(query_embedding) <= max_distance)
    return list((await session.execute(stmt)).scalars().all())
