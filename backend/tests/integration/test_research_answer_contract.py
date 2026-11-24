"""G04 acceptance suite (REG-02 answer/evidence) - continues the labeled
suite started in test_research_identity_contract.py. Covers the exact
categories the UAT gap analysis names for REG-02: covered facts,
calculated results, exact source passage, mismatched citation/version,
unsupported claim, source injection and revoked rights.
"""

import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.models import EvidenceBundle, EvidenceMember
from app.modules.research.answer_contract import (
    AnswerBlock,
    BlockType,
    Claim,
    PublishedResponse,
    validate_before_render,
)
from app.modules.research.identity_contract import CapabilityState


async def _make_ready_bundle(
    db_session: AsyncSession, *, member_kind: str
) -> tuple[EvidenceBundle, EvidenceMember]:
    bundle = EvidenceBundle(
        purpose_type="RESEARCH_ANSWER", knowledge_time=dt.datetime.now(dt.UTC), status="READY"
    )
    db_session.add(bundle)
    await db_session.flush()
    member = EvidenceMember(evidence_bundle_id=bundle.id, kind=member_kind)
    db_session.add(member)
    await db_session.commit()
    return bundle, member


def _response(
    *, bundle_id: uuid.UUID, state: CapabilityState, claims: list[Claim]
) -> PublishedResponse:
    return PublishedResponse(
        answer_id=uuid.uuid4(),
        version=1,
        evidence_bundle_id=bundle_id,
        capability_state=state,
        blocks=[AnswerBlock(block_type=BlockType.TEXT, content={"text": "..."}, claims=claims)],
        published_at=dt.datetime.now(dt.UTC),
    )


async def test_covered_fact_claim_passes_validation(db_session: AsyncSession) -> None:
    bundle, member = await _make_ready_bundle(db_session, member_kind="FACT")
    response = _response(
        bundle_id=bundle.id,
        state=CapabilityState.AVAILABLE,
        claims=[Claim(text="the yield is 4.6%", evidence_member_id=member.id)],
    )
    result = await validate_before_render(db_session, response)
    assert result.ok, result.errors


async def test_calculated_result_claim_passes_validation(db_session: AsyncSession) -> None:
    bundle, member = await _make_ready_bundle(db_session, member_kind="CALCULATION")
    response = _response(
        bundle_id=bundle.id,
        state=CapabilityState.AVAILABLE,
        claims=[Claim(text="duration is 7.2 years", evidence_member_id=member.id)],
    )
    result = await validate_before_render(db_session, response)
    assert result.ok, result.errors


async def test_exact_source_passage_claim_passes_validation(db_session: AsyncSession) -> None:
    bundle, member = await _make_ready_bundle(db_session, member_kind="DOCUMENT_SPAN")
    response = _response(
        bundle_id=bundle.id,
        state=CapabilityState.AVAILABLE,
        claims=[Claim(text="per the filing's risk factors section", evidence_member_id=member.id)],
    )
    result = await validate_before_render(db_session, response)
    assert result.ok, result.errors


async def test_claim_referencing_evidence_from_a_different_bundle_fails(
    db_session: AsyncSession,
) -> None:
    bundle_a, _ = await _make_ready_bundle(db_session, member_kind="FACT")
    _bundle_b, member_b = await _make_ready_bundle(db_session, member_kind="FACT")

    response = _response(
        bundle_id=bundle_a.id,
        state=CapabilityState.AVAILABLE,
        claims=[Claim(text="mismatched citation", evidence_member_id=member_b.id)],
    )
    result = await validate_before_render(db_session, response)
    assert not result.ok
    assert any("not a member of bundle" in e for e in result.errors)


async def test_claim_referencing_a_nonexistent_evidence_member_fails(
    db_session: AsyncSession,
) -> None:
    bundle, _member = await _make_ready_bundle(db_session, member_kind="FACT")
    response = _response(
        bundle_id=bundle.id,
        state=CapabilityState.AVAILABLE,
        claims=[Claim(text="source injection attempt", evidence_member_id=uuid.uuid4())],
    )
    result = await validate_before_render(db_session, response)
    assert not result.ok
    assert any("not a member of bundle" in e for e in result.errors)


async def test_unsupported_capability_with_nonempty_claims_fails(
    db_session: AsyncSession,
) -> None:
    bundle, member = await _make_ready_bundle(db_session, member_kind="FACT")
    response = _response(
        bundle_id=bundle.id,
        state=CapabilityState.UNSUPPORTED,
        claims=[Claim(text="should not be rendered", evidence_member_id=member.id)],
    )
    result = await validate_before_render(db_session, response)
    assert not result.ok
    assert any("must not render" in e for e in result.errors)


async def test_unsupported_capability_with_no_claims_passes(db_session: AsyncSession) -> None:
    bundle, _member = await _make_ready_bundle(db_session, member_kind="FACT")
    response = _response(bundle_id=bundle.id, state=CapabilityState.UNSUPPORTED, claims=[])
    result = await validate_before_render(db_session, response)
    assert result.ok, result.errors


async def test_bundle_not_ready_fails_closed(db_session: AsyncSession) -> None:
    """Stands in for "revoked rights": a bundle that isn't READY (revoked,
    still assembling, or any other non-ready status) must never be
    published from, regardless of what its claims look like."""
    bundle = EvidenceBundle(
        purpose_type="RESEARCH_ANSWER", knowledge_time=dt.datetime.now(dt.UTC), status="ASSEMBLING"
    )
    db_session.add(bundle)
    await db_session.commit()

    response = _response(bundle_id=bundle.id, state=CapabilityState.AVAILABLE, claims=[])
    result = await validate_before_render(db_session, response)
    assert not result.ok
    assert any("not READY" in e for e in result.errors)


async def test_unknown_evidence_bundle_fails_closed(db_session: AsyncSession) -> None:
    response = _response(bundle_id=uuid.uuid4(), state=CapabilityState.AVAILABLE, claims=[])
    result = await validate_before_render(db_session, response)
    assert not result.ok
    assert any("does not exist" in e for e in result.errors)
