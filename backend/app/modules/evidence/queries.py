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
