"""EVID-001 E3 (retrieval), semantic half: computes and stores a chunk's
embedding via Gemini, and orchestrates a semantic search query (embed the
query text, then rank by vector distance).

Gated on rights.evaluate_action(..., "embed", ...) - RIGHTS-001 treats
"embed" as its own independently-evaluated action, distinct from
"store"/"index"/"display": a document's rights profile might permit
lexical indexing but not sending its text to a third-party embedding API.
"""

import uuid
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.embeddings.gemini_client import embed_text
from app.modules.evidence.models import DocumentChunk, DocumentVersion, ParsedDocumentVersion
from app.modules.evidence.queries import search_chunks_by_vector
from app.modules.rights.engine import RightsDecision, evaluate_action


@dataclass(frozen=True)
class EmbedRejected:
    reason: str


@dataclass(frozen=True)
class EmbedResult:
    chunk_id: uuid.UUID


async def embed_chunk(
    session: AsyncSession, *, chunk_id: uuid.UUID, http: httpx.AsyncClient, api_key: str
) -> EmbedResult | EmbedRejected:
    """Idempotent: a chunk that already has an embedding is left alone,
    not re-embedded and not an error - same "already exists, return the
    existing result" pattern as evidence/pipeline/acquire.py's content-
    hash idempotency.
    """
    chunk = await session.get(DocumentChunk, chunk_id)
    if chunk is None:
        return EmbedRejected(reason=f"no document_chunk {chunk_id}")
    if chunk.embedding is not None:
        return EmbedResult(chunk_id=chunk.id)

    parsed = await session.get(ParsedDocumentVersion, chunk.parsed_document_version_id)
    version = await session.get(DocumentVersion, parsed.document_version_id) if parsed else None
    if version is None:
        return EmbedRejected(reason="parsed_document_version/document_version not found")

    rights_decision = await evaluate_action(session, "embed", version.rights_profile_id)
    if rights_decision is not RightsDecision.ALLOW:
        return EmbedRejected(
            reason=f"rights check denied 'embed' for profile {version.rights_profile_id}"
        )

    values = await embed_text(http, text=chunk.text_content, api_key=api_key)
    chunk.embedding = values
    await session.flush()
    return EmbedResult(chunk_id=chunk.id)


async def search_chunks_by_semantic_query(
    session: AsyncSession,
    *,
    query_text: str,
    http: httpx.AsyncClient,
    api_key: str,
    limit: int = 10,
    max_distance: float | None = None,
) -> list[DocumentChunk]:
    """Embeds query_text, then ranks already-embedded chunks by cosine
    distance to it - the orchestrating wrapper around queries.py's pure
    search_chunks_by_vector (which takes a precomputed embedding, since a
    pure-read query function shouldn't itself make an external API call).
    """
    query_embedding = await embed_text(http, text=query_text, api_key=api_key)
    return await search_chunks_by_vector(
        session, query_embedding=query_embedding, limit=limit, max_distance=max_distance
    )
