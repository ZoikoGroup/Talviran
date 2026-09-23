"""Onboards every CONVENTIONAL gilt in the real, legitimately-captured
DMO fixture (tests/fixtures/dmo_gilts_in_issue.xml - see
connectors/dmo_gilts/client.py's docstring for why this is a captured
fixture rather than a live automated call: DMO's endpoint is behind bot
protection for non-browser clients).

Deliberately NOT automatic identity resolution - see
scripts/seed_dev.py's own docstring on why reference data is onboarded
here, explicitly, rather than auto-created by the ingest pipeline
(app.modules.market.pipeline.identity_resolution's docstring: no fuzzy
matching, ever - an unmatched instrument goes to ops review, not a
guess). This script IS that deliberate onboarding action, just
data-driven from a real captured feed instead of hand-typed one gilt at
a time - each row it writes is real DMO reference data, not invented.

Only Conventional gilts (not Index-linked) - the calculation engine
(gilt_price_from_curve_v1) was built and golden-tested against
conventional fixed-coupon math only; index-linked gilts need their own
uplift-adjusted methodology and golden corpus, out of scope here. A
record whose coupon can't be parsed (mapping.parse_coupon_rate
returning None) is skipped and reported, never guessed.

Run with:

    uv run python -m scripts.onboard_all_gilts

Idempotent: safe to run repeatedly - every instrument/alias/terms
insert and every accepted-fact ingest is already guarded by its own
"does this exist" check (Instrument/InstrumentAlias here,
ingest_gilt_reference_candidate's own IngestSkipped/reconciliation
logic for the accepted facts).

Does NOT compute model-implied clean prices for the newly-onboarded
gilts - that's a separate calculation-pipeline run (curve_pricing),
intentionally out of scope for a reference-data onboarding pass. A
newly-onboarded gilt's facts render correctly with no price row until
that pipeline is run for it, the same graceful "row omitted, not
invented" behavior the facts table already has for any instrument
lacking a priced result.
"""

import asyncio
import datetime as dt
import hashlib
import uuid
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.modules.market.connectors.base import AcquiredPayload
from app.modules.market.connectors.dmo_gilts.mapping import (
    GILT_TYPE_CONVENTIONAL,
    GiltReferenceCandidate,
    RecordIssue,
)
from app.modules.market.connectors.dmo_gilts.reference_connector import DMOGiltsReferenceConnector
from app.modules.market.models import Dataset, Source, SourceArtifact
from app.modules.market.pipeline.stages import ingest_gilt_reference_candidate
from app.modules.reference.models import FiSovereignTerms, Instrument, InstrumentAlias, Issuer
from app.modules.rights.models import RightsProfile

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
DMO_FIXTURE_PATH = _BACKEND_ROOT / "tests" / "fixtures" / "dmo_gilts_in_issue.xml"
_ISSUER_NAME = "HM Treasury"
_DAY_COUNT_CONVENTION = "ACT_ACT_ICMA"  # UK gilt market convention, all conventional gilts
_EX_DIVIDEND_DAYS = 7  # UK gilt market convention (DMO's own published methodology)


async def _get_or_create_issuer(session: AsyncSession) -> Issuer:
    issuer = (
        await session.execute(select(Issuer).where(Issuer.name == _ISSUER_NAME))
    ).scalar_one_or_none()
    if issuer is None:
        issuer = Issuer(name=_ISSUER_NAME, country_code="GB", status="ACTIVE")
        session.add(issuer)
        await session.flush()
        print(f"  + issuer {_ISSUER_NAME} (GB)")
    return issuer


