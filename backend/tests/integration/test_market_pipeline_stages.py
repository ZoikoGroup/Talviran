"""End-to-end: real DMO fixture data -> connector.parse() -> identity
resolve -> observation write -> reconcile -> a real accepted_fact row.
This is what proves weeks 7-9 actually work together, not just each in
isolation.
"""

import datetime as dt
import uuid
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.connectors.base import AcquiredPayload
from app.modules.market.connectors.dmo_gilts.mapping import RecordIssue
from app.modules.market.connectors.dmo_gilts.reference_connector import DMOGiltsReferenceConnector
from app.modules.market.models import AcceptedFact, Dataset, Source, SourceArtifact
from app.modules.market.pipeline.stages import (
    IngestResult,
    IngestSkipped,
    ingest_gilt_reference_candidate,
)
from app.modules.reference.models import FiSovereignTerms, Instrument, InstrumentAlias, Issuer
from app.modules.rights.models import RightsGrant, RightsProfile

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "fixtures" / "dmo_gilts_in_issue.xml"
)
SEED_ISIN = "GB0032452392"


async def _seed_reference_and_rights(session: AsyncSession) -> tuple[str, str]:
    """Mirrors scripts/seed_dev.py's onboarding, scoped to this test's own
    session/transaction. Returns (rights_profile_id_str placeholder unused,
    instrument_id) — kept simple since callers just need the rights
    profile id back too.
    """
    issuer = Issuer(name="HM Treasury", country_code="GB", status="ACTIVE")
    session.add(issuer)
    await session.flush()

    instrument = Instrument(
        issuer_id=issuer.id,
        instrument_type="FI_SOVEREIGN",
        name="4 1/4% Treasury Stock 2036",
        currency_code="GBP",
        status="ACTIVE",
    )
    session.add(instrument)
    await session.flush()

    session.add(
        InstrumentAlias(instrument_id=instrument.id, alias_type="ISIN", alias_value=SEED_ISIN)
    )
    session.add(
        FiSovereignTerms(
            instrument_id=instrument.id,
            coupon_rate=Decimal("4.25"),
            coupon_frequency="SEMI_ANNUAL",
            day_count_convention="ACT_ACT_ICMA",
            first_issue_date=dt.date(2003, 2, 27),
            maturity_date=dt.date(2036, 3, 7),
            ex_dividend_days=7,
        )
    )

    profile = RightsProfile(code="uk-dmo.gilts.test", status="ACTIVE")
    session.add(profile)
    await session.flush()
    session.add(RightsGrant(rights_profile_id=profile.id, action="store", permission_state="ALLOW"))
    await session.flush()

    return str(profile.id), str(instrument.id)


