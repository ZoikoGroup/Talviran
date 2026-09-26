"""evidence/queries.py (EVID-001 E3, lexical half): proves full-text
search against real Postgres - relevant matches rank first, and
withdrawn/quarantined evidence is excluded from normal retrieval (§12.2),
not just filtered by convention in a caller that might forget to.
"""

import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

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
from app.modules.evidence.queries import search_chunks_by_text
from app.modules.market.models import Dataset, Source, SourceArtifact
from app.modules.rights.models import RightsProfile


async def _seed_chunk(
    db_session: AsyncSession,
    *,
    text_content: str,
    document_status: str = "CURRENT",
    extraction_quality: str = QUALITY_PASS,
) -> DocumentChunk:
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
        text_content=text_content, content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
    )
    db_session.add(chunk)
    await db_session.flush()
    return chunk


async def test_search_finds_the_relevant_chunk_not_the_unrelated_one(
    db_session: AsyncSession,
) -> None:
    relevant = await _seed_chunk(
        db_session,
        text_content="Accrued interest is calculated using the Actual/Actual (ICMA) "
        "day count convention for conventional gilts.",
    )
    await _seed_chunk(
        db_session,
        text_content="The gross redemption yield is computed via Newton-Raphson "
        "numerical iteration against a bounded bracket.",
    )
    await db_session.commit()

    results = await search_chunks_by_text(db_session, query_text="accrued interest day count")

    assert len(results) == 1
    assert results[0].id == relevant.id


async def test_search_excludes_withdrawn_document_versions(db_session: AsyncSession) -> None:
    await _seed_chunk(
        db_session,
        text_content="Accrued interest under a withdrawn methodology revision.",
        document_status=STATUS_DOCUMENT_VERSION_WITHDRAWN,
    )
    await db_session.commit()

    results = await search_chunks_by_text(db_session, query_text="accrued interest")

    assert results == []


async def test_search_excludes_quarantined_and_failed_parses(db_session: AsyncSession) -> None:
    await _seed_chunk(
        db_session,
        text_content="Accrued interest text from a quarantined parse.",
        extraction_quality=QUALITY_QUARANTINED,
    )
    await _seed_chunk(
        db_session,
        text_content="Accrued interest text from a failed parse.",
        extraction_quality=QUALITY_FAILED,
    )
    await db_session.commit()

    results = await search_chunks_by_text(db_session, query_text="accrued interest")

    assert results == []


async def test_search_respects_the_limit(db_session: AsyncSession) -> None:
    for i in range(5):
        await _seed_chunk(db_session, text_content=f"Accrued interest example number {i}.")
    await db_session.commit()

    results = await search_chunks_by_text(db_session, query_text="accrued interest", limit=2)

    assert len(results) == 2


async def test_min_rank_excludes_a_weak_incidental_match(db_session: AsyncSession) -> None:
    """A real gap found live: "what's your name" reduces (after English
    stopword removal) to just "name", which then matched ANY chunk
    containing that one common word - here, a form field, not a real
    answer to the question. Without min_rank this still "matches"
    (weakly); with the calibrated floor it must not.
    """
    await _seed_chunk(
        db_session,
        text_content="Name of firm: ___________ Address: ___________ Date of application: ___",
    )
    await db_session.commit()

    unfiltered = await search_chunks_by_text(db_session, query_text="what's your name")
    assert len(unfiltered) == 1, "sanity check: this really is a weak-but-real lexical match"

    filtered = await search_chunks_by_text(
        db_session, query_text="what's your name", min_rank=0.15
    )
    assert filtered == []


async def test_min_rank_still_returns_a_strong_genuine_match(db_session: AsyncSession) -> None:
    relevant = await _seed_chunk(
        db_session,
        text_content="Accrued interest is calculated using the Actual/Actual (ICMA) "
        "day count convention for conventional gilts.",
    )
    await db_session.commit()

    results = await search_chunks_by_text(
        db_session, query_text="accrued interest day count", min_rank=0.15
    )

    assert len(results) == 1
    assert results[0].id == relevant.id
