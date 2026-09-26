"""A real gap found live (2026-09-25, the 57-query test matrix): every
document-backed reply (accrued interest, GEMM obligations, primary
dealer, ex-dividend) was rejected by the AI Gateway with "evidence bundle
... has no renderable items", even though a real DOCUMENT_SPAN evidence
member existed - _resolve_bundle_items only ever rendered FACT/
CALCULATION members. These tests prove the fix: a DOCUMENT_SPAN-only
bundle is now a real, renderable evidence item, both at the evidence-read
layer and through the AI Gateway's own grounding path.
"""

import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_gateway.evidence_path import render_grounded_prompt
from app.modules.evidence.models import (
    QUALITY_PASS,
    CitationLocator,
    Document,
    DocumentChunk,
    DocumentVersion,
    EvidenceBundle,
    EvidenceMember,
    ParsedDocumentVersion,
)
from app.modules.evidence.service import get_evidence_bundle_items
from app.modules.market.models import Dataset, Source, SourceArtifact
from app.modules.rights.models import RightsGrant, RightsProfile


async def _seed_document_chunk(
    session: AsyncSession,
    *,
    title: str = "GEMM Guidebook (test)",
    text_content: str = "GEMMs must provide the DMO with written approval...",
    page_start: int | None = 6,
) -> DocumentChunk:
    profile = RightsProfile(code=f"test.doc.{uuid.uuid4().hex[:8]}", status="ACTIVE")
    session.add(profile)
    await session.flush()
    session.add(
        RightsGrant(rights_profile_id=profile.id, action="display", permission_state="ALLOW")
    )

    source = Source(code=f"test-source-{uuid.uuid4().hex[:8]}", name="Test Source")
    session.add(source)
    await session.flush()
    dataset = Dataset(source_id=source.id, code="methodology-docs", name="Methodology Docs")
    session.add(dataset)
    await session.flush()
    artifact = SourceArtifact(
        dataset_id=dataset.id, sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        storage_ref="test://fixture", media_type="application/pdf", byte_length=1,
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    session.add(artifact)
    await session.flush()

    document = Document(title=title, media_type="application/pdf")
    session.add(document)
    await session.flush()
    version = DocumentVersion(
        document_id=document.id, source_artifact_id=artifact.id,
        rights_profile_id=profile.id, retrieved_at=dt.datetime.now(dt.UTC),
    )
    session.add(version)
    await session.flush()
    parsed = ParsedDocumentVersion(
        document_version_id=version.id, parser_name="test", parser_version="1",
        parse_started_at=dt.datetime.now(dt.UTC), extraction_quality=QUALITY_PASS,
    )
    session.add(parsed)
    await session.flush()
    chunk = DocumentChunk(
        parsed_document_version_id=parsed.id, chunker_version="1", ordinal=0,
        page_start=page_start, text_content=text_content,
        content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
    )
    session.add(chunk)
    await session.flush()
    return chunk


async def _seed_document_span_bundle(session: AsyncSession, chunk: DocumentChunk) -> uuid.UUID:
    bundle = EvidenceBundle(
        purpose_type="FACTUAL_EXPLANATION", knowledge_time=dt.datetime.now(dt.UTC),
        status="ASSEMBLING",
    )
    session.add(bundle)
    await session.flush()
    locator = CitationLocator(
        document_chunk_id=chunk.id, locator_type="PAGE", locator_data={"page": chunk.page_start}
    )
    session.add(locator)
    await session.flush()
    session.add(
        EvidenceMember(
            evidence_bundle_id=bundle.id, kind="DOCUMENT_SPAN",
            document_chunk_id=chunk.id, citation_locator_id=locator.id,
        )
    )
    await session.commit()
    return bundle.id


async def test_document_span_member_is_now_a_renderable_evidence_item(
    db_session: AsyncSession,
) -> None:
    chunk = await _seed_document_chunk(db_session)
    bundle_id = await _seed_document_span_bundle(db_session, chunk)

    items = await get_evidence_bundle_items(db_session, bundle_id=bundle_id)

    assert items is not None
    assert len(items) == 1
    item = items[0]
    assert item.kind == "DOCUMENT_SPAN"
    assert item.document_title == "GEMM Guidebook (test), page 6"
    assert item.text == "GEMMs must provide the DMO with written approval..."


async def test_document_span_bundle_now_renders_a_real_grounded_prompt(
    db_session: AsyncSession,
) -> None:
    chunk = await _seed_document_chunk(
        db_session, title="GEMM Guidebook (test)",
        text_content="All GEMMs must be authorised by the FCA.",
    )
    bundle_id = await _seed_document_span_bundle(db_session, chunk)

    prompt = await render_grounded_prompt(
        db_session, bundle_id=bundle_id, instruction="what are the obligations of a GEMM"
    )

    assert prompt is not None, "a DOCUMENT_SPAN-only bundle must not be treated as empty"
    assert prompt.evidence_item_count == 1
    assert "GEMM Guidebook (test)" in prompt.text
    assert "All GEMMs must be authorised by the FCA." in prompt.text


async def test_document_chunk_with_no_page_omits_the_page_suffix(db_session: AsyncSession) -> None:
    chunk = await _seed_document_chunk(db_session, page_start=None)
    bundle_id = await _seed_document_span_bundle(db_session, chunk)

    items = await get_evidence_bundle_items(db_session, bundle_id=bundle_id)

    assert items is not None
    assert items[0].document_title == "GEMM Guidebook (test)"
