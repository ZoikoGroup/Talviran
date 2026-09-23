"""Orchestrates one TradewebPriceCandidate (tradeweb_gilts connector
output) through the pipeline stages this module owns: rights check ->
identity resolve -> observation write -> reconcile/publish. Same
division of labour as stages.py's gilt-reference-terms path and
curve_ingest.py's curve-point path - acquire/parse already happened in
the connector before a candidate ever reaches here.

A real market close price is valid for exactly its own trading day, not
indefinitely (curve_ingest.py's own reasoning for GILT_NOMINAL_SPOT_
CURVE applies identically here) - today's close does not "correct"
yesterday's, it's a different real-world fact.
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.connectors.tradeweb_gilts.mapping import TradewebPriceCandidate
from app.modules.market.pipeline.identity_resolution import (
    ResolvedIdentity,
    resolve_instrument_by_isin,
)
from app.modules.market.pipeline.ingest_tail import ingest_and_reconcile
from app.modules.market.pipeline.reconcile import ReconciliationOutcome
from app.modules.market.pipeline.reconciliation_policy import GILT_MARKET_CLOSE_PRICE_POLICY
from app.modules.rights.engine import RightsDecision, evaluate_action

METRIC_GILT_MARKET_CLOSE_PRICE = "GILT_MARKET_CLOSE_PRICE"


@dataclass(frozen=True)
class TradewebIngestSkipped:
    reason: str


@dataclass(frozen=True)
class TradewebIngestResult:
    observation_id: uuid.UUID
    reconciliation: ReconciliationOutcome


def candidate_value(candidate: TradewebPriceCandidate) -> dict[str, Any]:
    return {
        "instrument_name": candidate.instrument_name,
        "instrument_type": candidate.instrument_type,
        "clean_price": str(candidate.clean_price),
        "dirty_price": str(candidate.dirty_price) if candidate.dirty_price is not None else None,
        "yield_pct": str(candidate.yield_pct),
        "mod_duration": str(candidate.mod_duration) if candidate.mod_duration is not None else None,
        "accrued_interest": (
            str(candidate.accrued_interest) if candidate.accrued_interest is not None else None
        ),
    }


def semantic_observation_key(
    *, source_code: str, dataset_code: str, isin: str, close_of_business_date: dt.date
) -> str:
    raw = (
        f"{source_code}:{dataset_code}:{isin}:{METRIC_GILT_MARKET_CLOSE_PRICE}:"
        f"{close_of_business_date.isoformat()}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()


async def ingest_tradeweb_price_candidate(
    session: AsyncSession,
    *,
    candidate: TradewebPriceCandidate,
    source_artifact_id: uuid.UUID,
    source_code: str,
    dataset_code: str,
    rights_profile_id: uuid.UUID,
    fetched_at: dt.datetime,
) -> TradewebIngestResult | TradewebIngestSkipped:
    rights_decision = await evaluate_action(session, "store", rights_profile_id)
    if rights_decision != RightsDecision.ALLOW:
        return TradewebIngestSkipped(
            reason=f"rights check denied 'store' for profile {rights_profile_id}"
        )

    identity = await resolve_instrument_by_isin(session, candidate.isin)
    if not isinstance(identity, ResolvedIdentity):
        return TradewebIngestSkipped(reason=identity.reason)

    key = semantic_observation_key(
        source_code=source_code,
        dataset_code=dataset_code,
        isin=candidate.isin,
        close_of_business_date=candidate.close_of_business_date,
    )
    value = candidate_value(candidate)

    day_start = dt.datetime.combine(
        candidate.close_of_business_date, dt.time.min, tzinfo=dt.UTC
    )
    valid_range: Range[dt.datetime] = Range(
        lower=day_start, upper=day_start + dt.timedelta(days=1), bounds="[)"
    )

    outcome = await ingest_and_reconcile(
        session,
        source_artifact_id=source_artifact_id,
        source_code=source_code,
        rights_profile_id=rights_profile_id,
        subject_type="INSTRUMENT",
        subject_id=identity.instrument_id,
        metric_id=METRIC_GILT_MARKET_CLOSE_PRICE,
        semantic_observation_key=key,
        value=value,
        valid_from=candidate.close_of_business_date,
        valid_range=valid_range,
        fetched_at=fetched_at,
        policy=GILT_MARKET_CLOSE_PRICE_POLICY,
    )

    return TradewebIngestResult(
        observation_id=outcome.observation_id, reconciliation=outcome.reconciliation
    )
