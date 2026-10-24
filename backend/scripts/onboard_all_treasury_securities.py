"""Onboards real, currently-outstanding US Treasury Notes, Bonds and TIPS
from TreasuryDirect's live auctioned-securities feed (the last
DEFAULT_LOOKBACK_DAYS days of auctions — see reference_connector.py's own
docstring for why that's a meaningful "real current universe" pilot, not
an attempt at the full historical CUSIP archive).

Mirrors scripts/onboard_all_gilts.py's own shape and reasoning exactly:
deliberately NOT automatic identity resolution (DATA-002: no fuzzy
matching, ever) - this script IS the controlled onboarding action,
data-driven from a real live feed instead of hand-typed one security at a
time, each row it writes is real TreasuryDirect reference data, not
invented.

Only Note/Bond/TIPS - Bills (discount, no coupon) and FRNs (floating
spread, no fixed coupon) don't fit FiSovereignTerms' fixed-coupon shape;
see connectors/treasury_securities/mapping.py's own scope-decision
docstring. A record TreasuryDirect reports as a floating-rate note, or
whose coupon can't be parsed, is skipped and reported, never guessed.

Run with (after `uv run python -m scripts.seed_dev`):

    uv run python -m scripts.onboard_all_treasury_securities

Idempotent: safe to run repeatedly - every instrument/alias/terms insert
and every accepted-fact ingest is already guarded by its own "does this
exist" check, same as onboard_all_gilts.py.

Does NOT compute any priced calculation for the newly-onboarded
securities - that's separate, out-of-scope calculation-pipeline work
(Talvrin has no Treasury-side pricing calc spec yet at all, unlike gilts'
gilt_price_from_curve_v1). A newly-onboarded security's reference facts
render correctly with no price row until one exists.
"""

import asyncio
import hashlib
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.modules.market.connectors.base import Quarantined, validate_and_parse
from app.modules.market.connectors.treasury_securities.mapping import (
    RecordIssue,
    TreasurySecurityCandidate,
)
from app.modules.market.connectors.treasury_securities.reference_connector import (
    DATASET_CODE,
    TreasuryDirectSecuritiesConnector,
)
from app.modules.market.models import Dataset, Source, SourceArtifact
from app.modules.market.pipeline.treasury_securities_ingest import (
    ingest_treasury_security_reference_candidate,
)
from app.modules.reference.models import FiSovereignTerms, Instrument, InstrumentAlias, Issuer
from app.modules.rights.models import RightsProfile

_ISSUER_NAME = "U.S. Department of the Treasury"
# Distinct from gilts' ACT_ACT_ICMA - a real, different convention name,
# not a reused label.
_DAY_COUNT_CONVENTION = "ACT_ACT_TREASURY"
# US Treasuries have no UK-style ex-dividend period - 0 means not
# applicable, not a guessed value.
_EX_DIVIDEND_DAYS = 0
_SECURITY_TYPES_ONBOARDED = ("Note", "Bond", "TIPS")


async def _get_or_create_issuer(session: AsyncSession) -> Issuer:
    issuer = (
        await session.execute(select(Issuer).where(Issuer.name == _ISSUER_NAME))
    ).scalar_one_or_none()
    if issuer is None:
        issuer = Issuer(name=_ISSUER_NAME, country_code="US", status="ACTIVE")
        session.add(issuer)
        await session.flush()
        print(f"  + issuer {_ISSUER_NAME} (US)")
    return issuer


