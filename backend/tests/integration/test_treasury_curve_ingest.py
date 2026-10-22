"""End-to-end: real Treasury fixture -> connector.parse() -> curve-point
ingest -> a real accepted_fact row. Mirrors test_boe_curve_ingest.py's own
shape exactly, proving the Treasury connector and the shared ingest tail
work together for a genuine daily time series, not just each in isolation.
"""

import datetime as dt
import uuid
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.connectors.base import AcquiredPayload
from app.modules.market.connectors.treasury_yield_curve.mapping import CurvePointCandidate
from app.modules.market.connectors.treasury_yield_curve.reference_connector import (
    TreasuryYieldCurveConnector,
)
from app.modules.market.models import AcceptedFact, Dataset, Source, SourceArtifact
from app.modules.market.pipeline.treasury_curve_ingest import (
    TreasuryCurveIngestResult,
    TreasuryCurveIngestSkipped,
    ingest_treasury_curve_point_candidate,
    treasury_curve_point_subject_id,
)
from app.modules.rights.models import RightsGrant, RightsProfile

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "fixtures" / "treasury_yield_curve_2026.xml"
)


async def _seed_rights_profile(session: AsyncSession) -> uuid.UUID:
    profile = RightsProfile(
        code=f"treasury.yield-curve.test.{uuid.uuid4().hex[:8]}", status="ACTIVE"
    )
    session.add(profile)
    await session.flush()
    session.add(RightsGrant(rights_profile_id=profile.id, action="store", permission_state="ALLOW"))
    await session.flush()
    return profile.id


