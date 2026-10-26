"""Onboards real, currently-outstanding US Treasury Notes, Bonds, TIPS,
Bills (incl. Cash Management Bills) and Floating Rate Notes from
TreasuryDirect's live auctioned-securities feed.

Mirrors scripts/onboard_all_gilts.py's own shape and reasoning exactly:
deliberately NOT automatic identity resolution (DATA-002: no fuzzy
matching, ever) - this script IS the controlled onboarding action,
data-driven from a real live feed instead of hand-typed one security at a
time, each row it writes is real TreasuryDirect reference data, not
invented.

Five security types, each onboarded into its own terms-adapter table (see
reference/models.py's own docstrings, and connectors/treasury_securities/
mapping.py's parsing docstring): Note/Bond/TIPS -> FiSovereignTerms,
Bill (incl. CMBs) -> FiSovereignDiscountTerms, FRN -> FiSovereignFrnTerms.
A record TreasuryDirect reports with an unparseable/missing rate field is
skipped and reported, never guessed.

Lookback window is per-type, not one blanket constant - each type's own
maximum real-world tenor, not an arbitrary shared number:
- Bill: 400 days (max real tenor is 52 weeks - a 10-year window would
  onboard thousands of long-matured bills for no benefit).
- FRN: 800 days (Treasury's only FRN program is a single 2-year tenor).
- Note: 3660 days (~10 years, Note's own max tenor).
- Bond/TIPS: 10950 days (30 years, since both include a 30-year tenor).
  KNOWN API LIMIT (confirmed live, 2026-10-26): TreasuryDirect's
  /securities/auctioned endpoint caps its response at 250 records
  regardless of how large `days` is requested - Bond's real auction
  history is deep enough that this cap bites well inside 30 years
  (empirically, around 14-20 years back), so some older still-outstanding
  30-year bonds are NOT reachable through this endpoint at all. This is a
  real, documented source limitation (same "Twelve Data's free tier doesn't
  cover every symbol" category as CLAUDE.md's other sharp edges), not a
  bug in this script - a RecordIssue is never fabricated to compensate.

Also filters out any candidate whose maturity_date has already passed as
of onboarding time - widening the lookback window (above) means auction
dates further in the past are now in scope, several of which belong to
short-tenor securities (Bills, 2/3-year Notes) that have since matured.
"Currently outstanding" is the scope this whole pilot claims (see
reference_connector.py's own docstring); onboarding an already-matured
instrument as if it were live would violate that, not extend it.

Run with (after `uv run python -m scripts.seed_dev`):

    uv run python -m scripts.onboard_all_treasury_securities

Idempotent: safe to run repeatedly - every instrument/alias/terms insert
and every accepted-fact ingest is already guarded by its own "does this
exist" check, same as onboard_all_gilts.py.

Does NOT compute any priced calculation for the newly-onboarded Notes/
Bonds/TIPS - that's separate calculation-pipeline work
(calculation/specs/treasury_price_from_curve_v1). Bills and FRNs have no
priced calculation at all yet, by design (see that spec's own docstring on
why it's fixed-coupon-only, same scope boundary gilt_price_from_curve_v1
already draws for UK index-linked gilts).
"""

import asyncio
import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.modules.market.connectors.base import Quarantined, validate_and_parse
from app.modules.market.connectors.treasury_securities.mapping import (
    RecordIssue,
    TreasuryDiscountCandidate,
    TreasuryFrnCandidate,
    TreasurySecurityCandidate,
)
from app.modules.market.connectors.treasury_securities.reference_connector import (
    DATASET_CODE,
    TreasuryDirectSecuritiesConnector,
)
from app.modules.market.models import Dataset, Source, SourceArtifact
from app.modules.market.pipeline.treasury_securities_ingest import (
    ingest_treasury_discount_reference_candidate,
    ingest_treasury_frn_reference_candidate,
    ingest_treasury_security_reference_candidate,
)
from app.modules.reference.models import (
    FiSovereignDiscountTerms,
    FiSovereignFrnTerms,
    FiSovereignTerms,
    Instrument,
    InstrumentAlias,
    Issuer,
)
from app.modules.rights.models import RightsProfile

_ISSUER_NAME = "U.S. Department of the Treasury"
# Distinct from gilts' ACT_ACT_ICMA - a real, different convention name,
# not a reused label.
_DAY_COUNT_CONVENTION = "ACT_ACT_TREASURY"
# The standard, market-wide T-bill discount convention - not derived from
# the TreasuryDirect feed itself, a named market convention like
# ACT_ACT_TREASURY above.
_BILL_DAY_COUNT_CONVENTION = "ACT_360"
# US Treasuries have no UK-style ex-dividend period - 0 means not
# applicable, not a guessed value.
_EX_DIVIDEND_DAYS = 0

# Per-type lookback - see module docstring for why each value is sized to
# that type's own real-world maximum tenor, not a shared constant.
_SECURITY_TYPE_LOOKBACK_DAYS: dict[str, int] = {
    "Note": 3660,
    "Bond": 10950,
    "TIPS": 10950,
    "Bill": 400,
    "FRN": 800,
}


def _already_matured(maturity_date: dt.date, *, today: dt.date) -> bool:
    return maturity_date < today


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


async def _existing_instrument_for_cusip(
    session: AsyncSession, cusip: str
) -> Instrument | None:
    existing_alias = (
        await session.execute(
            select(InstrumentAlias).where(
                InstrumentAlias.alias_type == "CUSIP", InstrumentAlias.alias_value == cusip
            )
        )
    ).scalar_one_or_none()
    if existing_alias is None:
        return None
    instrument = await session.get(Instrument, existing_alias.instrument_id)
    assert instrument is not None
    return instrument