async def _get_or_create_instrument(
    session: AsyncSession, *, issuer: Issuer, candidate: TreasurySecurityCandidate
) -> tuple[Instrument, bool]:
    existing_alias = (
        await session.execute(
            select(InstrumentAlias).where(
                InstrumentAlias.alias_type == "CUSIP",
                InstrumentAlias.alias_value == candidate.cusip,
            )
        )
    ).scalar_one_or_none()
    if existing_alias is not None:
        instrument = await session.get(Instrument, existing_alias.instrument_id)
        assert instrument is not None
        return instrument, False

    instrument_name = (
        f"{candidate.coupon_rate}% Treasury {candidate.security_type} "
        f"{candidate.maturity_date.isoformat()}"
    )
    instrument = Instrument(
        issuer_id=issuer.id, instrument_type="FI_SOVEREIGN", name=instrument_name,
        currency_code="USD", status="ACTIVE",
    )
    session.add(instrument)
    await session.flush()
    session.add(
        InstrumentAlias(
            instrument_id=instrument.id, alias_type="CUSIP", alias_value=candidate.cusip
        )
    )
    session.add(
        FiSovereignTerms(
            instrument_id=instrument.id, coupon_rate=candidate.coupon_rate,
            coupon_frequency="SEMI_ANNUAL", day_count_convention=_DAY_COUNT_CONVENTION,
            first_issue_date=candidate.issue_date, maturity_date=candidate.maturity_date,
            ex_dividend_days=_EX_DIVIDEND_DAYS,
        )
    )
    return instrument, True


async def onboard() -> None:
    factory = get_session_factory()
    async with factory() as session:
        rights = (
            await session.execute(
                select(RightsProfile).where(RightsProfile.code == "treasurydirect.securities")
            )
        ).scalar_one_or_none()
        if rights is None:
            raise SystemExit(
                "treasurydirect.securities rights profile not seeded - "
                "run scripts.seed_dev first."
            )

        source = (
            await session.execute(select(Source).where(Source.code == "treasurydirect"))
        ).scalar_one_or_none()
        if source is None:
            source = Source(code="treasurydirect", name="TreasuryDirect")
            session.add(source)
            await session.flush()

        dataset = (
            await session.execute(select(Dataset).where(Dataset.code == DATASET_CODE))
        ).scalar_one_or_none()
        if dataset is None:
            dataset = Dataset(
                source_id=source.id, code=DATASET_CODE, name="TreasuryDirect Auctioned Securities"
            )
            session.add(dataset)
            await session.flush()

        issuer = await _get_or_create_issuer(session)
        await session.commit()

        onboarded = skipped = ingested_facts = 0
        async with httpx.AsyncClient() as client:
            for security_type in _SECURITY_TYPES_ONBOARDED:
                connector = TreasuryDirectSecuritiesConnector(client, security_type=security_type)
                try:
                    payload = await connector.acquire()
                except httpx.HTTPError as exc:
                    print(f"TreasuryDirect {security_type}: live fetch failed ({exc}).")
                    continue

                candidates_or_quarantine = validate_and_parse(connector, payload)
                if isinstance(candidates_or_quarantine, Quarantined):
                    print(
                        f"TreasuryDirect {security_type}: quarantined "
                        f"({candidates_or_quarantine.reasons})."
                    )
                    continue

                artifact = SourceArtifact(
                    dataset_id=dataset.id, sha256=hashlib.sha256(payload.raw_bytes).hexdigest(),
                    storage_ref=f"dev-live://treasurydirect/{security_type}/{uuid.uuid4().hex[:8]}",
                    media_type=payload.content_type or "application/json",
                    byte_length=len(payload.raw_bytes), retrieved_at=payload.fetched_at,
                )
                session.add(artifact)
                await session.flush()

                for record in candidates_or_quarantine:
                    if isinstance(record, RecordIssue):
                        skipped += 1
                        continue

                    instrument, created = await _get_or_create_instrument(
                        session, issuer=issuer, candidate=record
                    )
                    if created:
                        onboarded += 1
                        print(f"  + {instrument.name} ({record.cusip})")
                    await session.commit()

                    result = await ingest_treasury_security_reference_candidate(
                        session, candidate=record, source_artifact_id=artifact.id,
                        source_code="treasurydirect", dataset_code=DATASET_CODE,
                        rights_profile_id=rights.id, fetched_at=payload.fetched_at,
                    )
                    await session.commit()
                    ingested_facts += 1
                    # IngestResult/IngestSkipped both fine - already-current isn't an error.
                    _ = result

        print(
            f"\nOnboarded {onboarded} new instruments, ingested reference facts for "
            f"{ingested_facts} Note/Bond/TIPS records. Skipped {skipped} "
            f"(floating-rate or unparseable)."
        )


if __name__ == "__main__":
    asyncio.run(onboard())
