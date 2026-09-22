"""evidence/pipeline/embed.py and queries.py::search_chunks_by_vector
(EVID-001 E3, semantic half) against real Postgres/pgvector.

embed_chunk's success path is tested against a fake Gemini transport
(httpx.MockTransport, same pattern as conftest.py's FakeSupabaseAuth) -
the real API was already verified live (2026-09-21, see gemini_client.py's
docstring and scripts/embed_methodology_doc.py's real run) before this was
written; the automated suite shouldn't depend on network/cost/quota for
every run. Ranking tests use synthetic vectors with known geometric
relationships, not real embeddings - this tests the SQL/ranking mechanism,
which doesn't care what an embedding means semantically.
"""

import datetime as dt
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.embeddings.gemini_client import EMBEDDING_DIMENSIONS
from app.modules.evidence.models import (
    QUALITY_FAILED,
    QUALITY_PASS,
    QUALITY_QUARANTINED,
    STATUS_DOCUMENT_VERSION_WITHDRAWN,
    Document,
    DocumentChunk,
    DocumentVersion,
    ParsedDocumentVersion,
)
from app.modules.evidence.pipeline.embed import EmbedRejected, EmbedResult, embed_chunk
from app.modules.evidence.queries import search_chunks_by_vector
from app.modules.market.models import Dataset, Source, SourceArtifact
from app.modules.rights.models import RightsGrant, RightsProfile

_FAKE_VECTOR = [0.01] * EMBEDDING_DIMENSIONS


async def _fake_gemini_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"embedding": {"values": _FAKE_VECTOR}})


def _fake_gemini_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(_fake_gemini_handler))


