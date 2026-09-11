"""Seeds the minimum governance + reference rows needed for the reference
endpoints and the P1 week 9 ingest pipeline to actually run instead of
failing closed by (correct) default. Run with:

    uv run python -m scripts.seed_dev

Idempotent: safe to run repeatedly against the same dev database — every
insert is guarded by a "does this already exist" check first.

Seeds the reference registry (issuer/instrument/alias/terms) for exactly
one gilt — the corrected seed instrument, ISIN GB0032452392 (4 1/4%
Treasury Stock 2036; see memory: the ISIN originally assumed,
GB00BDX8CX86, is a real but unrelated index-linked 2068 gilt). Reference
data is onboarded here deliberately, not auto-created by the connector —
see app.modules.market.pipeline.identity_resolution's docstring for why.
"""

import asyncio
import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.modules.policy.models import ActivationRecord, CapabilityStatus
from app.modules.reference.models import FiSovereignTerms, Instrument, InstrumentAlias, Issuer
from app.modules.reference.service import REFERENCE_RIGHTS_PROFILE_CODE
from app.modules.rights.models import RightsGrant, RightsProfile

_JURISDICTION = "GB"
_CAPABILITIES = ["reference.issuers.read", "reference.instruments.read"]

UK_DMO_GILTS_RIGHTS_PROFILE_CODE = "uk-dmo.gilts"
SEED_GILT_ISIN = "GB0032452392"


async def _seed_capability_statuses(session: AsyncSession) -> None:
    for code in _CAPABILITIES:
        existing = (
            await session.execute(
                select(CapabilityStatus).where(
                    CapabilityStatus.capability_code == code,
                    CapabilityStatus.jurisdiction_code.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                CapabilityStatus(capability_code=code, jurisdiction_code=None, status="AVAILABLE")
            )
            print(f"  + capability_status {code} -> AVAILABLE")


async def _seed_activation_record(session: AsyncSession) -> None:
    existing = (
        await session.execute(
            select(ActivationRecord).where(
                ActivationRecord.jurisdiction_code == _JURISDICTION,
                ActivationRecord.status == "ACTIVE",
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            ActivationRecord(
                jurisdiction_code=_JURISDICTION,
                operating_entity="Talvrin Dev",
                status="ACTIVE",
                effective_from=dt.datetime.now(dt.UTC) - dt.timedelta(days=1),
                effective_to=None,
            )
        )
        print(f"  + activation_record {_JURISDICTION} -> ACTIVE")


async def _seed_rights_profile(session: AsyncSession, code: str, actions: list[str]) -> None:
    profile = (
        await session.execute(select(RightsProfile).where(RightsProfile.code == code))
    ).scalar_one_or_none()
    if profile is None:
        profile = RightsProfile(code=code, status="ACTIVE")
        session.add(profile)
        await session.flush()
        print(f"  + rights_profile {code} -> ACTIVE")

    for action in actions:
        grant = (
            await session.execute(
                select(RightsGrant).where(
                    RightsGrant.rights_profile_id == profile.id,
                    RightsGrant.action == action,
                )
            )
        ).scalar_one_or_none()
        if grant is None:
            session.add(
                RightsGrant(rights_profile_id=profile.id, action=action, permission_state="ALLOW")
            )
            print(f"  + rights_grant {code}.{action} -> ALLOW")


async def _seed_gilt_reference_data(session: AsyncSession) -> None:
    existing_alias = (
        await session.execute(
            select(InstrumentAlias).where(
                InstrumentAlias.alias_type == "ISIN", InstrumentAlias.alias_value == SEED_GILT_ISIN
            )
        )
    ).scalar_one_or_none()
    if existing_alias is not None:
        return

    issuer = (
        await session.execute(select(Issuer).where(Issuer.name == "HM Treasury"))
    ).scalar_one_or_none()
    if issuer is None:
        issuer = Issuer(name="HM Treasury", country_code="GB", status="ACTIVE")
        session.add(issuer)
        await session.flush()
        print("  + issuer HM Treasury (GB)")

    instrument = Instrument(
        issuer_id=issuer.id,
        instrument_type="FI_SOVEREIGN",
        name="4 1/4% Treasury Stock 2036",
        currency_code="GBP",
        status="ACTIVE",
    )
    session.add(instrument)
    await session.flush()
    print(f"  + instrument {instrument.name} ({instrument.id})")

    session.add(
        InstrumentAlias(instrument_id=instrument.id, alias_type="ISIN", alias_value=SEED_GILT_ISIN)
    )
    print(f"  + instrument_alias ISIN {SEED_GILT_ISIN}")

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
    print(f"  + fi_sovereign_terms for {instrument.name}")


async def seed() -> None:
    factory = get_session_factory()
    async with factory() as session:
        await _seed_capability_statuses(session)
        await _seed_activation_record(session)
        await _seed_rights_profile(session, REFERENCE_RIGHTS_PROFILE_CODE, ["retrieve"])
        await _seed_rights_profile(
            session, UK_DMO_GILTS_RIGHTS_PROFILE_CODE, ["retrieve", "store"]
        )
        await _seed_gilt_reference_data(session)
        await session.commit()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
