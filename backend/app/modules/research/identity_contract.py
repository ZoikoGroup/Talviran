"""G02: one canonical meaning for a research request's subject, across every
surface - the typed identity/capability contract proposed in the UAT gap
analysis (07/ENGINEERING REMEDIATION, "G02-G04: one meaning across every
surface").

Deterministic only, same doctrine as pipeline/identity_resolution.py's
ingestion-time resolver: an exact alias or issuer-name match, never a fuzzy
one. A typo is correctly UNRESOLVED, not auto-corrected - a wrong silent
guess is worse than an honest "not found". An issuer name that spans
multiple listings/share classes (GOOGL vs GOOG) is correctly AMBIGUOUS and
must be clarified, never collapsed to "the first one" or "the most liquid
one" - that collapsing is exactly the G02 defect this contract exists to
close.

This module intentionally does NOT yet wire rights.evaluate_action into
decide_capability (RESTRICTED is a defined state but never returned) -
that needs a real PolicyContext (jurisdiction, account) this module has no
cheap way to construct outside a request. Follow-up work, not guessed at
here.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.freshness import (
    DEFAULT_PROFILES,
    STATE_CURRENT,
    STATE_DELAYED,
    STATE_STALE,
    STATE_UNAVAILABLE,
    compute_freshness,
)
from app.modules.market.models import AcceptedFact
from app.modules.reference.models import Instrument, InstrumentAlias, Issuer

# Alias types a free-text research request may plausibly name an instrument
# by. Deliberately excludes nothing-matched fuzzy variants (no LIKE, no
# trigram) - exactly the set identity_resolution.py already trusts for
# ingestion, reused here for the request-resolution surface.
_ALIAS_TYPES = ("TICKER", "CASHTAG", "ISIN", "CUSIP", "SEDOL", "FIGI")


def _normalize(raw_text: str) -> str:
    """Case/whitespace/cashtag normalization only - RIGHTS-001/DATA-002's
    deterministic-matching doctrine forbids anything beyond this (no
    stemming, no edit-distance, no synonym table)."""
    text = raw_text.strip()
    if text.startswith("$"):
        text = text[1:]
    return text.upper()


@dataclass(frozen=True)
class EntityCandidate:
    instrument_id: uuid.UUID
    issuer_id: uuid.UUID
    display_name: str
    matched_alias_type: str
    matched_alias_value: str


@dataclass(frozen=True)
class ResolvedEntity:
    candidate: EntityCandidate


@dataclass(frozen=True)
class AmbiguousEntity:
    raw_text: str
    candidates: list[EntityCandidate]


@dataclass(frozen=True)
class UnresolvedEntity:
    raw_text: str
    reason: str


async def resolve_research_entity(
    session: AsyncSession, raw_text: str
) -> ResolvedEntity | AmbiguousEntity | UnresolvedEntity:
    """G02's "resolved research request" identity step. Tries an exact alias
    match first (ticker/cashtag/ISIN/...); if none matches, tries an exact
    issuer-name match, which may legitimately fan out to more than one
    instrument (several listings/share classes of the same issuer) - that
    fan-out IS the ambiguous case, not a bug to resolve by picking one.
    """
    normalized = _normalize(raw_text)
    if not normalized:
        return UnresolvedEntity(raw_text=raw_text, reason="empty request")

    alias_rows = (
        await session.execute(
            select(
                Instrument.id, Instrument.issuer_id, Instrument.name,
                InstrumentAlias.alias_type, InstrumentAlias.alias_value,
            )
            .join(InstrumentAlias, InstrumentAlias.instrument_id == Instrument.id)
            .where(
                InstrumentAlias.alias_type.in_(_ALIAS_TYPES),
                InstrumentAlias.alias_value == normalized,
                Instrument.status == "ACTIVE",
            )
        )
    ).all()

    if not alias_rows:
        issuer_rows = (
            await session.execute(
                select(Instrument.id, Instrument.issuer_id, Instrument.name)
                .join(Issuer, Issuer.id == Instrument.issuer_id)
                .where(Issuer.name.ilike(normalized), Instrument.status == "ACTIVE")
            )
        ).all()
        candidates = [
            EntityCandidate(
                instrument_id=row.id,
                issuer_id=row.issuer_id,
                display_name=row.name,
                matched_alias_type="ISSUER_NAME",
                matched_alias_value=normalized,
            )
            for row in issuer_rows
        ]
    else:
        candidates = [
            EntityCandidate(
                instrument_id=row.id,
                issuer_id=row.issuer_id,
                display_name=row.name,
                matched_alias_type=row.alias_type,
                matched_alias_value=row.alias_value,
            )
            for row in alias_rows
        ]

    distinct_instruments = {c.instrument_id: c for c in candidates}
    if not distinct_instruments:
        return UnresolvedEntity(
            raw_text=raw_text, reason="no matching instrument alias or issuer name"
        )
    if len(distinct_instruments) == 1:
        return ResolvedEntity(candidate=next(iter(distinct_instruments.values())))
    return AmbiguousEntity(raw_text=raw_text, candidates=list(distinct_instruments.values()))


class CapabilityState(StrEnum):
    """The seven states G02-G04's "capability decision" contract requires a
    request to land in. RESTRICTED is defined but not yet reachable - see
    module docstring."""

    AVAILABLE = "available"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    STALE = "stale"
    CONFLICTED = "conflicted"
    RESTRICTED = "restricted"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"


@dataclass(frozen=True)
class CapabilityDecision:
    state: CapabilityState
    reason: str
    checked_at: dt.datetime
    coverage_as_of: dt.datetime | None = field(default=None)


_FRESHNESS_TO_CAPABILITY = {
    STATE_CURRENT: CapabilityState.AVAILABLE,
    STATE_DELAYED: CapabilityState.AVAILABLE,
    STATE_STALE: CapabilityState.STALE,
    STATE_UNAVAILABLE: CapabilityState.TEMPORARILY_UNAVAILABLE,
}


async def decide_capability(
    session: AsyncSession, *, instrument_id: uuid.UUID, metric_id: str
) -> CapabilityDecision:
    """G02-G04's "capability decision" step: instrument x metric, resolved
    to exactly one of CapabilityState. Fails closed on an unregistered
    metric (market/freshness.py's own doctrine: no profile is a
    configuration gap, not an excuse to claim CURRENT) and on no accepted
    fact existing at all, rather than guessing availability either way.
    """
    now = dt.datetime.now(dt.UTC)

    if metric_id not in DEFAULT_PROFILES:
        return CapabilityDecision(
            state=CapabilityState.UNSUPPORTED,
            reason=f"no freshness profile registered for metric_id={metric_id!r}",
            checked_at=now,
        )

    row = (
        await session.execute(
            select(AcceptedFact)
            .where(
                AcceptedFact.subject_id == instrument_id,
                AcceptedFact.metric_id == metric_id,
                AcceptedFact.status == "ACTIVE",
            )
            .order_by(AcceptedFact.knowledge_range.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if row is None:
        return CapabilityDecision(
            state=CapabilityState.UNSUPPORTED,
            reason="no accepted fact for this instrument/metric",
            checked_at=now,
        )

    knowledge_time = row.knowledge_range.lower
    assert knowledge_time is not None, "accepted_fact.knowledge_range has no lower bound"
    freshness_state = compute_freshness(
        metric_id=metric_id, knowledge_time=knowledge_time, now=now
    )
    capability_state = _FRESHNESS_TO_CAPABILITY[freshness_state]
    return CapabilityDecision(
        state=capability_state,
        reason=f"accepted fact is {freshness_state.lower()}",
        checked_at=now,
        coverage_as_of=knowledge_time,
    )