async def _get_or_create_instrument(
    session: AsyncSession, *, issuer: Issuer, candidate: GiltReferenceCandidate
) -> tuple[Instrument, bool]:
    existing_alias = (
        await session.execute(
            select(InstrumentAlias).where(
                InstrumentAlias.alias_type == "ISIN", InstrumentAlias.alias_value == candidate.isin
            )
        )
    ).scalar_one_or_none()
    if existing_alias is not None:
        instrument = await session.get(Instrument, existing_alias.instrument_id)
        assert instrument is not None
        return instrument, False

    instrument = Instrument(
        issuer_id=issuer.id, instrument_type="FI_SOVEREIGN", name=candidate.instrument_name,
        currency_code="GBP", status="ACTIVE",
    )
    session.add(instrument)
    await session.flush()
    session.add(
        InstrumentAlias(instrument_id=instrument.id, alias_type="ISIN", alias_value=candidate.isin)
    )
    assert candidate.coupon_rate is not None  # filtered by the caller before this is reached
    session.add(
        FiSovereignTerms(
            instrument_id=instrument.id, coupon_rate=candidate.coupon_rate,
            coupon_frequency="SEMI_ANNUAL", day_count_convention=_DAY_COUNT_CONVENTION,
            first_issue_date=candidate.first_issue_date, maturity_date=candidate.redemption_date,
            ex_dividend_days=_EX_DIVIDEND_DAYS,
        )
    )
    return instrument, True


async def onboard() -> None:
    factory = get_session_factory()
    async with factory() as session:
        dmo_rights = (
            await session.execute(select(RightsProfile).where(RightsProfile.code == "uk-dmo.gilts"))
        ).scalar_one_or_none()
        if dmo_rights is None:
            raise SystemExit("uk-dmo.gilts rights profile not seeded - run scripts.seed_dev first.")

        source = (
            await session.execute(select(Source).where(Source.code == "uk-dmo"))
        ).scalar_one_or_none()
        if source is None:
            source = Source(code="uk-dmo", name="UK DMO")
            session.add(source)
            await session.flush()

        dataset = (
            await session.execute(select(Dataset).where(Dataset.code == "gilts-in-issue"))
        ).scalar_one_or_none()
        if dataset is None:
            dataset = Dataset(source_id=source.id, code="gilts-in-issue", name="Gilts in Issue")
            session.add(dataset)
            await session.flush()

        fixture_bytes = DMO_FIXTURE_PATH.read_bytes()
        artifact = SourceArtifact(
            dataset_id=dataset.id, sha256=hashlib.sha256(fixture_bytes).hexdigest(),
            storage_ref=f"dev-fixture://dmo/{uuid.uuid4().hex[:8]}",
            media_type="text/xml", byte_length=len(fixture_bytes),
            retrieved_at=dt.datetime.now(dt.UTC),
        )
        session.add(artifact)
        await session.flush()

        connector = DMOGiltsReferenceConnector(httpx.AsyncClient())
        payload = AcquiredPayload(
            raw_bytes=fixture_bytes, content_type="text/xml", status_code=200,
            fetched_at=dt.datetime.now(dt.UTC), source_url="dev-fixture",
        )
        records = connector.parse(payload)

        issuer = await _get_or_create_issuer(session)
        await session.commit()

        onboarded = skipped_index_linked = skipped_unparseable = 0
        ingested_facts = 0
        for record in records:
            if isinstance(record, RecordIssue):
                skipped_unparseable += 1
                continue
            if record.gilt_type != GILT_TYPE_CONVENTIONAL:
                skipped_index_linked += 1
                continue
            if record.coupon_rate is None:
                skipped_unparseable += 1
                print(f"  ! unparseable coupon for {record.instrument_name} ({record.isin})")
                continue

            instrument, created = await _get_or_create_instrument(
                session, issuer=issuer, candidate=record
            )
            if created:
                onboarded += 1
                print(f"  + {record.instrument_name} ({record.isin})")
            await session.commit()

            result = await ingest_gilt_reference_candidate(
                session, candidate=record, source_artifact_id=artifact.id,
                source_code="uk-dmo", dataset_code="gilts-in-issue",
                rights_profile_id=dmo_rights.id, fetched_at=payload.fetched_at,
            )
            await session.commit()
            ingested_facts += 1
            _ = result  # IngestResult/IngestSkipped both fine - already-current isn't an error

        print(
            f"\nOnboarded {onboarded} new instruments, ingested reference facts for "
            f"{ingested_facts} conventional gilts. Skipped {skipped_index_linked} "
            f"index-linked, {skipped_unparseable} unparseable."
        )


if __name__ == "__main__":
    asyncio.run(onboard())