async def _seed_source_artifact(session: AsyncSession) -> SourceArtifact:
    source = Source(code="uk-dmo-test", name="UK DMO (test)", status="ACTIVE")
    session.add(source)
    await session.flush()
    dataset = Dataset(source_id=source.id, code="gilts-in-issue", name="Gilts in Issue")
    session.add(dataset)
    await session.flush()
    artifact = SourceArtifact(
        dataset_id=dataset.id,
        sha256="1" * 64,
        storage_ref="test://fixture",
        media_type="text/xml",
        byte_length=len(FIXTURE_PATH.read_bytes()),
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    session.add(artifact)
    await session.flush()
    return artifact


async def test_real_fixture_flows_through_to_an_accepted_fact(db_session: AsyncSession) -> None:
    rights_profile_id_str, instrument_id_str = await _seed_reference_and_rights(db_session)
    artifact = await _seed_source_artifact(db_session)

    connector = DMOGiltsReferenceConnector(httpx.AsyncClient())
    payload = AcquiredPayload(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        content_type="text/xml",
        status_code=200,
        fetched_at=dt.datetime.now(dt.UTC),
        source_url="test",
    )
    candidates = connector.parse(payload)
    seed_candidate = next(
        c for c in candidates if not isinstance(c, RecordIssue) and c.isin == SEED_ISIN
    )

    result = await ingest_gilt_reference_candidate(
        db_session,
        candidate=seed_candidate,
        source_artifact_id=artifact.id,
        source_code="uk-dmo",
        dataset_code="gilts-in-issue",
        rights_profile_id=uuid.UUID(rights_profile_id_str),
        fetched_at=payload.fetched_at,
    )
    await db_session.commit()

    assert isinstance(result, IngestResult)
    assert result.reconciliation.decision == "ACCEPTED"

    fact = await db_session.get(AcceptedFact, result.reconciliation.accepted_fact_id)
    assert fact is not None
    assert fact.status == "ACTIVE"
    assert fact.subject_id == uuid.UUID(instrument_id_str)
    assert fact.value["coupon_rate"] == "4.25"
    assert fact.value["redemption_date"] == "2036-03-07"


async def test_reingesting_the_same_snapshot_is_no_change(db_session: AsyncSession) -> None:
    rights_profile_id_str, _ = await _seed_reference_and_rights(db_session)
    artifact = await _seed_source_artifact(db_session)

    connector = DMOGiltsReferenceConnector(httpx.AsyncClient())
    payload = AcquiredPayload(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        content_type="text/xml",
        status_code=200,
        fetched_at=dt.datetime.now(dt.UTC),
        source_url="test",
    )
    candidates = connector.parse(payload)
    seed_candidate = next(
        c for c in candidates if not isinstance(c, RecordIssue) and c.isin == SEED_ISIN
    )

    rights_profile_id = uuid.UUID(rights_profile_id_str)

    first = await ingest_gilt_reference_candidate(
        db_session,
        candidate=seed_candidate,
        source_artifact_id=artifact.id,
        source_code="uk-dmo",
        dataset_code="gilts-in-issue",
        rights_profile_id=rights_profile_id,
        fetched_at=payload.fetched_at,
    )
    await db_session.commit()

    second = await ingest_gilt_reference_candidate(
        db_session,
        candidate=seed_candidate,
        source_artifact_id=artifact.id,
        source_code="uk-dmo",
        dataset_code="gilts-in-issue",
        rights_profile_id=rights_profile_id,
        fetched_at=payload.fetched_at + dt.timedelta(hours=1),
    )
    await db_session.commit()

    assert isinstance(first, IngestResult)
    assert isinstance(second, IngestResult)
    # Same semantic_observation_key (same close_of_business_date) -> the
    # SAME observation row is reused, not duplicated.
    assert first.observation_id == second.observation_id
    assert second.reconciliation.decision == "NO_CHANGE"


async def test_unresolved_isin_is_skipped_not_guessed(db_session: AsyncSession) -> None:
    # Deliberately do NOT seed reference data — no instrument_alias exists
    # for any ISIN in the fixture, so every candidate must be skipped.
    profile = RightsProfile(code="uk-dmo.gilts.test2", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    db_session.add(
        RightsGrant(rights_profile_id=profile.id, action="store", permission_state="ALLOW")
    )
    await db_session.flush()

    artifact = await _seed_source_artifact(db_session)

    connector = DMOGiltsReferenceConnector(httpx.AsyncClient())
    payload = AcquiredPayload(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        content_type="text/xml",
        status_code=200,
        fetched_at=dt.datetime.now(dt.UTC),
        source_url="test",
    )
    candidates = connector.parse(payload)
    seed_candidate = next(
        c for c in candidates if not isinstance(c, RecordIssue) and c.isin == SEED_ISIN
    )

    result = await ingest_gilt_reference_candidate(
        db_session,
        candidate=seed_candidate,
        source_artifact_id=artifact.id,
        source_code="uk-dmo",
        dataset_code="gilts-in-issue",
        rights_profile_id=profile.id,
        fetched_at=payload.fetched_at,
    )

    assert isinstance(result, IngestSkipped)
    assert "instrument_alias" in result.reason


async def test_denied_rights_skips_without_touching_identity(db_session: AsyncSession) -> None:
    # No RightsGrant at all for this profile -> fail-closed DENY.
    profile = RightsProfile(code="uk-dmo.gilts.norights", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    artifact = await _seed_source_artifact(db_session)

    connector = DMOGiltsReferenceConnector(httpx.AsyncClient())
    payload = AcquiredPayload(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        content_type="text/xml",
        status_code=200,
        fetched_at=dt.datetime.now(dt.UTC),
        source_url="test",
    )
    candidates = connector.parse(payload)
    seed_candidate = next(
        c for c in candidates if not isinstance(c, RecordIssue) and c.isin == SEED_ISIN
    )

    result = await ingest_gilt_reference_candidate(
        db_session,
        candidate=seed_candidate,
        source_artifact_id=artifact.id,
        source_code="uk-dmo",
        dataset_code="gilts-in-issue",
        rights_profile_id=profile.id,
        fetched_at=payload.fetched_at,
    )

    assert isinstance(result, IngestSkipped)
    assert "rights check denied" in result.reason
