"""EVID-001 E1 (source artefact acquisition) - fetches one real source
document, content-hashes it into a market.source_artifact (the same
SourceArtefact concept EVID-001 §3 names — not a new table; see evidence/
models.py's own docstring for why), and creates/reuses the Document/
DocumentVersion chain E0 built. Mirrors market/pipeline/curve_ingest.py's
rights-check-before-persist pattern exactly (evaluate_action(..., "store",
...) before anything is written).

EVID-001 §4: "HTTP 200 does not prove completeness" - minimum-size and
media-type are checked before anything is persisted, same doctrine as
market/connectors/base.py's Quarantined path for connector schema drift:
an unexpected small/wrong-type response (e.g. a bot-check HTML page)
must be rejected, never silently accepted as if it were the real document.

Real, computed content hashes: unlike scripts/ingest_dev_data.py's dev
fixtures (which use placeholder hashes like "1" * 64 since real hashing
was never exercised end-to-end before), this is the first pipeline in the
codebase to sha256 genuinely acquired bytes.
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.models import (
    STAGE_ACQUIRE,
    STATUS_JOB_DONE,
    Document,
    DocumentProcessingJob,
    DocumentVersion,
)
from app.modules.market import artifact_storage
from app.modules.market.models import Dataset, Source, SourceArtifact
from app.modules.rights.engine import RightsDecision, evaluate_action

# A genuine PDF/document response is never this small - catches a
# bot-check redirect page or a truncated download before it's persisted.
_MIN_BYTE_LENGTH = 1024


@dataclass(frozen=True)
class AcquisitionRejected:
    reason: str


@dataclass(frozen=True)
class AcquisitionResult:
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    source_artifact_id: uuid.UUID
    was_new_artifact: bool


async def _get_or_create_source(session: AsyncSession, *, code: str, name: str) -> Source:
    source = (
        await session.execute(select(Source).where(Source.code == code))
    ).scalar_one_or_none()
    if source is None:
        source = Source(code=code, name=name)
        session.add(source)
        await session.flush()
    return source


async def _get_or_create_dataset(
    session: AsyncSession, *, source_id: uuid.UUID, code: str, name: str
) -> Dataset:
    dataset = (
        await session.execute(
            select(Dataset).where(Dataset.source_id == source_id, Dataset.code == code)
        )
    ).scalar_one_or_none()
    if dataset is None:
        dataset = Dataset(source_id=source_id, code=code, name=name)
        session.add(dataset)
        await session.flush()
    return dataset


async def acquire_document(
    session: AsyncSession,
    *,
    content: bytes,
    media_type: str,
    document_title: str,
    source_code: str,
    source_name: str,
    dataset_code: str,
    dataset_name: str,
    rights_profile_id: uuid.UUID,
    published_at: dt.datetime | None,
    retrieved_at: dt.datetime,
) -> AcquisitionResult | AcquisitionRejected:
    """Idempotent on (dataset, content-hash) - re-acquiring byte-identical
    content returns the existing DocumentVersion rather than creating a
    duplicate (EVID-001 §4: "idempotent on source-identity+content-hash/
    version semantics"). Different bytes under the same document title
    create a genuinely new DocumentVersion, never overwrite the old one.
    """
    if len(content) < _MIN_BYTE_LENGTH:
        return AcquisitionRejected(
            reason=(
                f"acquired content is only {len(content)} bytes - below the "
                f"{_MIN_BYTE_LENGTH}-byte minimum, likely an error page, not the document"
            )
        )
    if not media_type.startswith("application/pdf"):
        return AcquisitionRejected(reason=f"unexpected media_type {media_type!r}")

    rights_decision = await evaluate_action(session, "store", rights_profile_id)
    if rights_decision != RightsDecision.ALLOW:
        return AcquisitionRejected(
            reason=f"rights check denied 'store' for profile {rights_profile_id}"
        )

    source = await _get_or_create_source(session, code=source_code, name=source_name)
    dataset = await _get_or_create_dataset(
        session, source_id=source.id, code=dataset_code, name=dataset_name
    )

    sha256 = hashlib.sha256(content).hexdigest()
    existing_artifact = (
        await session.execute(
            select(SourceArtifact).where(
                SourceArtifact.dataset_id == dataset.id, SourceArtifact.sha256 == sha256
            )
        )
    ).scalar_one_or_none()

    if existing_artifact is not None:
        existing_version = (
            await session.execute(
                select(DocumentVersion).where(
                    DocumentVersion.source_artifact_id == existing_artifact.id
                )
            )
        ).scalar_one_or_none()
        if existing_version is not None:
            return AcquisitionResult(
                document_id=existing_version.document_id,
                document_version_id=existing_version.id,
                source_artifact_id=existing_artifact.id,
                was_new_artifact=False,
            )
        artifact = existing_artifact
        was_new_artifact = False
    else:
        storage_ref = artifact_storage.save(sha256, content)
        artifact = SourceArtifact(
            dataset_id=dataset.id,
            sha256=sha256,
            storage_ref=storage_ref,
            media_type=media_type,
            byte_length=len(content),
            retrieved_at=retrieved_at,
            published_at=published_at,
        )
        session.add(artifact)
        await session.flush()
        was_new_artifact = True

    document = (
        await session.execute(
            select(Document).where(
                Document.source_id == source.id, Document.title == document_title
            )
        )
    ).scalar_one_or_none()
    if document is None:
        document = Document(source_id=source.id, title=document_title, media_type=media_type)
        session.add(document)
        await session.flush()

    version = DocumentVersion(
        document_id=document.id,
        source_artifact_id=artifact.id,
        rights_profile_id=rights_profile_id,
        retrieved_at=retrieved_at,
        published_at=published_at,
    )
    session.add(version)
    await session.flush()

    session.add(
        DocumentProcessingJob(document_id=document.id, stage=STAGE_ACQUIRE, status=STATUS_JOB_DONE)
    )
    await session.flush()

    return AcquisitionResult(
        document_id=document.id,
        document_version_id=version.id,
        source_artifact_id=artifact.id,
        was_new_artifact=was_new_artifact,
    )