async def _seed_chunk(
    db_session: AsyncSession,
    *,
    embedding: list[float] | None = None,
    document_status: str = "CURRENT",
    extraction_quality: str = QUALITY_PASS,
    rights_actions: list[str] | None = None,
) -> tuple[DocumentChunk, uuid.UUID]:
    source = Source(code=f"test-source-{uuid.uuid4().hex[:8]}", name="Test Source")
    db_session.add(source)
    await db_session.flush()
    dataset = Dataset(source_id=source.id, code="methodology-docs", name="Methodology Docs")
    db_session.add(dataset)
    await db_session.flush()
    artifact = SourceArtifact(
        dataset_id=dataset.id, sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        storage_ref="test://fixture", media_type="application/pdf", byte_length=1,
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    db_session.add(artifact)
    await db_session.flush()

    profile = RightsProfile(code=f"test-profile-{uuid.uuid4().hex[:8]}", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    for action in rights_actions or ["embed"]:
        db_session.add(
            RightsGrant(rights_profile_id=profile.id, action=action, permission_state="ALLOW")
        )
    await db_session.flush()

    document = Document(title="Test Doc", media_type="application/pdf")
    db_session.add(document)
    await db_session.flush()
    version = DocumentVersion(
        document_id=document.id, source_artifact_id=artifact.id, rights_profile_id=profile.id,
        status=document_status, retrieved_at=dt.datetime.now(dt.UTC),
    )
    db_session.add(version)
    await db_session.flush()
    parsed = ParsedDocumentVersion(
        document_version_id=version.id, parser_name="test", parser_version="1",
        parse_started_at=dt.datetime.now(dt.UTC), extraction_quality=extraction_quality,
    )
    db_session.add(parsed)
    await db_session.flush()
    chunk = DocumentChunk(
        parsed_document_version_id=parsed.id, chunker_version="1", ordinal=0,
        text_content="Some evidence text.",
        content_hash=uuid.uuid4().hex + uuid.uuid4().hex, embedding=embedding,
    )
    db_session.add(chunk)
    await db_session.flush()
    return chunk, profile.id


async def test_embed_chunk_stores_a_real_shaped_vector(db_session: AsyncSession) -> None:
    chunk, _ = await _seed_chunk(db_session)
    await db_session.commit()

    async with _fake_gemini_client() as http:
        result = await embed_chunk(
            db_session, chunk_id=chunk.id, http=http, api_key="fake-key"
        )
    assert isinstance(result, EmbedResult)
    await db_session.commit()

    reloaded = await db_session.get(DocumentChunk, chunk.id)
    assert reloaded is not None
    assert reloaded.embedding is not None
    assert len(reloaded.embedding) == EMBEDDING_DIMENSIONS


async def test_embed_chunk_is_idempotent(db_session: AsyncSession) -> None:
    chunk, _ = await _seed_chunk(db_session, embedding=_FAKE_VECTOR)
    await db_session.commit()

    async def _should_not_be_called(request: httpx.Request) -> httpx.Response:
        raise AssertionError("embed_text should not be called for an already-embedded chunk")

    async with httpx.AsyncClient(transport=httpx.MockTransport(_should_not_be_called)) as http:
        result = await embed_chunk(db_session, chunk_id=chunk.id, http=http, api_key="fake-key")
    assert isinstance(result, EmbedResult)


async def test_embed_chunk_without_embed_rights_is_rejected(db_session: AsyncSession) -> None:
    chunk, _ = await _seed_chunk(db_session, rights_actions=["display"])
    await db_session.commit()

    async with _fake_gemini_client() as http:
        result = await embed_chunk(db_session, chunk_id=chunk.id, http=http, api_key="fake-key")
    assert isinstance(result, EmbedRejected)


async def test_search_ranks_the_closer_vector_first(db_session: AsyncSession) -> None:
    query = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
    close = [0.99] + [0.01] * (EMBEDDING_DIMENSIONS - 1)
    far = [0.0] * (EMBEDDING_DIMENSIONS - 1) + [1.0]

    close_chunk, _ = await _seed_chunk(db_session, embedding=close)
    far_chunk, _ = await _seed_chunk(db_session, embedding=far)
    await db_session.commit()

    results = await search_chunks_by_vector(db_session, query_embedding=query, limit=10)

    ids = [r.id for r in results]
    assert ids.index(close_chunk.id) < ids.index(far_chunk.id)


async def test_search_max_distance_filters_out_weak_matches(db_session: AsyncSession) -> None:
    """The mechanism behind evidence/service.py's _MAX_SEMANTIC_MATCH_
    DISTANCE cutoff (a real bug found live: "hi" returned the nearest
    chunk regardless of relevance, since nearest-neighbour search always
    returns *something*). Orthogonal vectors have cosine distance 1.0;
    max_distance=0.5 must exclude one and keep the near-identical other.
    """
    query = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
    close = [0.99] + [0.01] * (EMBEDDING_DIMENSIONS - 1)
    orthogonal = [0.0, 1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 2)

    close_chunk, _ = await _seed_chunk(db_session, embedding=close)
    await _seed_chunk(db_session, embedding=orthogonal)
    await db_session.commit()

    results = await search_chunks_by_vector(
        db_session, query_embedding=query, limit=10, max_distance=0.5
    )

    assert [r.id for r in results] == [close_chunk.id]


async def test_search_excludes_chunks_without_an_embedding(db_session: AsyncSession) -> None:
    await _seed_chunk(db_session, embedding=None)
    await db_session.commit()

    results = await search_chunks_by_vector(
        db_session, query_embedding=[0.1] * EMBEDDING_DIMENSIONS
    )

    assert results == []


async def test_search_excludes_withdrawn_and_quarantined(db_session: AsyncSession) -> None:
    await _seed_chunk(
        db_session, embedding=_FAKE_VECTOR, document_status=STATUS_DOCUMENT_VERSION_WITHDRAWN
    )
    await _seed_chunk(
        db_session, embedding=_FAKE_VECTOR, extraction_quality=QUALITY_QUARANTINED
    )
    await _seed_chunk(db_session, embedding=_FAKE_VECTOR, extraction_quality=QUALITY_FAILED)
    await db_session.commit()

    results = await search_chunks_by_vector(
        db_session, query_embedding=_FAKE_VECTOR, limit=10
    )

    assert results == []
