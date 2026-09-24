"""Proves the real point of adding boe_fx: two genuinely independent
sources for the same real-world FX rate now actually get compared against
each other through the real ingestion path, not just synthetically in
test_reconcile.py. Before ingest_tail.ingest_and_reconcile gathered sibling
observations across sources, a second source's slightly different value
would have silently "superseded" the first's as an ordinary value change -
never compared, agreement or disagreement.
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.connectors.frankfurter_fx.mapping import FxRateCandidate
from app.modules.market.models import AcceptedFact, Dataset, Source, SourceArtifact
from app.modules.market.pipeline.fx_ingest import fx_pair_subject_id, ingest_fx_rate_candidate
from app.modules.market.pipeline.ingest_tail import IngestOutcome
from app.modules.rights.models import RightsGrant, RightsProfile

_GBP_USD_DAY = dt.date(2026, 9, 22)


async def _seed_rights_profile(session: AsyncSession, code: str) -> uuid.UUID:
    profile = RightsProfile(code=f"{code}.test.{uuid.uuid4().hex[:8]}", status="ACTIVE")
    session.add(profile)
    await session.flush()
    session.add(RightsGrant(rights_profile_id=profile.id, action="store", permission_state="ALLOW"))
    await session.flush()
    return profile.id


async def _seed_artifact(session: AsyncSession, *, source_code: str) -> SourceArtifact:
    source = Source(code=source_code, name=source_code)
    session.add(source)
    await session.flush()
    dataset = Dataset(source_id=source.id, code="rates", name="rates")
    session.add(dataset)
    await session.flush()
    artifact = SourceArtifact(
        dataset_id=dataset.id, sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        storage_ref=f"test://{source_code}", media_type="text/csv", byte_length=1,
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    session.add(artifact)
    await session.flush()
    return artifact


async def test_boe_and_frankfurter_agree_within_tolerance_and_publish_one_fact(
    db_session: AsyncSession,
) -> None:
    frankfurter_rights = await _seed_rights_profile(db_session, "frankfurter.fx")
    boe_rights = await _seed_rights_profile(db_session, "boe.fx-rates")
    frankfurter_artifact = await _seed_artifact(db_session, source_code="frankfurter")
    boe_artifact = await _seed_artifact(db_session, source_code="boe")

    frankfurter_candidate = FxRateCandidate(
        base_currency="GBP", quote_currency="USD", rate=Decimal("1.3350"), as_of=_GBP_USD_DAY
    )
    boe_candidate = FxRateCandidate(
        base_currency="GBP", quote_currency="USD", rate=Decimal("1.3348"), as_of=_GBP_USD_DAY
    )

    first = await ingest_fx_rate_candidate(
        db_session, candidate=frankfurter_candidate, source_artifact_id=frankfurter_artifact.id,
        source_code="frankfurter", dataset_code="rates",
        rights_profile_id=frankfurter_rights, fetched_at=dt.datetime.now(dt.UTC),
    )
    await db_session.commit()
    assert isinstance(first, IngestOutcome)
    assert first.reconciliation.decision == "ACCEPTED"

    second = await ingest_fx_rate_candidate(
        db_session, candidate=boe_candidate, source_artifact_id=boe_artifact.id,
        source_code="boe", dataset_code="fx-daily-spot-rates",
        rights_profile_id=boe_rights, fetched_at=dt.datetime.now(dt.UTC),
    )
    await db_session.commit()

    assert isinstance(second, IngestOutcome)
    assert second.reconciliation.decision == "ACCEPTED", (
        "two sources 0.0002 apart on a 0.01-tolerance policy must agree, not conflict"
    )

    subject_id = fx_pair_subject_id("GBP", "USD")
    fact = await db_session.get(AcceptedFact, second.reconciliation.accepted_fact_id)
    assert fact is not None
    assert fact.subject_id == subject_id
    assert fact.status == "ACTIVE"
    # frankfurter has precedence in FX_SPOT_RATE_POLICY.ordered_source_codes
    assert fact.value["rate"] == "1.3350"

    active_facts = (
        await db_session.execute(
            select(AcceptedFact).where(
                AcceptedFact.subject_id == subject_id, AcceptedFact.status == "ACTIVE"
            )
        )
    ).scalars().all()
    assert len(active_facts) == 1, "agreement must publish exactly one fact, not two"


async def test_boe_and_frankfurter_disagreeing_beyond_tolerance_flags_conflict(
    db_session: AsyncSession,
) -> None:
    frankfurter_rights = await _seed_rights_profile(db_session, "frankfurter.fx")
    boe_rights = await _seed_rights_profile(db_session, "boe.fx-rates")
    frankfurter_artifact = await _seed_artifact(db_session, source_code="frankfurter")
    boe_artifact = await _seed_artifact(db_session, source_code="boe")

    frankfurter_candidate = FxRateCandidate(
        base_currency="GBP", quote_currency="USD", rate=Decimal("1.3350"), as_of=_GBP_USD_DAY
    )
    # Genuinely implausible for real GBP/USD - proves a real disagreement
    # still surfaces as CONFLICT even with tolerance active, not silently
    # averaged or overwritten.
    boe_candidate = FxRateCandidate(
        base_currency="GBP", quote_currency="USD", rate=Decimal("2.0000"), as_of=_GBP_USD_DAY
    )

    first = await ingest_fx_rate_candidate(
        db_session, candidate=frankfurter_candidate, source_artifact_id=frankfurter_artifact.id,
        source_code="frankfurter", dataset_code="rates",
        rights_profile_id=frankfurter_rights, fetched_at=dt.datetime.now(dt.UTC),
    )
    await db_session.commit()
    assert isinstance(first, IngestOutcome)
    assert first.reconciliation.decision == "ACCEPTED"

    second = await ingest_fx_rate_candidate(
        db_session, candidate=boe_candidate, source_artifact_id=boe_artifact.id,
        source_code="boe", dataset_code="fx-daily-spot-rates",
        rights_profile_id=boe_rights, fetched_at=dt.datetime.now(dt.UTC),
    )
    await db_session.commit()

    assert isinstance(second, IngestOutcome)
    assert second.reconciliation.decision == "CONFLICT"
    assert second.reconciliation.accepted_fact_id is None

    # The first source's fact must still stand - a later CONFLICT must
    # never retroactively unpublish an already-accepted fact.
    subject_id = fx_pair_subject_id("GBP", "USD")
    original_fact = await db_session.get(AcceptedFact, first.reconciliation.accepted_fact_id)
    assert original_fact is not None
    assert original_fact.status == "ACTIVE"
    assert original_fact.subject_id == subject_id