async def _get_or_create_fixed_coupon_instrument(
    session: AsyncSession, *, issuer: Issuer, candidate: TreasurySecurityCandidate
) -> tuple[Instrument, bool]:
    existing = await _existing_instrument_for_cusip(session, candidate.cusip)
    if existing is not None:
        return existing, False

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


async def _get_or_create_discount_instrument(
    session: AsyncSession, *, issuer: Issuer, candidate: TreasuryDiscountCandidate
) -> tuple[Instrument, bool]:
    existing = await _existing_instrument_for_cusip(session, candidate.cusip)
    if existing is not None:
        return existing, False

    kind = "Cash Management Bill" if candidate.is_cash_management_bill else "Treasury Bill"
    instrument_name = f"{kind} {candidate.maturity_date.isoformat()}"
    instrument = Instrument(
        issuer_id=issuer.id, instrument_type="FI_SOVEREIGN_DISCOUNT", name=instrument_name,
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
        FiSovereignDiscountTerms(
            instrument_id=instrument.id, high_rate=candidate.high_rate,
            investment_rate=candidate.investment_rate,
            is_cash_management_bill=candidate.is_cash_management_bill,
            day_count_convention=_BILL_DAY_COUNT_CONVENTION,
            first_issue_date=candidate.issue_date, maturity_date=candidate.maturity_date,
        )
    )
    return instrument, True


async def _get_or_create_frn_instrument(
    session: AsyncSession, *, issuer: Issuer, candidate: TreasuryFrnCandidate
) -> tuple[Instrument, bool]:
    existing = await _existing_instrument_for_cusip(session, candidate.cusip)
    if existing is not None:
        return existing, False

    instrument_name = f"FRN +{candidate.spread}% {candidate.maturity_date.isoformat()}"
    instrument = Instrument(
        issuer_id=issuer.id, instrument_type="FI_SOVEREIGN_FRN", name=instrument_name,
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
        FiSovereignFrnTerms(
            instrument_id=instrument.id, spread=candidate.spread,
            index_determination_rate=candidate.index_determination_rate,
            frequency_of_interest_payments=candidate.frequency_of_interest_payments.upper(),
            day_count_convention=_DAY_COUNT_CONVENTION,
            first_issue_date=candidate.issue_date, maturity_date=candidate.maturity_date,
        )
    )
    return instrument, True


@dataclass(frozen=True)
class _Counts:
    onboarded: int = 0
    skipped: int = 0
    matured: int = 0
    ingested_facts: int = 0


async def onboard() -> None:
    factory = get_session_factory()
    today = dt.datetime.now(dt.UTC).date()
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

        onboarded = skipped = matured = ingested_facts = 0
        async with httpx.AsyncClient() as client:
            for security_type, days in _SECURITY_TYPE_LOOKBACK_DAYS.items():
                connector = TreasuryDirectSecuritiesConnector(
                    client, security_type=security_type, days=days
                )
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
                    if _already_matured(record.maturity_date, today=today):
                        matured += 1
                        continue

                    created: bool
                    ingest_result: Any
                    if isinstance(record, TreasurySecurityCandidate):
                        instrument, created = await _get_or_create_fixed_coupon_instrument(
                            session, issuer=issuer, candidate=record
                        )
                        if created:
                            onboarded += 1
                            print(f"  + {instrument.name} ({record.cusip})")
                        await session.commit()
                        ingest_result = await ingest_treasury_security_reference_candidate(
                            session, candidate=record, source_artifact_id=artifact.id,
                            source_code="treasurydirect", dataset_code=DATASET_CODE,
                            rights_profile_id=rights.id, fetched_at=payload.fetched_at,
                        )
                    elif isinstance(record, TreasuryDiscountCandidate):
                        instrument, created = await _get_or_create_discount_instrument(
                            session, issuer=issuer, candidate=record
                        )
                        if created:
                            onboarded += 1
                            print(f"  + {instrument.name} ({record.cusip})")
                        await session.commit()
                        ingest_result = await ingest_treasury_discount_reference_candidate(
                            session, candidate=record, source_artifact_id=artifact.id,
                            source_code="treasurydirect", dataset_code=DATASET_CODE,
                            rights_profile_id=rights.id, fetched_at=payload.fetched_at,
                        )
                    else:
                        assert isinstance(record, TreasuryFrnCandidate)
                        instrument, created = await _get_or_create_frn_instrument(
                            session, issuer=issuer, candidate=record
                        )
                        if created:
                            onboarded += 1
                            print(f"  + {instrument.name} ({record.cusip})")
                        await session.commit()
                        ingest_result = await ingest_treasury_frn_reference_candidate(
                            session, candidate=record, source_artifact_id=artifact.id,
                            source_code="treasurydirect", dataset_code=DATASET_CODE,
                            rights_profile_id=rights.id, fetched_at=payload.fetched_at,
                        )
                    await session.commit()
                    ingested_facts += 1
                    # IngestResult/IngestSkipped both fine - already-current isn't an error.
                    _ = ingest_result

        print(
            f"\nOnboarded {onboarded} new instruments, ingested reference facts for "
            f"{ingested_facts} records. Skipped {skipped} (unparseable/floating-mismatch), "
            f"{matured} already matured."
        )


if __name__ == "__main__":
    asyncio.run(onboard())
