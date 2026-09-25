"""End-to-end: a Twelve Data candidate -> identity resolve -> equity ingest
-> a real accepted_fact row. Proves the Twelve Data connector and the
shared ingest_and_reconcile tail actually work together, not just each in
isolation — and that an unresolved ticker is skipped, never guessed.
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.connectors.twelve_data_equity.mapping import EquityEodPriceCandidate
from app.modules.market.models import AcceptedFact, Dataset, Source, SourceArtifact
from app.modules.market.pipeline.equity_ingest import (
    EquityIngestSkipped,
    equity_alias_value,
    ingest_equity_eod_price_candidate,
)
from app.modules.market.pipeline.ingest_tail import IngestOutcome
from app.modules.reference.models import Instrument, InstrumentAlias, Issuer
from app.modules.rights.models import RightsGrant, RightsProfile

SEED_SYMBOL = "VOD"
SEED_EXCHANGE = "LSE"


async def _seed_reference_and_rights(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """Mirrors scripts/seed_dev.py's pilot-equity onboarding, scoped to
    this test's own session/transaction — same pattern as the gilt
    pipeline's own integration test.
    """
    issuer = Issuer(
        name="Vodafone Group Public Limited Company", country_code="GB", status="ACTIVE"
    )
    session.add(issuer)
    await session.flush()

    instrument = Instrument(
        issuer_id=issuer.id,
        instrument_type="EQUITY_COMMON",
        name="Vodafone Group Public Limited Company",
        currency_code="GBP",
        status="ACTIVE",
    )
    session.add(instrument)
    await session.flush()

    session.add(
        InstrumentAlias(
            instrument_id=instrument.id,
            alias_type="TICKER",
            alias_value=equity_alias_value(SEED_EXCHANGE, SEED_SYMBOL),
        )
    )

    profile = RightsProfile(code=f"twelve-data.equity.test.{uuid.uuid4().hex[:8]}", status="ACTIVE")
    session.add(profile)
    await session.flush()
    session.add(
        RightsGrant(rights_profile_id=profile.id, action="store", permission_state="ALLOW")
    )
    await session.flush()

    return profile.id, instrument.id


async def _seed_source_artifact(session: AsyncSession) -> SourceArtifact:
    source = Source(code=f"twelve-data-test-{uuid.uuid4().hex[:8]}", name="Twelve Data (test)")
    session.add(source)
    await session.flush()
    dataset = Dataset(source_id=source.id, code="eod-price", name="Equity EOD Price")
    session.add(dataset)
    await session.flush()
    artifact = SourceArtifact(
        dataset_id=dataset.id,
        sha256="5" * 64,
        storage_ref="test://twelve-data-fixture",
        media_type="application/json",
        byte_length=1,
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    session.add(artifact)
    await session.flush()
    return artifact


def _candidate(trade_date: dt.date = dt.date(2026, 9, 17)) -> EquityEodPriceCandidate:
    return EquityEodPriceCandidate(
        symbol=SEED_SYMBOL, exchange=SEED_EXCHANGE, trade_date=trade_date,
        close_price=Decimal("69.25"), currency_code="GBP",
    )


async def test_resolved_ticker_flows_through_to_an_accepted_fact(db_session: AsyncSession) -> None:
    rights_profile_id, instrument_id = await _seed_reference_and_rights(db_session)
    artifact = await _seed_source_artifact(db_session)
    fetched_at = dt.datetime.now(dt.UTC)

    result = await ingest_equity_eod_price_candidate(
        db_session,
        candidate=_candidate(),
        source_artifact_id=artifact.id,
        source_code="twelve-data",
        dataset_code="eod-price",
        rights_profile_id=rights_profile_id,
        fetched_at=fetched_at,
    )
    await db_session.commit()

    assert isinstance(result, IngestOutcome)
    assert result.reconciliation.decision == "ACCEPTED"

    fact = await db_session.get(AcceptedFact, result.reconciliation.accepted_fact_id)
    assert fact is not None
    assert fact.status == "ACTIVE"
    assert fact.subject_type == "INSTRUMENT"
    assert fact.subject_id == instrument_id
    assert fact.value == {
        "symbol": "VOD", "exchange": "LSE", "close_price": "69.25",
        "currency_code": "GBP",
    }


async def test_two_different_trading_days_coexist_without_superseding(
    db_session: AsyncSession,
) -> None:
    rights_profile_id, instrument_id = await _seed_reference_and_rights(db_session)
    artifact = await _seed_source_artifact(db_session)
    fetched_at = dt.datetime.now(dt.UTC)

    day1 = _candidate(dt.date(2026, 9, 16))
    day2 = EquityEodPriceCandidate(
        symbol=day1.symbol, exchange=day1.exchange, trade_date=dt.date(2026, 9, 17),
        close_price=day1.close_price + 1, currency_code=day1.currency_code,
    )

    first = await ingest_equity_eod_price_candidate(
        db_session, candidate=day1, source_artifact_id=artifact.id, source_code="twelve-data",
        dataset_code="eod-price", rights_profile_id=rights_profile_id, fetched_at=fetched_at,
    )
    await db_session.commit()
    second = await ingest_equity_eod_price_candidate(
        db_session, candidate=day2, source_artifact_id=artifact.id, source_code="twelve-data",
        dataset_code="eod-price", rights_profile_id=rights_profile_id, fetched_at=fetched_at,
    )
    await db_session.commit()

    assert isinstance(first, IngestOutcome) and isinstance(second, IngestOutcome)
    assert first.reconciliation.decision == "ACCEPTED"
    assert second.reconciliation.decision == "ACCEPTED"

    facts = (
        await db_session.execute(
            select(AcceptedFact).where(AcceptedFact.subject_id == instrument_id)
        )
    ).scalars().all()
    assert len(facts) == 2
    assert all(f.status == "ACTIVE" for f in facts), "neither day should supersede the other"


async def test_reingesting_the_same_day_is_no_change(db_session: AsyncSession) -> None:
    rights_profile_id, _ = await _seed_reference_and_rights(db_session)
    artifact = await _seed_source_artifact(db_session)
    candidate = _candidate()

    first = await ingest_equity_eod_price_candidate(
        db_session, candidate=candidate, source_artifact_id=artifact.id, source_code="twelve-data",
        dataset_code="eod-price", rights_profile_id=rights_profile_id,
        fetched_at=dt.datetime.now(dt.UTC),
    )
    await db_session.commit()
    second = await ingest_equity_eod_price_candidate(
        db_session, candidate=candidate, source_artifact_id=artifact.id, source_code="twelve-data",
        dataset_code="eod-price", rights_profile_id=rights_profile_id,
        fetched_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )
    await db_session.commit()

    assert isinstance(first, IngestOutcome) and isinstance(second, IngestOutcome)
    assert first.observation_id == second.observation_id
    assert second.reconciliation.decision == "NO_CHANGE"


async def test_unresolved_ticker_is_skipped_not_guessed(db_session: AsyncSession) -> None:
    # Deliberately do NOT seed any reference data — no instrument_alias
    # exists for this ticker, so the candidate must be skipped, never
    # fuzzy-matched to some other company.
    profile = RightsProfile(code=f"twelve-data.norights.{uuid.uuid4().hex[:8]}", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    db_session.add(
        RightsGrant(rights_profile_id=profile.id, action="store", permission_state="ALLOW")
    )
    await db_session.flush()
    artifact = await _seed_source_artifact(db_session)

    result = await ingest_equity_eod_price_candidate(
        db_session, candidate=_candidate(), source_artifact_id=artifact.id,
        source_code="twelve-data", dataset_code="eod-price", rights_profile_id=profile.id,
        fetched_at=dt.datetime.now(dt.UTC),
    )

    assert isinstance(result, EquityIngestSkipped)
    assert "instrument_alias" in result.reason


async def test_denied_rights_skips_ingest(db_session: AsyncSession) -> None:
    _, _ = await _seed_reference_and_rights(db_session)
    profile = RightsProfile(code=f"twelve-data.denied.{uuid.uuid4().hex[:8]}", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    artifact = await _seed_source_artifact(db_session)

    result = await ingest_equity_eod_price_candidate(
        db_session, candidate=_candidate(), source_artifact_id=artifact.id,
        source_code="twelve-data", dataset_code="eod-price", rights_profile_id=profile.id,
        fetched_at=dt.datetime.now(dt.UTC),
    )

    assert isinstance(result, EquityIngestSkipped)
    assert "rights check denied" in result.reason
