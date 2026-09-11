"""Proves deterministic-only identity resolution against real Postgres:
an exact ISIN match resolves, anything else is explicitly unresolved and
logged to audit — never fuzzy-matched or guessed.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import EventLog
from app.modules.market.pipeline.identity_resolution import (
    ResolvedIdentity,
    UnresolvedIdentity,
    resolve_instrument_by_isin,
)
from app.modules.reference.models import Instrument, InstrumentAlias, Issuer


async def _seed_instrument(session: AsyncSession, isin: str) -> Instrument:
    issuer = Issuer(name="HM Treasury", country_code="GB", status="ACTIVE")
    session.add(issuer)
    await session.flush()

    instrument = Instrument(
        issuer_id=issuer.id,
        instrument_type="FI_SOVEREIGN",
        name="Test Gilt",
        currency_code="GBP",
        status="ACTIVE",
    )
    session.add(instrument)
    await session.flush()

    session.add(InstrumentAlias(instrument_id=instrument.id, alias_type="ISIN", alias_value=isin))
    await session.flush()
    return instrument


async def test_exact_isin_match_resolves(db_session: AsyncSession) -> None:
    instrument = await _seed_instrument(db_session, "GB0032452392")

    result = await resolve_instrument_by_isin(db_session, "GB0032452392")

    assert isinstance(result, ResolvedIdentity)
    assert result.instrument_id == instrument.id


async def test_unknown_isin_is_unresolved_not_guessed(db_session: AsyncSession) -> None:
    await _seed_instrument(db_session, "GB0032452392")

    result = await resolve_instrument_by_isin(db_session, "GB0000000000")

    assert isinstance(result, UnresolvedIdentity)
    assert result.alias_value == "GB0000000000"


async def test_unresolved_identity_is_logged_to_audit(db_session: AsyncSession) -> None:
    await resolve_instrument_by_isin(db_session, "GB9999999999")
    await db_session.commit()

    rows = (
        await db_session.execute(
            select(EventLog).where(
                EventLog.event_type == "identity_resolution.unresolved",
                EventLog.subject_id == "GB9999999999",
            )
        )
    ).scalars().all()
    assert len(rows) == 1


async def test_near_miss_isin_does_not_fuzzy_match(db_session: AsyncSession) -> None:
    # One character off from a real, seeded ISIN — must NOT resolve. This
    # is the test that would catch a regression toward fuzzy matching.
    await _seed_instrument(db_session, "GB0032452392")

    result = await resolve_instrument_by_isin(db_session, "GB0032452393")

    assert isinstance(result, UnresolvedIdentity)
