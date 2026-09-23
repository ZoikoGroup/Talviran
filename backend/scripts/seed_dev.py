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
from app.modules.calculation.models import CalculationSpecification
from app.modules.calculation.service import CALCULATION_RIGHTS_PROFILE_CODE
from app.modules.market.pipeline.equity_ingest import equity_alias_value
from app.modules.policy.models import ActivationRecord, CapabilityStatus
from app.modules.reference.models import FiSovereignTerms, Instrument, InstrumentAlias, Issuer
from app.modules.reference.service import REFERENCE_RIGHTS_PROFILE_CODE
from app.modules.rights.models import RightsGrant, RightsProfile

_JURISDICTION = "GB"
_CAPABILITIES = [
    "reference.issuers.read",
    "reference.instruments.read",
    "research.answer",
    "calculation.results.read",
    "monitoring.alerts.create",
    "monitoring.alerts.read",
    "monitoring.rules.create",
    "monitoring.rules.read",
]

UK_DMO_GILTS_RIGHTS_PROFILE_CODE = "uk-dmo.gilts"
BOE_YIELD_CURVE_RIGHTS_PROFILE_CODE = "boe.yield-curve"
UK_DMO_METHODOLOGY_RIGHTS_PROFILE_CODE = "uk-dmo.methodology"
FRANKFURTER_FX_RIGHTS_PROFILE_CODE = "frankfurter.fx"
DBNOMICS_MACRO_RIGHTS_PROFILE_CODE = "dbnomics.macro"
TWELVE_DATA_EQUITY_RIGHTS_PROFILE_CODE = "twelve-data.equity"
#: A genuinely different license than UK_DMO_GILTS_RIGHTS_PROFILE_CODE
#: (its own source, its own terms) - "non-professional and
#: non-commercial use" only, confirmed live from the export flow's own
#: terms-of-use dialog, with no redistribution right granted. Deliberately
#: NOT given "export"/"redistribute" actions - RIGHTS-001's per-action
#: doctrine means this restriction is enforced structurally, not by
#: policy convention alone.
TRADEWEB_GILT_PRICES_RIGHTS_PROFILE_CODE = "tradeweb.gilt-prices"
SEED_GILT_ISIN = "GB0032452392"

#: (issuer name, NSE trading symbol) — the pilot equity list for the
#: Twelve Data connector. Twelve Data's own symbol/exchange format was
#: confirmed live via its key-free /symbol_search endpoint (2026-09-18):
#: each resolves to symbol=<SYMBOL>, exchange="NSE", not a dotted suffix.
NSE_EXCHANGE_CODE = "NSE"
PILOT_EQUITIES: tuple[tuple[str, str], ...] = (
    ("Tata Motors Limited", "TATAMOTORS"),
    ("Tata Consultancy Services Limited", "TCS"),
    ("Reliance Industries Limited", "RELIANCE"),
    ("Infosys Limited", "INFY"),
    ("HDFC Bank Limited", "HDFCBANK"),
)


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


async def _seed_equity_reference_data(session: AsyncSession) -> None:
    """One Instrument/Issuer/InstrumentAlias per pilot stock — no adapter
    table (unlike FiSovereignTerms), since only the price fact is needed
    right now; static attributes (sector, etc.) are a later addition if
    the similarity/recommendation work ever needs them.
    """
    for issuer_name, symbol in PILOT_EQUITIES:
        alias_value = equity_alias_value(NSE_EXCHANGE_CODE, symbol)
        existing_alias = (
            await session.execute(
                select(InstrumentAlias).where(
                    InstrumentAlias.alias_type == "TICKER",
                    InstrumentAlias.alias_value == alias_value,
                )
            )
        ).scalar_one_or_none()
        if existing_alias is not None:
            continue

        issuer = (
            await session.execute(select(Issuer).where(Issuer.name == issuer_name))
        ).scalar_one_or_none()
        if issuer is None:
            issuer = Issuer(name=issuer_name, country_code="IN", status="ACTIVE")
            session.add(issuer)
            await session.flush()
            print(f"  + issuer {issuer_name} (IN)")

        instrument = Instrument(
            issuer_id=issuer.id,
            instrument_type="EQUITY_COMMON",
            name=issuer_name,
            currency_code="INR",
            status="ACTIVE",
        )
        session.add(instrument)
        await session.flush()
        print(f"  + instrument {instrument.name} ({instrument.id})")

        session.add(
            InstrumentAlias(
                instrument_id=instrument.id, alias_type="TICKER", alias_value=alias_value
            )
        )
        print(f"  + instrument_alias TICKER {alias_value}")


async def _seed_calculation_specification(
    session: AsyncSession, *, code: str, version: str, description: str
) -> None:
    # DRAFT, not APPROVED: moving to APPROVED is FIN-001's dual-implementation
    # + golden-test governance sign-off, never something seed/app code decides.
    existing = (
        await session.execute(
            select(CalculationSpecification).where(CalculationSpecification.code == code)
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            CalculationSpecification(
                code=code, version=version, status="DRAFT", description=description
            )
        )
        print(f"  + calculation_specification {code} v{version} -> DRAFT")


async def seed() -> None:
    factory = get_session_factory()
    async with factory() as session:
        await _seed_capability_statuses(session)
        await _seed_activation_record(session)
        await _seed_rights_profile(session, REFERENCE_RIGHTS_PROFILE_CODE, ["retrieve"])
        await _seed_rights_profile(session, CALCULATION_RIGHTS_PROFILE_CODE, ["retrieve"])
        await _seed_rights_profile(
            session, UK_DMO_GILTS_RIGHTS_PROFILE_CODE, ["retrieve", "store", "display"]
        )
        await _seed_rights_profile(
            session, BOE_YIELD_CURVE_RIGHTS_PROFILE_CODE, ["retrieve", "store", "display"]
        )
        # Document rights are evaluated independently of whatever profile
        # governs price data from the same publisher (EVID-001 doctrine) -
        # a freely-published UK government methodology PDF, so index/embed/
        # ai are granted now even though nothing consumes them until P4b.
        await _seed_rights_profile(
            session,
            UK_DMO_METHODOLOGY_RIGHTS_PROFILE_CODE,
            ["retrieve", "store", "index", "embed", "ai", "display"],
        )
        await _seed_rights_profile(
            session, FRANKFURTER_FX_RIGHTS_PROFILE_CODE, ["retrieve", "store", "display"]
        )
        await _seed_rights_profile(
            session, DBNOMICS_MACRO_RIGHTS_PROFILE_CODE, ["retrieve", "store", "display"]
        )
        await _seed_rights_profile(
            session, TWELVE_DATA_EQUITY_RIGHTS_PROFILE_CODE, ["retrieve", "store", "display"]
        )
        await _seed_rights_profile(
            session, TRADEWEB_GILT_PRICES_RIGHTS_PROFILE_CODE, ["retrieve", "store", "display"]
        )
        await _seed_gilt_reference_data(session)
        await _seed_equity_reference_data(session)
        await _seed_calculation_specification(
            session,
            code="gilt_price_yield_v1",
            version="1",
            description="UK DMO conventional-gilt price/yield formula (Section One).",
        )
        await _seed_calculation_specification(
            session,
            code="gilt_price_from_curve_v1",
            version="1",
            description=(
                "Model-implied gilt price from the BoE nominal spot curve — "
                "MODEL_IMPLIED basis, never a market quote."
            ),
        )
        await session.commit()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
