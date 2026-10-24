"""End-to-end: real TreasuryDirect fixture -> connector.parse() -> CUSIP
identity resolve -> observation write -> reconcile -> a real accepted_fact
row. Mirrors test_market_pipeline_stages.py's gilt equivalent exactly,
proving the same identity-resolve + observation-write + reconcile tail
works for CUSIP-keyed securities, not just ISIN-keyed gilts.
"""

import datetime as dt
import uuid
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.connectors.base import AcquiredPayload
from app.modules.market.connectors.treasury_securities.mapping import (
    RecordIssue,
    TreasurySecurityCandidate,
)
from app.modules.market.connectors.treasury_securities.reference_connector import (
    TreasuryDirectSecuritiesConnector,
)
from app.modules.market.models import AcceptedFact, Dataset, Source, SourceArtifact
from app.modules.market.pipeline.treasury_securities_ingest import (
    TreasurySecurityIngestResult,
    TreasurySecurityIngestSkipped,
    ingest_treasury_security_reference_candidate,
)
from app.modules.reference.models import FiSovereignTerms, Instrument, InstrumentAlias, Issuer
from app.modules.rights.models import RightsGrant, RightsProfile

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "fixtures" / "treasurydirect_auctioned_note.json"
)
SEED_CUSIP = "91282CRF0"


async def _seed_reference_and_rights(session: AsyncSession) -> tuple[str, str]:
    issuer = Issuer(name="U.S. Department of the Treasury", country_code="US", status="ACTIVE")
    session.add(issuer)
    await session.flush()

    instrument = Instrument(
        issuer_id=issuer.id, instrument_type="FI_SOVEREIGN", name="4.625% Treasury Note 2036-08-15",
        currency_code="USD", status="ACTIVE",
    )
    session.add(instrument)
    await session.flush()

    session.add(
        InstrumentAlias(instrument_id=instrument.id, alias_type="CUSIP", alias_value=SEED_CUSIP)
    )
    session.add(
        FiSovereignTerms(
            instrument_id=instrument.id, coupon_rate=Decimal("4.625"),
            coupon_frequency="SEMI_ANNUAL", day_count_convention="ACT_ACT_TREASURY",
            first_issue_date=dt.date(2026, 10, 15), maturity_date=dt.date(2036, 8, 15),
            ex_dividend_days=0,
        )
    )

    profile = RightsProfile(code="treasurydirect.securities.test", status="ACTIVE")
    session.add(profile)
    await session.flush()
    session.add(RightsGrant(rights_profile_id=profile.id, action="store", permission_state="ALLOW"))
    await session.flush()

    return str(profile.id), str(instrument.id)


