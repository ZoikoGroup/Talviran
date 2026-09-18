"""Orchestrates one EquityEodPriceCandidate (Twelve Data connector output)
through the pipeline stages this module owns: rights check -> identity
resolve -> observation write -> reconcile/publish. Acquire/manifest/
validate/normalise already happened in the connector before a candidate
ever reaches here — same division of labour as stages.py's gilt-reference-
terms path, the only other connector needing identity resolution.

Unlike a curve point, an FX pair, or a macro series, an equity IS a real
instrument (a real issuer/company, a real trading currency), so it goes
through reference.instrument + reference.instrument_alias like a gilt
does. Identity resolution is by exact TICKER match (never fuzzy
company-name matching) — an unresolved ticker is skipped, never
auto-created, same DATA-002 discipline as an unresolved ISIN.
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.connectors.twelve_data_equity.mapping import EquityEodPriceCandidate
from app.modules.market.pipeline.identity_resolution import (
    ResolvedIdentity,
    resolve_instrument_by_alias,
)
from app.modules.market.pipeline.ingest_tail import IngestOutcome, ingest_and_reconcile
from app.modules.market.pipeline.reconciliation_policy import EQUITY_EOD_PRICE_POLICY
from app.modules.rights.engine import RightsDecision, evaluate_action

METRIC_EQUITY_EOD_PRICE = "EQUITY_EOD_PRICE"
SUBJECT_TYPE_INSTRUMENT = "INSTRUMENT"
ALIAS_TYPE_TICKER = "TICKER"


def equity_alias_value(exchange_code: str, symbol: str) -> str:
    return f"{exchange_code}:{symbol}"


@dataclass(frozen=True)
class EquityIngestSkipped:
    reason: str


def equity_price_value(candidate: EquityEodPriceCandidate) -> dict[str, str]:
    # symbol/exchange are redundant with the resolved instrument_id, but a
    # fact must be self-describing to a reader — nothing should have to
    # look up a UUID to know what a fact even means.
    return {
        "symbol": candidate.symbol,
        "exchange": candidate.exchange,
        "close_price": str(candidate.close_price),
        "currency_code": candidate.currency_code,
    }


def equity_semantic_observation_key(
    *, source_code: str, dataset_code: str, exchange: str, symbol: str, trade_date: dt.date
) -> str:
    raw = f"{source_code}:{dataset_code}:{exchange}:{symbol}:{trade_date.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def ingest_equity_eod_price_candidate(
    session: AsyncSession,
    *,
    candidate: EquityEodPriceCandidate,
    source_artifact_id: uuid.UUID,
    source_code: str,
    dataset_code: str,
    rights_profile_id: uuid.UUID,
    fetched_at: dt.datetime,
) -> IngestOutcome | EquityIngestSkipped:
    rights_decision = await evaluate_action(session, "store", rights_profile_id)
    if rights_decision != RightsDecision.ALLOW:
        return EquityIngestSkipped(
            reason=f"rights check denied 'store' for profile {rights_profile_id}"
        )

    alias_value = equity_alias_value(candidate.exchange, candidate.symbol)
    identity = await resolve_instrument_by_alias(
        session, alias_type=ALIAS_TYPE_TICKER, alias_value=alias_value
    )
    if not isinstance(identity, ResolvedIdentity):
        return EquityIngestSkipped(reason=identity.reason)

    key = equity_semantic_observation_key(
        source_code=source_code,
        dataset_code=dataset_code,
        exchange=candidate.exchange,
        symbol=candidate.symbol,
        trade_date=candidate.trade_date,
    )
    value = equity_price_value(candidate)

    # An equity's end-of-day price is valid for exactly its own trading
    # day — the next day's close is a different real-world fact, not a
    # correction of this one, same reasoning as an FX rate or curve point.
    day_start = dt.datetime.combine(candidate.trade_date, dt.time.min, tzinfo=dt.UTC)
    valid_range: Range[dt.datetime] = Range(
        lower=day_start, upper=day_start + dt.timedelta(days=1), bounds="[)"
    )

    return await ingest_and_reconcile(
        session,
        source_artifact_id=source_artifact_id,
        source_code=source_code,
        rights_profile_id=rights_profile_id,
        subject_type=SUBJECT_TYPE_INSTRUMENT,
        subject_id=identity.instrument_id,
        metric_id=METRIC_EQUITY_EOD_PRICE,
        semantic_observation_key=key,
        value=value,
        valid_from=candidate.trade_date,
        valid_range=valid_range,
        fetched_at=fetched_at,
        policy=EQUITY_EOD_PRICE_POLICY,
    )
