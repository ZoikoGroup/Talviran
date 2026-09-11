"""Proves reconcile_and_publish's real behavior against Postgres: NO_CHANGE
doesn't create a duplicate fact, a changed value supersedes the previous
version (never mutates it in place), and disagreement surfaces as CONFLICT
rather than being silently resolved — unless the policy explicitly says
otherwise, in which case it's still logged, not silent.
"""

import datetime as dt
import uuid
from dataclasses import replace

import pytest
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.models import (
    AcceptedFact,
    Dataset,
    Source,
    SourceArtifact,
    SourceObservation,
)
from app.modules.market.pipeline.reconcile import (
    CandidateObservation,
    reconcile_and_publish,
)
from app.modules.market.pipeline.reconciliation_policy import (
    CONFLICT_ACTION_FLAG,
    CONFLICT_ACTION_PREFER_ORDER,
    ReconciliationPolicy,
)
from app.modules.rights.models import RightsProfile

_POLICY = ReconciliationPolicy(
    metric_id="TEST_METRIC", ordered_source_codes=("source-a",), tolerance=None,
    conflict_action=CONFLICT_ACTION_FLAG,
)

# A fixed, shared valid_range — real-world validity is a caller concern
# (e.g. an instrument's first_issue_date), separate from knowledge_time.
# Using the SAME valid_range across "supersede" test calls is deliberate:
# it proves a correction reuses the same real-world validity period and
# only knowledge_range changes (see reconcile_and_publish's docstring).
_VALID_RANGE: Range[dt.datetime] = Range(
    lower=dt.datetime(2000, 1, 1, tzinfo=dt.UTC), upper=None, bounds="[)"
)


