"""evidence/pipeline/parse.py (EVID-001 E2): proves real PDF text
extraction against the actual DMO methodology PDF (tests/fixtures/
dmo_yldconv.pdf - the exact bytes live-acquired from dmo.gov.uk via
scripts.ingest_methodology_doc, saved once so tests don't depend on
network), and the FAILED-quality path for genuinely unparseable content
(EVID-001 §8.3: FAILED means zero chunks, no semantic index admission).
"""

import datetime as dt
import hashlib
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.models import (
    QUALITY_FAILED,
    QUALITY_PASS,
    Document,
    DocumentChunk,
    DocumentVersion,
)
from app.modules.evidence.pipeline.parse import ParseRejected, ParseResult, parse_document_version
from app.modules.market import artifact_storage
from app.modules.market.models import Dataset, Source, SourceArtifact
from app.modules.rights.models import RightsGrant, RightsProfile

_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "dmo_yldconv.pdf"


async def _seed_document_version(db_session: AsyncSession, *, content: bytes) -> uuid.UUID:
    source = Source(code=f"test-source-{uuid.uuid4().hex[:8]}", name="Test Source")
    db_session.add(source)
    await db_session.flush()
    dataset = Dataset(source_id=source.id, code="methodology-docs", name="Methodology Docs")
    db_session.add(dataset)
    await db_session.flush()

    sha256 = hashlib.sha256(content).hexdigest()
    storage_ref = artifact_storage.save(sha256, content)
    artifact = SourceArtifact(
        dataset_id=dataset.id, sha256=sha256, storage_ref=storage_ref,
        media_type="application/pdf", byte_length=len(content),
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    db_session.add(artifact)
    await db_session.flush()

    profile = RightsProfile(code=f"test-profile-{uuid.uuid4().hex[:8]}", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    db_session.add(
        RightsGrant(rights_profile_id=profile.id, action="store", permission_state="ALLOW")
    )
    await db_session.flush()

    document = Document(title="Test Doc", media_type="application/pdf")
    db_session.add(document)
    await db_session.flush()
    version = DocumentVersion(
        document_id=document.id, source_artifact_id=artifact.id, rights_profile_id=profile.id,
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    db_session.add(version)
    await db_session.flush()
    return version.id


async def test_parsing_the_real_dmo_pdf_extracts_real_text(db_session: AsyncSession) -> None:
    content = _FIXTURE_PATH.read_bytes()
    document_version_id = await _seed_document_version(db_session, content=content)

    result = await parse_document_version(db_session, document_version_id=document_version_id)
    assert isinstance(result, ParseResult)
    await db_session.commit()

    assert result.extraction_quality == QUALITY_PASS
    assert result.chunk_count == 5
    assert result.warnings == []

    chunks = (
        (
            await db_session.execute(
                DocumentChunk.__table__.select()
                .where(
                    DocumentChunk.parsed_document_version_id
                    == result.parsed_document_version_id
                )
                .order_by(DocumentChunk.ordinal)
            )
        )
        .mappings()
        .all()
    )
    assert len(chunks) == 5
    assert chunks[0]["page_start"] == 1
    assert chunks[0]["page_end"] == 1
    assert chunks[0]["chunker_version"] == "page-v1"
    # Real, specific content from the actual DMO worked examples - proves
    # this is genuine extraction, not an empty/garbled result.
    assert "nominal redemption yields" in chunks[0]["text_content"]
    assert len(chunks[0]["content_hash"]) == 64


async def test_unparseable_content_is_failed_with_zero_chunks(db_session: AsyncSession) -> None:
    document_version_id = await _seed_document_version(
        db_session, content=b"not a real pdf" + b"\x00" * 2000
    )

    result = await parse_document_version(db_session, document_version_id=document_version_id)
    assert isinstance(result, ParseResult)
    await db_session.commit()

    assert result.extraction_quality == QUALITY_FAILED
    assert result.chunk_count == 0

    chunks = (
        await db_session.execute(
            DocumentChunk.__table__.select().where(
                DocumentChunk.parsed_document_version_id == result.parsed_document_version_id
            )
        )
    ).all()
    assert chunks == []


async def test_unknown_document_version_is_rejected(db_session: AsyncSession) -> None:
    result = await parse_document_version(db_session, document_version_id=uuid.uuid4())
    assert isinstance(result, ParseRejected)


async def test_reparsing_with_the_same_parser_is_idempotent(db_session: AsyncSession) -> None:
    """A real bug found live (2026-09-22): re-running parse_document_version
    against an already-parsed version created a second ParsedDocumentVersion
    and doubled the chunk count, with no audit trail to explain why. Same
    parser_name+parser_version must reuse the existing row.
    """
    content = _FIXTURE_PATH.read_bytes()
    document_version_id = await _seed_document_version(db_session, content=content)

    first = await parse_document_version(db_session, document_version_id=document_version_id)
    assert isinstance(first, ParseResult)
    await db_session.commit()

    second = await parse_document_version(db_session, document_version_id=document_version_id)
    assert isinstance(second, ParseResult)
    await db_session.commit()

    assert second.parsed_document_version_id == first.parsed_document_version_id
    assert second.chunk_count == first.chunk_count

    all_chunks = (
        await db_session.execute(
            DocumentChunk.__table__.select().where(
                DocumentChunk.parsed_document_version_id == first.parsed_document_version_id
            )
        )
    ).all()
    assert len(all_chunks) == 5