async def _seed_source_artifact(session: AsyncSession) -> SourceArtifact:
    source = Source(code=f"treasury-test-{uuid.uuid4().hex[:8]}", name="US Treasury (test)")
    session.add(source)
    await session.flush()
    dataset = Dataset(
        source_id=source.id, code="par-yield-curve", name="US Treasury Par Yield Curve"
    )
    session.add(dataset)
    await session.flush()
    artifact = SourceArtifact(
        dataset_id=dataset.id,
        sha256="3" * 64,
        storage_ref="test://treasury-fixture",
        media_type="text/xml",
        byte_length=len(FIXTURE_PATH.read_bytes()),
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    session.add(artifact)
    await session.flush()
    return artifact


def _parse_fixture() -> list[CurvePointCandidate]:
    connector = TreasuryYieldCurveConnector(httpx.AsyncClient(), year=2026)
    payload = AcquiredPayload(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        content_type="text/xml",
        status_code=200,
        fetched_at=dt.datetime.now(dt.UTC),
        source_url="test",
    )
    candidates = connector.parse(payload)
    return [c for c in candidates if isinstance(c, CurvePointCandidate)]


async def test_real_fixture_flows_through_to_an_accepted_fact(db_session: AsyncSession) -> None:
    rights_profile_id = await _seed_rights_profile(db_session)
    artifact = await _seed_source_artifact(db_session)
    fetched_at = dt.datetime.now(dt.UTC)

    points = _parse_fixture()
    ten_year_jan2 = next(
        p
        for p in points
        if p.tenor_field == "BC_10YEAR" and p.curve_date == dt.date(2026, 1, 2)
    )

    result = await ingest_treasury_curve_point_candidate(
        db_session,
        candidate=ten_year_jan2,
        source_artifact_id=artifact.id,
        source_code="treasury",
        dataset_code="par-yield-curve",
        rights_profile_id=rights_profile_id,
        fetched_at=fetched_at,
    )
    await db_session.commit()

    assert isinstance(result, TreasuryCurveIngestResult)
    assert result.reconciliation.decision == "ACCEPTED"

    fact = await db_session.get(AcceptedFact, result.reconciliation.accepted_fact_id)
    assert fact is not None
    assert fact.status == "ACTIVE"
    assert fact.subject_type == "TREASURY_CURVE_POINT"
    assert fact.subject_id == treasury_curve_point_subject_id("BC_10YEAR")
    assert fact.value == {
        "tenor_field": "BC_10YEAR",
        "tenor_label": "10 Year",
        "par_yield_pct": "4.19",
    }


async def test_two_different_days_coexist_without_superseding(db_session: AsyncSession) -> None:
    rights_profile_id = await _seed_rights_profile(db_session)
    artifact = await _seed_source_artifact(db_session)
    fetched_at = dt.datetime.now(dt.UTC)

    points = _parse_fixture()
    ten_year = [p for p in points if p.tenor_field == "BC_10YEAR"]
    day1 = next(p for p in ten_year if p.curve_date == dt.date(2026, 1, 2))
    day2 = next(p for p in ten_year if p.curve_date == dt.date(2026, 1, 5))
    assert day1.par_yield_pct != day2.par_yield_pct, "test needs two genuinely different values"

    first = await ingest_treasury_curve_point_candidate(
        db_session, candidate=day1, source_artifact_id=artifact.id, source_code="treasury",
        dataset_code="par-yield-curve", rights_profile_id=rights_profile_id, fetched_at=fetched_at,
    )
    await db_session.commit()

    second = await ingest_treasury_curve_point_candidate(
        db_session, candidate=day2, source_artifact_id=artifact.id, source_code="treasury",
        dataset_code="par-yield-curve", rights_profile_id=rights_profile_id, fetched_at=fetched_at,
    )
    await db_session.commit()

    assert isinstance(first, TreasuryCurveIngestResult)
    assert isinstance(second, TreasuryCurveIngestResult)
    assert first.reconciliation.decision == "ACCEPTED"
    assert second.reconciliation.decision == "ACCEPTED"

    subject_id = treasury_curve_point_subject_id("BC_10YEAR")
    facts = (
        await db_session.execute(select(AcceptedFact).where(AcceptedFact.subject_id == subject_id))
    ).scalars().all()
    assert len(facts) == 2
    assert all(f.status == "ACTIVE" for f in facts), "neither day should supersede the other"


async def test_reingesting_the_same_day_is_no_change(db_session: AsyncSession) -> None:
    rights_profile_id = await _seed_rights_profile(db_session)
    artifact = await _seed_source_artifact(db_session)

    points = _parse_fixture()
    point = next(
        p for p in points if p.tenor_field == "BC_10YEAR" and p.curve_date == dt.date(2026, 1, 2)
    )

    first = await ingest_treasury_curve_point_candidate(
        db_session, candidate=point, source_artifact_id=artifact.id, source_code="treasury",
        dataset_code="par-yield-curve", rights_profile_id=rights_profile_id,
        fetched_at=dt.datetime.now(dt.UTC),
    )
    await db_session.commit()

    second = await ingest_treasury_curve_point_candidate(
        db_session, candidate=point, source_artifact_id=artifact.id, source_code="treasury",
        dataset_code="par-yield-curve", rights_profile_id=rights_profile_id,
        fetched_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )
    await db_session.commit()

    assert isinstance(first, TreasuryCurveIngestResult)
    assert isinstance(second, TreasuryCurveIngestResult)
    assert first.observation_id == second.observation_id
    assert second.reconciliation.decision == "NO_CHANGE"


async def test_denied_rights_skips_ingest(db_session: AsyncSession) -> None:
    profile = RightsProfile(code=f"treasury.norights.{uuid.uuid4().hex[:8]}", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    artifact = await _seed_source_artifact(db_session)

    points = _parse_fixture()
    point = points[0]

    result = await ingest_treasury_curve_point_candidate(
        db_session, candidate=point, source_artifact_id=artifact.id, source_code="treasury",
        dataset_code="par-yield-curve", rights_profile_id=profile.id,
        fetched_at=dt.datetime.now(dt.UTC),
    )

    assert isinstance(result, TreasuryCurveIngestSkipped)
    assert "rights check denied" in result.reason
