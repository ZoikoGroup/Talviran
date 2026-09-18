"""EVID-001 E0 (core evidence object model): proves the new
document_version/parsed_document_version/document_chunk chain actually
round-trips against real Postgres, and that the identity-key-separation
constraints the spec requires (§25.1 - rights_profile_id non-null,
document_chunk pointing at a parsed version rather than the document
directly) are enforced by the schema, not just documented in a comment.
"""

import datetime as dt
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.models import (
    QUALITY_PASS,
    STAGE_ACQUIRE,
    STATUS_JOB_PENDING,
    Document,
    DocumentChunk,
    DocumentProcessingJob,
    DocumentVersion,
    ParsedDocumentVersion,
)
from app.modules.market.models import Dataset, Source, SourceArtifact
from app.modules.rights.models import RightsProfile


async def _seed_source_artifact(db_session: AsyncSession) -> SourceArtifact:
    source = Source(code=f"test-source-{uuid.uuid4().hex[:8]}", name="Test Source")
    db_session.add(source)
    await db_session.flush()
    dataset = Dataset(source_id=source.id, code="methodology-docs", name="Methodology Docs")
    db_session.add(dataset)
    await db_session.flush()
    artifact = SourceArtifact(
        dataset_id=dataset.id, sha256="a" * 64, storage_ref="s3://test/doc.pdf",
        media_type="application/pdf", byte_length=1024,
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    db_session.add(artifact)
    await db_session.flush()
    return artifact


async def _seed_rights_profile(db_session: AsyncSession) -> RightsProfile:
    profile = RightsProfile(code=f"test-profile-{uuid.uuid4().hex[:8]}", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    return profile


async def test_document_version_requires_a_rights_profile(db_session: AsyncSession) -> None:
    document = Document(title="Test Methodology Doc", media_type="application/pdf")
    db_session.add(document)
    await db_session.flush()
    artifact = await _seed_source_artifact(db_session)

    db_session.add(
        DocumentVersion(
            document_id=document.id,
            source_artifact_id=artifact.id,
            rights_profile_id=None,  # deliberately invalid - proves the NOT NULL constraint
            retrieved_at=dt.datetime.now(dt.UTC),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_full_chain_round_trips(db_session: AsyncSession) -> None:
    document = Document(title="DMO Gilt Formulae", media_type="application/pdf")
    db_session.add(document)
    await db_session.flush()

    artifact = await _seed_source_artifact(db_session)
    profile = await _seed_rights_profile(db_session)

    version = DocumentVersion(
        document_id=document.id,
        source_artifact_id=artifact.id,
        rights_profile_id=profile.id,
        version_label="4th ed., 18 Dec 2024",
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    db_session.add(version)
    await db_session.flush()

    parsed = ParsedDocumentVersion(
        document_version_id=version.id,
        parser_name="pdfminer",
        parser_version="1.0.0",
        parse_started_at=dt.datetime.now(dt.UTC),
        extraction_quality=QUALITY_PASS,
    )
    db_session.add(parsed)
    await db_session.flush()
    # JSONB list defaults actually apply, not left NULL.
    assert parsed.language_codes == []
    assert parsed.warnings == []

    chunk = DocumentChunk(
        parsed_document_version_id=parsed.id,
        chunker_version="1.0.0",
        ordinal=0,
        text_content="Accrued interest is calculated on an Actual/Actual basis...",
        content_hash="b" * 64,
    )
    db_session.add(chunk)
    await db_session.flush()

    job = DocumentProcessingJob(document_id=document.id, stage=STAGE_ACQUIRE)
    db_session.add(job)
    await db_session.flush()
    assert job.status == STATUS_JOB_PENDING

    await db_session.commit()

    reloaded_chunk = await db_session.get(DocumentChunk, chunk.id)
    assert reloaded_chunk is not None
    assert reloaded_chunk.parsed_document_version_id == parsed.id

    reloaded_version = await db_session.get(DocumentVersion, version.id)
    assert reloaded_version is not None
    assert reloaded_version.rights_profile_id == profile.id
    assert reloaded_version.source_artifact_id == artifact.id