async def _seed_observation(session: AsyncSession, source_code: str) -> SourceObservation:
    # fact_observation_link.source_observation_id has a real FK — a
    # candidate must point at a genuine observation row, not a bare UUID.
    profile = RightsProfile(code=f"test.{source_code}.{uuid.uuid4().hex[:8]}", status="ACTIVE")
    session.add(profile)
    await session.flush()

    source = Source(code=f"{source_code}-{uuid.uuid4().hex[:8]}", name=source_code, status="ACTIVE")
    session.add(source)
    await session.flush()

    dataset = Dataset(source_id=source.id, code="test-dataset", name="Test Dataset")
    session.add(dataset)
    await session.flush()

    artifact = SourceArtifact(
        dataset_id=dataset.id,
        sha256="0" * 64,
        storage_ref="test://artifact",
        media_type="application/xml",
        byte_length=1,
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    session.add(artifact)
    await session.flush()

    observation = SourceObservation(
        source_artifact_id=artifact.id,
        rights_profile_id=profile.id,
        subject_type="INSTRUMENT",
        metric_id="TEST_METRIC",
        semantic_observation_key=str(uuid.uuid4()),
        raw_value={},
        observed_at=dt.datetime.now(dt.UTC),
    )
    session.add(observation)
    await session.flush()
    return observation


async def _candidate(
    session: AsyncSession, source_code: str = "source-a", **value_overrides: object
) -> CandidateObservation:
    value = {"coupon_rate": "4.25", **value_overrides}
    observation = await _seed_observation(session, source_code)
    return CandidateObservation(observation_id=observation.id, source_code=source_code, value=value)


async def test_first_candidate_creates_accepted_fact(db_session: AsyncSession) -> None:
    subject_id = uuid.uuid4()

    outcome = await reconcile_and_publish(
        db_session,
        subject_type="INSTRUMENT",
        subject_id=subject_id,
        metric_id="TEST_METRIC",
        candidates=[await _candidate(db_session)],
        policy=_POLICY,
        valid_range=_VALID_RANGE, knowledge_time=dt.datetime.now(dt.UTC),
    )
    await db_session.commit()

    assert outcome.decision == "ACCEPTED"
    fact = await db_session.get(AcceptedFact, outcome.accepted_fact_id)
    assert fact is not None
    assert fact.status == "ACTIVE"
    assert fact.value == {"coupon_rate": "4.25"}


async def test_identical_candidate_is_no_change(db_session: AsyncSession) -> None:
    subject_id = uuid.uuid4()
    now = dt.datetime.now(dt.UTC)

    first = await reconcile_and_publish(
        db_session, subject_type="INSTRUMENT", subject_id=subject_id, metric_id="TEST_METRIC",
        candidates=[await _candidate(db_session)],
        policy=_POLICY, valid_range=_VALID_RANGE, knowledge_time=now,
    )
    await db_session.commit()

    second = await reconcile_and_publish(
        db_session, subject_type="INSTRUMENT", subject_id=subject_id, metric_id="TEST_METRIC",
        candidates=[await _candidate(db_session)],
        policy=_POLICY,
        valid_range=_VALID_RANGE, knowledge_time=now + dt.timedelta(days=1),
    )
    await db_session.commit()

    assert second.decision == "NO_CHANGE"
    assert second.accepted_fact_id == first.accepted_fact_id

    count = (
        await db_session.execute(
            select(AcceptedFact).where(AcceptedFact.subject_id == subject_id)
        )
    ).scalars().all()
    assert len(count) == 1, "NO_CHANGE must not create a second row"


async def test_changed_value_supersedes_without_mutating_history(db_session: AsyncSession) -> None:
    subject_id = uuid.uuid4()
    t0 = dt.datetime.now(dt.UTC)
    t1 = t0 + dt.timedelta(days=1)

    first = await reconcile_and_publish(
        db_session, subject_type="INSTRUMENT", subject_id=subject_id, metric_id="TEST_METRIC",
        candidates=[await _candidate(db_session, coupon_rate="4.25")],
        policy=_POLICY, valid_range=_VALID_RANGE, knowledge_time=t0,
    )
    await db_session.commit()

    second = await reconcile_and_publish(
        db_session, subject_type="INSTRUMENT", subject_id=subject_id, metric_id="TEST_METRIC",
        candidates=[await _candidate(db_session, coupon_rate="4.50")],
        policy=_POLICY, valid_range=_VALID_RANGE, knowledge_time=t1,
    )
    await db_session.commit()

    assert second.decision == "ACCEPTED"
    assert second.accepted_fact_id != first.accepted_fact_id

    old_fact = await db_session.get(AcceptedFact, first.accepted_fact_id)
    new_fact = await db_session.get(AcceptedFact, second.accepted_fact_id)
    assert old_fact is not None and new_fact is not None
    assert old_fact.status == "SUPERSEDED"
    assert old_fact.superseded_by_id == new_fact.id
    assert old_fact.value == {"coupon_rate": "4.25"}, "history must never be rewritten in place"
    assert new_fact.status == "ACTIVE"
    assert new_fact.value == {"coupon_rate": "4.50"}


async def test_disagreeing_candidates_flag_conflict_and_create_no_fact(
    db_session: AsyncSession,
) -> None:
    subject_id = uuid.uuid4()

    outcome = await reconcile_and_publish(
        db_session, subject_type="INSTRUMENT", subject_id=subject_id, metric_id="TEST_METRIC",
        candidates=[
            await _candidate(db_session, source_code="source-a", coupon_rate="4.25"),
            await _candidate(db_session, source_code="source-b", coupon_rate="4.50"),
        ],
        policy=_POLICY, valid_range=_VALID_RANGE, knowledge_time=dt.datetime.now(dt.UTC),
    )
    await db_session.commit()

    assert outcome.decision == "CONFLICT"
    assert outcome.accepted_fact_id is None

    facts = (
        await db_session.execute(
            select(AcceptedFact).where(AcceptedFact.subject_id == subject_id)
        )
    ).scalars().all()
    assert facts == [], "a CONFLICT must never publish a fact"


async def test_prefer_order_policy_resolves_by_precedence_but_still_logs_conflict(
    db_session: AsyncSession,
) -> None:
    subject_id = uuid.uuid4()
    policy = replace(
        _POLICY, ordered_source_codes=("source-b", "source-a"),
        conflict_action=CONFLICT_ACTION_PREFER_ORDER,
    )

    outcome = await reconcile_and_publish(
        db_session, subject_type="INSTRUMENT", subject_id=subject_id, metric_id="TEST_METRIC",
        candidates=[
            await _candidate(db_session, source_code="source-a", coupon_rate="4.25"),
            await _candidate(db_session, source_code="source-b", coupon_rate="4.50"),
        ],
        policy=policy, valid_range=_VALID_RANGE, knowledge_time=dt.datetime.now(dt.UTC),
    )
    await db_session.commit()

    assert outcome.decision == "ACCEPTED"
    fact = await db_session.get(AcceptedFact, outcome.accepted_fact_id)
    assert fact is not None
    assert fact.value == {"coupon_rate": "4.50"}, "source-b has precedence in this policy"
    assert "precedence" in outcome.reason


_INSERT_ACCEPTED_FACT = text(
    """
    INSERT INTO market.accepted_fact (
        id, subject_type, subject_id, metric_id,
        valid_range, knowledge_range, value, status
    )
    VALUES (
        gen_random_uuid(), 'INSTRUMENT', :subject_id, 'TEST_METRIC',
        tstzrange(now(), null, '[)'), tstzrange(now(), null, '[)'),
        (:value)::jsonb, 'ACTIVE'
    )
    """
)


async def test_gist_exclusion_constraint_rejects_overlapping_ranges_at_db_level(
    db_session: AsyncSession,
) -> None:
    # Proves the DB-level constraint, not just the app-level "check current
    # fact first" logic in reconcile_and_publish — a second writer bypassing
    # the service layer entirely must still be rejected.
    subject_id = uuid.uuid4()
    await db_session.execute(_INSERT_ACCEPTED_FACT, {"subject_id": subject_id, "value": '{"a": 1}'})
    await db_session.commit()

    with pytest.raises(IntegrityError):
        await db_session.execute(
            _INSERT_ACCEPTED_FACT, {"subject_id": subject_id, "value": '{"a": 2}'}
        )
        await db_session.commit()
