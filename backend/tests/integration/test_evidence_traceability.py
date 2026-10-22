"""P2 (evidence-transparency roadmap item #5): proves each displayed
evidence item now carries all four things the acceptance test names -
source, market-effective time, ingestion/knowledge time, and permitted
use - not just a bare value. Previously, source and permitted-use were
missing entirely, and CALCULATION items conflated as_of (market-effective
date) with knowledge time; this fixes both gaps.
"""

import datetime as dt
import uuid

from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import (
    CalculationInput,
    CalculationResult,
    CalculationSpecification,
)
from app.modules.evidence.models import EvidenceBundle, EvidenceMember
from app.modules.evidence.service import get_evidence_bundle_items
from app.modules.market.models import (
    AcceptedFact,
    Dataset,
    FactObservationLink,
    Source,
    SourceArtifact,
    SourceObservation,
)
from app.modules.rights.models import RightsGrant, RightsProfile

_VALID_RANGE: Range[dt.datetime] = Range(
    lower=dt.datetime(2026, 9, 24, tzinfo=dt.UTC),
    upper=dt.datetime(2026, 9, 25, tzinfo=dt.UTC),
    bounds="[)",
)
_KNOWLEDGE_TIME = dt.datetime(2026, 9, 25, 9, 47, tzinfo=dt.UTC)


