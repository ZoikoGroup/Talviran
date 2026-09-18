"""End-to-end: real Frankfurter fixture -> connector.parse() -> FX ingest
-> a real accepted_fact row. Proves the Frankfurter connector and the
shared ingest_and_reconcile tail actually work together, not just each in
isolation.
"""

import datetime as dt
import uuid
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.connectors.base import AcquiredPayload
from app.modules.market.connectors.frankfurter_fx.mapping import FxRateCandidate
from app.modules.market.connectors.frankfurter_fx.reference_connector import (
    FrankfurterFxConnector,
)
from app.modules.market.models import AcceptedFact, Dataset, Source, SourceArtifact
from app.modules.market.pipeline.fx_ingest import (
    FxIngestSkipped,
    fx_pair_subject_id,
    ingest_fx_rate_candidate,
)
from app.modules.market.pipeline.ingest_tail import IngestOutcome
from app.modules.rights.models import RightsGrant, RightsProfile

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "frankfurter_usd_gbp_inr.json"


async def _seed_rights_profile(session: AsyncSession) -> uuid.UUID:
    profile = RightsProfile(
        code=f"frankfurter.fx.test.{uuid.uuid4().hex[:8]}", status="ACTIVE"
    )
    session.add(profile)
    await session.flush()
    session.add(
        RightsGrant(rights_profile_id=profile.id, action="store", permission_state="ALLOW")
    )
    await session.flush()
    return profile.id


async def _seed_source_artifact(session: AsyncSession) -> SourceArtifact:
    source = Source(code=f"frankfurter-test-{uuid.uuid4().hex[:8]}", name="Frankfurter (test)")
    session.add(source)
    await session.flush()
    dataset = Dataset(source_id=source.id, code="rates", name="Frankfurter Rates")
    session.add(dataset)
    await session.flush()
    artifact = SourceArtifact(
        dataset_id=dataset.id,
        sha256="3" * 64,
        storage_ref="test://frankfurter-fixture",
        media_type="application/json",
        byte_length=len(FIXTURE_PATH.read_bytes()),
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    session.add(artifact)
    await session.flush()
    return artifact


def _parse_fixture() -> list[FxRateCandidate]:
    connector = FrankfurterFxConnector(
        httpx.AsyncClient(), base_currency="USD", quote_currencies=("GBP", "INR")
    )
    payload = AcquiredPayload(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        content_type="application/json; charset=utf-8",
        status_code=200,
        fetched_at=dt.datetime.now(dt.UTC),
        source_url="test",
    )
    candidates = connector.parse(payload)
    return [c for c in candidates if isinstance(c, FxRateCandidate)]


async def test_real_fixture_flows_through_to_an_accepted_fact(db_session: AsyncSession) -> None:
    rights_profile_id = await _seed_rights_profile(db_session)
    artifact = await _seed_source_artifact(db_session)
    fetched_at = dt.datetime.now(dt.UTC)

    usd_inr = next(c for c in _parse_fixture() if c.quote_currency == "INR")

    result = await ingest_fx_rate_candidate(
        db_session,
        candidate=usd_inr,
        source_artifact_id=artifact.id,
        source_code="frankfurter",
        dataset_code="rates",
        rights_profile_id=rights_profile_id,
        fetched_at=fetched_at,
    )
    await db_session.commit()

    assert isinstance(result, IngestOutcome)
    assert result.reconciliation.decision == "ACCEPTED"

    fact = await db_session.get(AcceptedFact, result.reconciliation.accepted_fact_id)
    assert fact is not None
    assert fact.status == "ACTIVE"
    assert fact.subject_type == "FX_PAIR"
    assert fact.subject_id == fx_pair_subject_id("USD", "INR")
    assert fact.value == {"base_currency": "USD", "quote_currency": "INR", "rate": "95.91"}


async def test_two_different_days_coexist_without_superseding(db_session: AsyncSession) -> None:
    rights_profile_id = await _seed_rights_profile(db_session)
    artifact = await _seed_source_artifact(db_session)
    fetched_at = dt.datetime.now(dt.UTC)

    base = next(c for c in _parse_fixture() if c.quote_currency == "GBP")
    day1 = base
    day2 = FxRateCandidate(
        base_currency=base.base_currency,
        quote_currency=base.quote_currency,
        rate=base.rate + Decimal("0.01"),
        as_of=base.as_of + dt.timedelta(days=1),
    )

    first = await ingest_fx_rate_candidate(
        db_session, candidate=day1, source_artifact_id=artifact.id, source_code="frankfurter",
        dataset_code="rates", rights_profile_id=rights_profile_id, fetched_at=fetched_at,
    )
    await db_session.commit()

    second = await ingest_fx_rate_candidate(
        db_session, candidate=day2, source_artifact_id=artifact.id, source_code="frankfurter",
        dataset_code="rates", rights_profile_id=rights_profile_id, fetched_at=fetched_at,
    )
    await db_session.commit()

    assert isinstance(first, IngestOutcome) and isinstance(second, IngestOutcome)
    assert first.reconciliation.decision == "ACCEPTED"
    assert second.reconciliation.decision == "ACCEPTED"

    subject_id = fx_pair_subject_id(base.base_currency, base.quote_currency)
    facts = (
        await db_session.execute(select(AcceptedFact).where(AcceptedFact.subject_id == subject_id))
    ).scalars().all()
    assert len(facts) == 2
    assert all(f.status == "ACTIVE" for f in facts), "neither day should supersede the other"


async def test_reingesting_the_same_day_is_no_change(db_session: AsyncSession) -> None:
    rights_profile_id = await _seed_rights_profile(db_session)
    artifact = await _seed_source_artifact(db_session)

    candidate = next(c for c in _parse_fixture() if c.quote_currency == "GBP")

    first = await ingest_fx_rate_candidate(
        db_session, candidate=candidate, source_artifact_id=artifact.id, source_code="frankfurter",
        dataset_code="rates", rights_profile_id=rights_profile_id,
        fetched_at=dt.datetime.now(dt.UTC),
    )
    await db_session.commit()

    second = await ingest_fx_rate_candidate(
        db_session, candidate=candidate, source_artifact_id=artifact.id, source_code="frankfurter",
        dataset_code="rates", rights_profile_id=rights_profile_id,
        fetched_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )
    await db_session.commit()

    assert isinstance(first, IngestOutcome) and isinstance(second, IngestOutcome)
    assert first.observation_id == second.observation_id
    assert second.reconciliation.decision == "NO_CHANGE"


async def test_denied_rights_skips_ingest(db_session: AsyncSession) -> None:
    profile = RightsProfile(code=f"frankfurter.norights.{uuid.uuid4().hex[:8]}", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    artifact = await _seed_source_artifact(db_session)

    candidate = _parse_fixture()[0]

    result = await ingest_fx_rate_candidate(
        db_session, candidate=candidate, source_artifact_id=artifact.id, source_code="frankfurter",
        dataset_code="rates", rights_profile_id=profile.id, fetched_at=dt.datetime.now(dt.UTC),
    )

    assert isinstance(result, FxIngestSkipped)
    assert "rights check denied" in result.reason
