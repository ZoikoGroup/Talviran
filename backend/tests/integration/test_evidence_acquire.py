"""evidence/pipeline/acquire.py (EVID-001 E1): proves acquisition against
real Postgres - idempotency on content-hash, the rights-check-before-
persist gate, and the minimum-size/media-type rejection doctrine (§4:
"HTTP 200 does not prove completeness").
"""

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.models import Document, DocumentProcessingJob, DocumentVersion
from app.modules.evidence.pipeline.acquire import (
    AcquisitionRejected,
    AcquisitionResult,
    acquire_document,
)
from app.modules.rights.models import RightsGrant, RightsProfile

_REAL_PDF_CONTENT = b"%PDF-1.4\n" + b"x" * 2000  # over the 1024-byte minimum


async def _seed_rights_profile(
    db_session: AsyncSession, *, granted: bool = True
) -> uuid.UUID:
    profile = RightsProfile(code=f"test-doc-{uuid.uuid4().hex[:8]}", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    if granted:
        db_session.add(
            RightsGrant(rights_profile_id=profile.id, action="store", permission_state="ALLOW")
        )
        await db_session.flush()
    return profile.id


async def test_acquiring_a_new_document_creates_the_full_chain(
    db_session: AsyncSession,
) -> None:
    rights_profile_id = await _seed_rights_profile(db_session)

    result = await acquire_document(
        db_session,
        content=_REAL_PDF_CONTENT,
        media_type="application/pdf",
        document_title="Test Methodology Doc",
        source_code=f"test-source-{uuid.uuid4().hex[:8]}",
        source_name="Test Source",
        dataset_code="methodology-docs",
        dataset_name="Methodology Docs",
        rights_profile_id=rights_profile_id,
        published_at=None,
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    assert isinstance(result, AcquisitionResult)
    assert result.was_new_artifact is True
    await db_session.commit()

    document = await db_session.get(Document, result.document_id)
    version = await db_session.get(DocumentVersion, result.document_version_id)
    assert document is not None
    assert version is not None
    assert version.rights_profile_id == rights_profile_id
    assert version.source_artifact_id == result.source_artifact_id


async def test_reacquiring_identical_bytes_is_idempotent(db_session: AsyncSession) -> None:
    rights_profile_id = await _seed_rights_profile(db_session)
    source_code = f"test-source-{uuid.uuid4().hex[:8]}"
    retrieved_at = dt.datetime.now(dt.UTC)

    first = await acquire_document(
        db_session,
        content=_REAL_PDF_CONTENT,
        media_type="application/pdf",
        document_title="Test Methodology Doc",
        source_code=source_code,
        source_name="Test Source",
        dataset_code="methodology-docs",
        dataset_name="Methodology Docs",
        rights_profile_id=rights_profile_id,
        published_at=None,
        retrieved_at=retrieved_at,
    )
    await db_session.commit()
    assert isinstance(first, AcquisitionResult)

    second = await acquire_document(
        db_session,
        content=_REAL_PDF_CONTENT,
        media_type="application/pdf",
        document_title="Test Methodology Doc",
        source_code=source_code,
        source_name="Test Source",
        dataset_code="methodology-docs",
        dataset_name="Methodology Docs",
        rights_profile_id=rights_profile_id,
        published_at=None,
        retrieved_at=retrieved_at,
    )
    await db_session.commit()
    assert isinstance(second, AcquisitionResult)

    assert second.document_id == first.document_id
    assert second.document_version_id == first.document_version_id
    assert second.source_artifact_id == first.source_artifact_id
    assert second.was_new_artifact is False


async def test_too_small_a_response_is_rejected(db_session: AsyncSession) -> None:
    rights_profile_id = await _seed_rights_profile(db_session)

    result = await acquire_document(
        db_session,
        content=b"<html>bot check</html>",
        media_type="application/pdf",
        document_title="Should Not Persist",
        source_code=f"test-source-{uuid.uuid4().hex[:8]}",
        source_name="Test Source",
        dataset_code="methodology-docs",
        dataset_name="Methodology Docs",
        rights_profile_id=rights_profile_id,
        published_at=None,
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    assert isinstance(result, AcquisitionRejected)


async def test_without_store_rights_acquisition_is_rejected(db_session: AsyncSession) -> None:
    rights_profile_id = await _seed_rights_profile(db_session, granted=False)

    result = await acquire_document(
        db_session,
        content=_REAL_PDF_CONTENT,
        media_type="application/pdf",
        document_title="Should Not Persist",
        source_code=f"test-source-{uuid.uuid4().hex[:8]}",
        source_name="Test Source",
        dataset_code="methodology-docs",
        dataset_name="Methodology Docs",
        rights_profile_id=rights_profile_id,
        published_at=None,
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    assert isinstance(result, AcquisitionRejected)


async def test_successful_acquisition_records_a_processing_job(
    db_session: AsyncSession,
) -> None:
    rights_profile_id = await _seed_rights_profile(db_session)

    result = await acquire_document(
        db_session,
        content=_REAL_PDF_CONTENT,
        media_type="application/pdf",
        document_title="Test Methodology Doc",
        source_code=f"test-source-{uuid.uuid4().hex[:8]}",
        source_name="Test Source",
        dataset_code="methodology-docs",
        dataset_name="Methodology Docs",
        rights_profile_id=rights_profile_id,
        published_at=None,
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    assert isinstance(result, AcquisitionResult)
    await db_session.commit()

    job = (
        await db_session.execute(
            select(DocumentProcessingJob).where(
                DocumentProcessingJob.document_id == result.document_id
            )
        )
    ).scalar_one_or_none()
    assert job is not None
    assert job.stage == "ACQUIRE"
    assert job.status == "DONE"