async def _seed_source_chain(
    session: AsyncSession, *, source_name: str, rights_actions: dict[str, str]
) -> tuple[SourceArtifact, uuid.UUID]:
    profile = RightsProfile(code=f"test.trace.{uuid.uuid4().hex[:8]}", status="ACTIVE")
    session.add(profile)
    await session.flush()
    for action, state in rights_actions.items():
        session.add(
            RightsGrant(rights_profile_id=profile.id, action=action, permission_state=state)
        )
    await session.flush()

    source = Source(code=f"test-src-{uuid.uuid4().hex[:8]}", name=source_name)
    session.add(source)
    await session.flush()
    dataset = Dataset(source_id=source.id, code="test-dataset", name="Test Dataset")
    session.add(dataset)
    await session.flush()
    artifact = SourceArtifact(
        dataset_id=dataset.id, sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        storage_ref="test://fixture", media_type="application/json", byte_length=1,
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    session.add(artifact)
    await session.flush()
    return artifact, profile.id


async def _seed_fact_with_observation(
    session: AsyncSession, *, source_name: str, rights_actions: dict[str, str]
) -> AcceptedFact:
    artifact, rights_profile_id = await _seed_source_chain(
        session, source_name=source_name, rights_actions=rights_actions
    )
    fact = AcceptedFact(
        subject_type="TEST_SUBJECT", subject_id=uuid.uuid4(), metric_id="TEST_METRIC",
        valid_range=_VALID_RANGE,
        knowledge_range=Range(lower=_KNOWLEDGE_TIME, upper=None, bounds="[)"),
        value={"v": "1"}, status="ACTIVE",
    )
    session.add(fact)
    await session.flush()

    observation = SourceObservation(
        source_artifact_id=artifact.id, rights_profile_id=rights_profile_id,
        subject_type="TEST_SUBJECT", subject_id=fact.subject_id, metric_id="TEST_METRIC",
        semantic_observation_key=uuid.uuid4().hex, raw_value={"v": "1"},
        valid_from=dt.date(2026, 9, 24), observed_at=_KNOWLEDGE_TIME,
    )
    session.add(observation)
    await session.flush()
    session.add(
        FactObservationLink(
            accepted_fact_id=fact.id, source_observation_id=observation.id, role="PRIMARY"
        )
    )
    await session.flush()
    return fact


async def _seed_bundle_for_fact(session: AsyncSession, fact: AcceptedFact) -> uuid.UUID:
    bundle = EvidenceBundle(
        purpose_type="FACTUAL_EXPLANATION", knowledge_time=dt.datetime.now(dt.UTC),
        status="ASSEMBLING",
    )
    session.add(bundle)
    await session.flush()
    session.add(
        EvidenceMember(evidence_bundle_id=bundle.id, kind="FACT", accepted_fact_id=fact.id)
    )
    await session.commit()
    return bundle.id


async def test_fact_item_surfaces_source_effective_time_and_permitted_use(
    db_session: AsyncSession,
) -> None:
    fact = await _seed_fact_with_observation(
        db_session, source_name="Bank of England",
        rights_actions={
            "display": "ALLOW", "export": "ALLOW", "redistribute": "DENY", "ai": "ALLOW",
        },
    )
    bundle_id = await _seed_bundle_for_fact(db_session, fact)

    items = await get_evidence_bundle_items(db_session, bundle_id=bundle_id)

    assert items is not None
    assert len(items) == 1
    item = items[0]
    assert item.source == "Bank of England"
    assert item.effective_time == "2026-09-24T00:00:00+00:00"
    assert item.as_of == "2026-09-25T09:47:00+00:00"
    assert item.permitted_use == (
        "Export: permitted · Redistribution: not permitted · AI-composed use: permitted"
    )


async def test_fact_item_with_no_grant_for_an_action_shows_not_permitted(
    db_session: AsyncSession,
) -> None:
    # No "ai" grant at all - evaluate_action's fail-closed default applies.
    fact = await _seed_fact_with_observation(
        db_session, source_name="Frankfurter",
        rights_actions={"display": "ALLOW", "export": "ALLOW", "redistribute": "ALLOW"},
    )
    bundle_id = await _seed_bundle_for_fact(db_session, fact)

    items = await get_evidence_bundle_items(db_session, bundle_id=bundle_id)

    assert items is not None
    assert items[0].permitted_use is not None
    assert "AI-composed use: not permitted" in items[0].permitted_use


async def test_fact_item_with_no_linked_observation_has_no_source_or_rights(
    db_session: AsyncSession,
) -> None:
    fact = AcceptedFact(
        subject_type="TEST_SUBJECT", subject_id=uuid.uuid4(), metric_id="TEST_METRIC",
        valid_range=_VALID_RANGE,
        knowledge_range=Range(lower=_KNOWLEDGE_TIME, upper=None, bounds="[)"),
        value={"v": "1"}, status="ACTIVE",
    )
    db_session.add(fact)
    await db_session.flush()
    bundle_id = await _seed_bundle_for_fact(db_session, fact)

    items = await get_evidence_bundle_items(db_session, bundle_id=bundle_id)

    assert items is not None
    assert items[0].source is None
    assert items[0].permitted_use is None
    # Still has its own valid_range even with no linked observation.
    assert items[0].effective_time == "2026-09-24T00:00:00+00:00"


async def test_calculation_item_surfaces_spec_as_source_and_both_time_axes(
    db_session: AsyncSession,
) -> None:
    input_fact = await _seed_fact_with_observation(
        db_session, source_name="Bank of England",
        rights_actions={
            "display": "ALLOW", "export": "ALLOW", "redistribute": "ALLOW", "ai": "ALLOW",
        },
    )

    spec = CalculationSpecification(
        code="test_calc_v1", version="1", status="APPROVED", description="test spec"
    )
    db_session.add(spec)
    await db_session.flush()

    result = CalculationResult(
        calculation_specification_id=spec.id, subject_type="INSTRUMENT", subject_id=uuid.uuid4(),
        metric_id="TEST_RESULT", as_of_date=dt.date(2026, 9, 24), basis="MODEL_IMPLIED",
        value={"r": "1"}, status="ACTIVE",
    )
    db_session.add(result)
    await db_session.flush()
    db_session.add(
        CalculationInput(
            calculation_result_id=result.id, accepted_fact_id=input_fact.id, role="INPUT"
        )
    )
    await db_session.flush()

    bundle = EvidenceBundle(
        purpose_type="FACTUAL_EXPLANATION", knowledge_time=dt.datetime.now(dt.UTC),
        status="ASSEMBLING",
    )
    db_session.add(bundle)
    await db_session.flush()
    db_session.add(
        EvidenceMember(
            evidence_bundle_id=bundle.id, kind="CALCULATION", calculation_result_id=result.id
        )
    )
    await db_session.commit()

    items = await get_evidence_bundle_items(db_session, bundle_id=bundle.id)

    assert items is not None
    item = items[0]
    assert item.source == "Talvrin calculation (test_calc_v1 v1)"
    # effective_time is the market-effective as_of_date - distinct from
    # as_of, which is now uniformly knowledge/computation time.
    assert item.effective_time == "2026-09-24"
    assert item.as_of == result.created_at.isoformat()
    assert item.permitted_use == (
        "Export: permitted · Redistribution: permitted · AI-composed use: permitted"
    )
