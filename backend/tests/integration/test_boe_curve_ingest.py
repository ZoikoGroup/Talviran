"""End-to-end: real BoE fixture -> connector.parse() -> curve-point ingest
-> a real accepted_fact row. Proves the BoE connector and the
valid_range-overlap fix in reconcile.py actually work together for a
genuine daily time series, not just each in isolation.
"""

import datetime as dt
import uuid
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.connectors.base import AcquiredPayload
from app.modules.market.connectors.boe_yield_curve.mapping import CurvePointCandidate
from app.modules.market.connectors.boe_yield_curve.reference_connector import (
    BoEYieldCurveConnector,
)
from app.modules.market.models import AcceptedFact, Dataset, Source, SourceArtifact
from app.modules.market.pipeline.curve_ingest import (
    CurveIngestResult,
    CurveIngestSkipped,
    curve_point_subject_id,
    ingest_curve_point_candidate,
)
from app.modules.rights.models import RightsGrant, RightsProfile

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "fixtures" / "boe_yield_curve_latest.zip"
)


async def _seed_rights_profile(session: AsyncSession) -> uuid.UUID:
    profile = RightsProfile(code=f"boe.yield-curve.test.{uuid.uuid4().hex[:8]}", status="ACTIVE")
    session.add(profile)
    await session.flush()
    session.add(RightsGrant(rights_profile_id=profile.id, action="store", permission_state="ALLOW"))
    await session.flush()
    return profile.id


async def _seed_source_artifact(session: AsyncSession) -> SourceArtifact:
    source = Source(code=f"boe-test-{uuid.uuid4().hex[:8]}", name="Bank of England (test)")
    session.add(source)
    await session.flush()
    dataset = Dataset(
        source_id=source.id, code="gilt-nominal-spot-curve", name="Gilt Nominal Spot Curve"
    )
    session.add(dataset)
    await session.flush()
    artifact = SourceArtifact(
        dataset_id=dataset.id,
        sha256="2" * 64,
        storage_ref="test://boe-fixture",
        media_type="application/x-zip-compressed",
        byte_length=len(FIXTURE_PATH.read_bytes()),
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    session.add(artifact)
    await session.flush()
    return artifact


def _parse_fixture() -> list[CurvePointCandidate]:
    connector = BoEYieldCurveConnector(httpx.AsyncClient())
    payload = AcquiredPayload(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        content_type="application/x-zip-compressed",
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
    ten_year_first_day = next(
        p
        for p in points
        if p.tenor_years == Decimal("10") and p.curve_date == dt.date(2026, 9, 1)
    )

    result = await ingest_curve_point_candidate(
        db_session,
        candidate=ten_year_first_day,
        source_artifact_id=artifact.id,
        source_code="boe",
        dataset_code="gilt-nominal-spot-curve",
        rights_profile_id=rights_profile_id,
        fetched_at=fetched_at,
    )
    await db_session.commit()

    assert isinstance(result, CurveIngestResult)
    assert result.reconciliation.decision == "ACCEPTED"

    fact = await db_session.get(AcceptedFact, result.reconciliation.accepted_fact_id)
    assert fact is not None
    assert fact.status == "ACTIVE"
    assert fact.subject_type == "YIELD_CURVE_POINT"
    assert fact.subject_id == curve_point_subject_id(Decimal("10"))
    assert fact.value == {"tenor_years": "10", "spot_rate_pct": "5.206769"}


async def test_two_different_days_coexist_without_superseding(db_session: AsyncSession) -> None:
    rights_profile_id = await _seed_rights_profile(db_session)
    artifact = await _seed_source_artifact(db_session)
    fetched_at = dt.datetime.now(dt.UTC)

    points = _parse_fixture()
    ten_year = [p for p in points if p.tenor_years == Decimal("10")]
    day1 = next(p for p in ten_year if p.curve_date == dt.date(2026, 9, 1))
    day2 = next(p for p in ten_year if p.curve_date == dt.date(2026, 9, 2))
    assert day1.spot_rate_pct != day2.spot_rate_pct, "test needs two genuinely different values"

    first = await ingest_curve_point_candidate(
        db_session, candidate=day1, source_artifact_id=artifact.id, source_code="boe",
        dataset_code="gilt-nominal-spot-curve", rights_profile_id=rights_profile_id,
        fetched_at=fetched_at,
    )
    await db_session.commit()

    second = await ingest_curve_point_candidate(
        db_session, candidate=day2, source_artifact_id=artifact.id, source_code="boe",
        dataset_code="gilt-nominal-spot-curve", rights_profile_id=rights_profile_id,
        fetched_at=fetched_at,
    )
    await db_session.commit()

    assert isinstance(first, CurveIngestResult) and isinstance(second, CurveIngestResult)
    assert first.reconciliation.decision == "ACCEPTED"
    assert second.reconciliation.decision == "ACCEPTED"

    subject_id = curve_point_subject_id(Decimal("10"))
    facts = (
        await db_session.execute(
            select(AcceptedFact).where(AcceptedFact.subject_id == subject_id)
        )
    ).scalars().all()
    assert len(facts) == 2
    assert all(f.status == "ACTIVE" for f in facts), "neither day should supersede the other"


async def test_reingesting_the_same_day_is_no_change(db_session: AsyncSession) -> None:
    rights_profile_id = await _seed_rights_profile(db_session)
    artifact = await _seed_source_artifact(db_session)

    points = _parse_fixture()
    point = next(
        p
        for p in points
        if p.tenor_years == Decimal("10") and p.curve_date == dt.date(2026, 9, 1)
    )

    first = await ingest_curve_point_candidate(
        db_session, candidate=point, source_artifact_id=artifact.id, source_code="boe",
        dataset_code="gilt-nominal-spot-curve", rights_profile_id=rights_profile_id,
        fetched_at=dt.datetime.now(dt.UTC),
    )
    await db_session.commit()

    second = await ingest_curve_point_candidate(
        db_session, candidate=point, source_artifact_id=artifact.id, source_code="boe",
        dataset_code="gilt-nominal-spot-curve", rights_profile_id=rights_profile_id,
        fetched_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )
    await db_session.commit()

    assert isinstance(first, CurveIngestResult) and isinstance(second, CurveIngestResult)
    assert first.observation_id == second.observation_id
    assert second.reconciliation.decision == "NO_CHANGE"


async def test_denied_rights_skips_ingest(db_session: AsyncSession) -> None:
    profile = RightsProfile(code=f"boe.norights.{uuid.uuid4().hex[:8]}", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    artifact = await _seed_source_artifact(db_session)

    points = _parse_fixture()
    point = points[0]

    result = await ingest_curve_point_candidate(
        db_session, candidate=point, source_artifact_id=artifact.id, source_code="boe",
        dataset_code="gilt-nominal-spot-curve", rights_profile_id=profile.id,
        fetched_at=dt.datetime.now(dt.UTC),
    )

    assert isinstance(result, CurveIngestSkipped)
    assert "rights check denied" in result.reason
