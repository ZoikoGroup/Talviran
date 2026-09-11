"""Proves the week-7 schema's real invariants against live Postgres — not
just that the tables exist, but that the constraints DATA-002/EVID-001
actually depend on are enforced by the database, not just by convention.
"""

import datetime as dt
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.models import (
    CitationLocator,
    Document,
    DocumentChunk,
    EvidenceBundle,
    EvidenceMember,
)
from app.modules.market.models import Dataset, Source, SourceArtifact, SourceObservation
from app.modules.rights.models import RightsProfile


async def _seed_rights_profile(session: AsyncSession) -> RightsProfile:
    profile = RightsProfile(code=f"test.{uuid.uuid4().hex[:8]}", status="ACTIVE")
    session.add(profile)
    await session.flush()
    return profile


async def _seed_source_artifact(session: AsyncSession) -> SourceArtifact:
    source = Source(code=f"src-{uuid.uuid4().hex[:8]}", name="Test Source")
    session.add(source)
    await session.flush()

    dataset = Dataset(source_id=source.id, code="test-dataset", name="Test Dataset")
    session.add(dataset)
    await session.flush()

    artifact = SourceArtifact(
        dataset_id=dataset.id,
        sha256="a" * 64,
        storage_ref="local://test/artifact.bin",
        media_type="application/json",
        byte_length=123,
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    session.add(artifact)
    await session.flush()
    return artifact


async def test_source_observation_requires_rights_profile_id(db_session: AsyncSession) -> None:
    artifact = await _seed_source_artifact(db_session)

    observation = SourceObservation(
        source_artifact_id=artifact.id,
        rights_profile_id=None,
        subject_type="INSTRUMENT",
        metric_id="CLEAN_PRICE",
        semantic_observation_key=str(uuid.uuid4()),
        raw_value={"value": "100.5"},
        observed_at=dt.datetime.now(dt.UTC),
    )
    db_session.add(observation)

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_semantic_observation_key_is_unique_for_idempotent_writes(
    db_session: AsyncSession,
) -> None:
    artifact = await _seed_source_artifact(db_session)
    profile = await _seed_rights_profile(db_session)
    key = str(uuid.uuid4())

    def make_observation() -> SourceObservation:
        return SourceObservation(
            source_artifact_id=artifact.id,
            rights_profile_id=profile.id,
            subject_type="INSTRUMENT",
            metric_id="CLEAN_PRICE",
            semantic_observation_key=key,
            raw_value={"value": "100.5"},
            observed_at=dt.datetime.now(dt.UTC),
        )

    db_session.add(make_observation())
    await db_session.flush()

    db_session.add(make_observation())
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_evidence_bundle_chain_round_trips(db_session: AsyncSession) -> None:
    document = Document(title="UK DMO Gilt Formulae", media_type="application/pdf")
    db_session.add(document)
    await db_session.flush()

    chunk = DocumentChunk(document_id=document.id, chunk_index=0, text_content="Section 1...")
    db_session.add(chunk)
    await db_session.flush()

    locator = CitationLocator(
        document_chunk_id=chunk.id,
        locator_type="TEXT_OFFSET",
        locator_data={"start": 0, "end": 42},
    )
    db_session.add(locator)
    await db_session.flush()

    bundle = EvidenceBundle(
        purpose_type="FACTUAL_EXPLANATION",
        knowledge_time=dt.datetime.now(dt.UTC),
        status="READY",
    )
    db_session.add(bundle)
    await db_session.flush()

    member = EvidenceMember(
        evidence_bundle_id=bundle.id,
        kind="DOCUMENT_SPAN",
        document_chunk_id=chunk.id,
        citation_locator_id=locator.id,
    )
    db_session.add(member)
    await db_session.flush()
    await db_session.commit()

    fetched = (
        await db_session.execute(
            select(EvidenceMember).where(EvidenceMember.evidence_bundle_id == bundle.id)
        )
    ).scalar_one()
    assert fetched.kind == "DOCUMENT_SPAN"
    assert fetched.document_chunk_id == chunk.id
    assert fetched.accepted_fact_id is None
    assert fetched.calculation_result_id is None