async def _seed_source_artifact(session: AsyncSession) -> SourceArtifact:
    source = Source(code="treasurydirect-test", name="TreasuryDirect (test)", status="ACTIVE")
    session.add(source)
    await session.flush()
    dataset = Dataset(
        source_id=source.id, code="treasurydirect.auctioned-securities",
        name="TreasuryDirect Auctioned Securities",
    )
    session.add(dataset)
    await session.flush()
    artifact = SourceArtifact(
        dataset_id=dataset.id, sha256="1" * 64, storage_ref="test://fixture",
        media_type="application/json", byte_length=len(FIXTURE_PATH.read_bytes()),
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    session.add(artifact)
    await session.flush()
    return artifact


def _parse_fixture_candidate() -> TreasurySecurityCandidate:
    connector = TreasuryDirectSecuritiesConnector(httpx.AsyncClient(), security_type="Note")
    payload = AcquiredPayload(
        raw_bytes=FIXTURE_PATH.read_bytes(), content_type="application/json", status_code=200,
        fetched_at=dt.datetime.now(dt.UTC), source_url="test",
    )
    candidates = connector.parse(payload)
    return next(
        c
        for c in candidates
        if not isinstance(c, RecordIssue)
        and c.cusip == SEED_CUSIP
        and c.security_term == "9-Year 10-Month"
    )


async def test_real_fixture_flows_through_to_an_accepted_fact(db_session: AsyncSession) -> None:
    rights_profile_id_str, instrument_id_str = await _seed_reference_and_rights(db_session)
    artifact = await _seed_source_artifact(db_session)
    candidate = _parse_fixture_candidate()

    result = await ingest_treasury_security_reference_candidate(
        db_session, candidate=candidate, source_artifact_id=artifact.id,
        source_code="treasurydirect", dataset_code="treasurydirect.auctioned-securities",
        rights_profile_id=uuid.UUID(rights_profile_id_str), fetched_at=dt.datetime.now(dt.UTC),
    )
    await db_session.commit()

    assert isinstance(result, TreasurySecurityIngestResult)
    assert result.reconciliation.decision == "ACCEPTED"

    fact = await db_session.get(AcceptedFact, result.reconciliation.accepted_fact_id)
    assert fact is not None
    assert fact.status == "ACTIVE"
    assert fact.subject_id == uuid.UUID(instrument_id_str)
    assert fact.value["coupon_rate"] == "4.625"
    assert fact.value["maturity_date"] == "2036-08-15"
    assert fact.value["security_type"] == "Note"


async def test_reingesting_the_same_snapshot_is_no_change(db_session: AsyncSession) -> None:
    rights_profile_id_str, _ = await _seed_reference_and_rights(db_session)
    artifact = await _seed_source_artifact(db_session)
    candidate = _parse_fixture_candidate()
    rights_profile_id = uuid.UUID(rights_profile_id_str)

    first = await ingest_treasury_security_reference_candidate(
        db_session, candidate=candidate, source_artifact_id=artifact.id,
        source_code="treasurydirect", dataset_code="treasurydirect.auctioned-securities",
        rights_profile_id=rights_profile_id, fetched_at=dt.datetime.now(dt.UTC),
    )
    await db_session.commit()

    second = await ingest_treasury_security_reference_candidate(
        db_session, candidate=candidate, source_artifact_id=artifact.id,
        source_code="treasurydirect", dataset_code="treasurydirect.auctioned-securities",
        rights_profile_id=rights_profile_id,
        fetched_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )
    await db_session.commit()

    assert isinstance(first, TreasurySecurityIngestResult)
    assert isinstance(second, TreasurySecurityIngestResult)
    assert first.observation_id == second.observation_id
    assert second.reconciliation.decision == "NO_CHANGE"


async def test_unresolved_cusip_is_skipped_not_guessed(db_session: AsyncSession) -> None:
    # Deliberately do NOT seed reference data - no instrument_alias exists
    # for this CUSIP, so the candidate must be skipped.
    profile = RightsProfile(code="treasurydirect.securities.test2", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    db_session.add(
        RightsGrant(rights_profile_id=profile.id, action="store", permission_state="ALLOW")
    )
    await db_session.flush()
    artifact = await _seed_source_artifact(db_session)
    candidate = _parse_fixture_candidate()

    result = await ingest_treasury_security_reference_candidate(
        db_session, candidate=candidate, source_artifact_id=artifact.id,
        source_code="treasurydirect", dataset_code="treasurydirect.auctioned-securities",
        rights_profile_id=profile.id, fetched_at=dt.datetime.now(dt.UTC),
    )

    assert isinstance(result, TreasurySecurityIngestSkipped)
    assert "instrument_alias" in result.reason


async def test_denied_rights_skips_without_touching_identity(db_session: AsyncSession) -> None:
    profile = RightsProfile(code="treasurydirect.securities.norights", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    artifact = await _seed_source_artifact(db_session)
    candidate = _parse_fixture_candidate()

    result = await ingest_treasury_security_reference_candidate(
        db_session, candidate=candidate, source_artifact_id=artifact.id,
        source_code="treasurydirect", dataset_code="treasurydirect.auctioned-securities",
        rights_profile_id=profile.id, fetched_at=dt.datetime.now(dt.UTC),
    )

    assert isinstance(result, TreasurySecurityIngestSkipped)
    assert "rights check denied" in result.reason
