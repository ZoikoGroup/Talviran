"""Deterministic identity resolution (DATA-002) — exact ISIN match against
reference.instrument_alias only. Never fuzzy/AI matching: an unmatched
candidate is routed to the audit log as an unresolved-identity event (a
lightweight stand-in for a real ops-review queue, which doesn't exist yet)
rather than guessed at.

Deliberately does NOT create new reference.instrument rows for unmatched
ISINs — the reference registry is populated through controlled onboarding
(see scripts/seed_dev.py), not auto-created from arbitrary incoming
observations. Letting ingestion silently mint new "instruments" from
whatever a feed contains would be exactly the kind of ungoverned
auto-linking DATA-002 forbids.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import record_event
from app.modules.reference.models import InstrumentAlias


@dataclass(frozen=True)
class ResolvedIdentity:
    instrument_id: uuid.UUID


@dataclass(frozen=True)
class UnresolvedIdentity:
    alias_type: str
    alias_value: str
    reason: str


async def resolve_instrument_by_isin(
    session: AsyncSession, isin: str
) -> ResolvedIdentity | UnresolvedIdentity:
    instrument_id = (
        await session.execute(
            select(InstrumentAlias.instrument_id).where(
                InstrumentAlias.alias_type == "ISIN",
                InstrumentAlias.alias_value == isin,
            )
        )
    ).scalar_one_or_none()

    if instrument_id is None:
        unresolved = UnresolvedIdentity(
            alias_type="ISIN", alias_value=isin, reason="no matching instrument_alias row"
        )
        await record_event(
            session,
            event_type="identity_resolution.unresolved",
            subject_type="ISIN",
            subject_id=isin,
            payload={"reason": unresolved.reason},
        )
        return unresolved

    return ResolvedIdentity(instrument_id=instrument_id)
