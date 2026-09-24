"""Ingests the three new trusted-data-layer connectors (Frankfurter FX,
DBnomics macro, Twelve Data equities) into the dev database. Split out
from ingest_dev_data.py's existing gilt/curve blocks — those two also
enqueue and run the model-implied-price pricing job, which none of these
three need — but called from that same script's main(), so one command
still populates everything.

Not a production scheduler: like the rest of ingest_dev_data.py, this is
a manually-invoked dev script. A real recurring job is separate,
non-trivial future work — there is no scheduler of any kind in this
codebase yet.

The leading underscore on this module's filename is deliberate: this is
ingest_dev_data.py's own internal helper, not a general-purpose connector
framework to import from elsewhere.
"""

import asyncio
import datetime as dt
import hashlib
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.market.connectors.base import Quarantined, validate_and_parse
from app.modules.market.connectors.boe_fx.reference_connector import BoEFxConnector
from app.modules.market.connectors.dbnomics_macro.mapping import MacroObservationCandidate
from app.modules.market.connectors.dbnomics_macro.reference_connector import (
    DBnomicsMacroConnector,
)
from app.modules.market.connectors.frankfurter_fx.mapping import FxRateCandidate
from app.modules.market.connectors.frankfurter_fx.reference_connector import (
    FrankfurterFxConnector,
)
from app.modules.market.connectors.twelve_data_equity.mapping import EquityEodPriceCandidate
from app.modules.market.connectors.twelve_data_equity.reference_connector import (
    TwelveDataEquityConnector,
)
from app.modules.market.models import Dataset, Source, SourceArtifact
from app.modules.market.pipeline.equity_ingest import (
    EquityIngestSkipped,
    ingest_equity_eod_price_candidate,
)
from app.modules.market.pipeline.fx_ingest import FxIngestSkipped, ingest_fx_rate_candidate
from app.modules.market.pipeline.macro_ingest import (
    MacroIngestSkipped,
    ingest_macro_observation_candidate,
)
from app.modules.market.pipeline.reconciliation_policy import (
    MACRO_CPI_POLICY,
    MACRO_GDP_POLICY,
    ReconciliationPolicy,
)
from app.modules.rights.models import RightsProfile
from scripts.seed_dev import (
    BOE_FX_RIGHTS_PROFILE_CODE,
    DBNOMICS_MACRO_RIGHTS_PROFILE_CODE,
    FRANKFURTER_FX_RIGHTS_PROFILE_CODE,
    NSE_EXCHANGE_CODE,
    PILOT_EQUITIES,
    TWELVE_DATA_EQUITY_RIGHTS_PROFILE_CODE,
)

#: (base currency, quote currencies) — covers the 5 pilot pairs (GBP/INR,
#: GBP/USD, USD/GBP, USD/INR, EUR/INR) across 3 acquisitions, since
#: Frankfurter serves several quote currencies per base in one call.
#: GBP->USD (added to the GBP query, not the existing USD->GBP one)
#: deliberately matches boe_fx's own base/quote convention (GBP base, USD
#: quote): fx_pair_subject_id is order-sensitive, USD->GBP and GBP->USD
#: are different subjects, and only the GBP-base ordering is what boe_fx
#: also feeds - only that one actually reconciles against it.
FX_PILOT_QUERIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("GBP", ("INR", "USD")),
    ("USD", ("GBP", "INR")),
    ("EUR", ("INR",)),
)

#: (provider_code, dataset_code, series_code, metric_id) — confirmed real
#: against DBnomics' live API (2026-09-18), not guessed.
MACRO_PILOT_SERIES: tuple[tuple[str, str, str, str], ...] = (
    ("WB", "WDI", "A-NY.GDP.MKTP.CD-IND", "MACRO_GDP"),
    ("WB", "WDI", "A-FP.CPI.TOTL.ZG-IND", "MACRO_CPI"),
    ("WB", "WDI", "A-NY.GDP.MKTP.CD-GBR", "MACRO_GDP"),
    ("WB", "WDI", "A-FP.CPI.TOTL.ZG-GBR", "MACRO_CPI"),
    ("WB", "WDI", "A-NY.GDP.MKTP.CD-USA", "MACRO_GDP"),
    ("WB", "WDI", "A-FP.CPI.TOTL.ZG-USA", "MACRO_CPI"),
)

_MACRO_POLICIES: dict[str, ReconciliationPolicy] = {
    "MACRO_GDP": MACRO_GDP_POLICY,
    "MACRO_CPI": MACRO_CPI_POLICY,
}

# Twelve Data's free tier allows ~8 requests/minute - a plain sleep
# between calls is a dev-script-level throttle, not production
# rate-limiting (no retry/rate-limit machinery exists in any connector).
_TWELVE_DATA_THROTTLE_SECONDS = 8


async def _rights_profile_id(session: AsyncSession, code: str) -> uuid.UUID:
    profile = (
        await session.execute(select(RightsProfile).where(RightsProfile.code == code))
    ).scalar_one()
    return profile.id


async def _seed_source_artifact(
    session: AsyncSession,
    *,
    source_code: str,
    source_name: str,
    dataset_code: str,
    dataset_name: str,
    media_type: str,
    raw_bytes: bytes,
) -> SourceArtifact:
    # Stable, idempotent Source.code == source_code (find-or-create), not a
    # randomized suffix per run - a real gap found while wiring boe_fx:
    # ingest_and_reconcile's cross-source gathering now joins BACK through
    # Source.code to resolve each sibling observation's source for
    # reconciliation-policy precedence matching. A randomized code here
    # would silently break that match (ordered_source_codes=("frankfurter",
    # "boe") would never equal "frankfurter-a1b2c3"), even though nothing
    # depended on this table's exact code before that gathering existed.
    source = (
        await session.execute(select(Source).where(Source.code == source_code))
    ).scalar_one_or_none()
    if source is None:
        source = Source(code=source_code, name=source_name)
        session.add(source)
        await session.flush()

    dataset = (
        await session.execute(
            select(Dataset).where(Dataset.source_id == source.id, Dataset.code == dataset_code)
        )
    ).scalar_one_or_none()
    if dataset is None:
        dataset = Dataset(source_id=source.id, code=dataset_code, name=dataset_name)
        session.add(dataset)
        await session.flush()
    artifact = SourceArtifact(
        dataset_id=dataset.id,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        storage_ref=f"dev-live://{source_code}",
        media_type=media_type,
        byte_length=len(raw_bytes),
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    session.add(artifact)
    await session.flush()
    return artifact


async def ingest_fx_pilot(session: AsyncSession) -> None:
    rights_id = await _rights_profile_id(session, FRANKFURTER_FX_RIGHTS_PROFILE_CODE)
    async with httpx.AsyncClient() as client:
        for base_currency, quotes in FX_PILOT_QUERIES:
            connector = FrankfurterFxConnector(
                client, base_currency=base_currency, quote_currencies=quotes
            )
            try:
                payload = await connector.acquire()
            except httpx.HTTPError as exc:
                print(f"Frankfurter {base_currency}->{quotes}: live fetch failed ({exc}).")
                continue

            candidates_or_quarantine = validate_and_parse(connector, payload)
            if isinstance(candidates_or_quarantine, Quarantined):
                print(
                    f"Frankfurter {base_currency}->{quotes}: quarantined "
                    f"({candidates_or_quarantine.reasons})."
                )
                continue

            artifact = await _seed_source_artifact(
                session,
                source_code="frankfurter",
                source_name="Frankfurter (dev)",
                dataset_code="rates",
                dataset_name="Frankfurter Rates",
                media_type="application/json",
                raw_bytes=payload.raw_bytes,
            )
            ingested = 0
            for candidate in candidates_or_quarantine:
                if not isinstance(candidate, FxRateCandidate):
                    continue
                result = await ingest_fx_rate_candidate(
                    session,
                    candidate=candidate,
                    source_artifact_id=artifact.id,
                    source_code="frankfurter",
                    dataset_code="rates",
                    rights_profile_id=rights_id,
                    fetched_at=payload.fetched_at,
                )
                if isinstance(result, FxIngestSkipped):
                    print(
                        f"  FX {candidate.base_currency}/{candidate.quote_currency}: "
                        f"skipped ({result.reason})."
                    )
                else:
                    ingested += 1
            await session.commit()
            print(f"Frankfurter {base_currency}->{quotes}: ingested {ingested} rate(s).")


async def ingest_boe_fx_pilot(session: AsyncSession) -> None:
    """The second real FX_SPOT_RATE source (alongside frankfurter) - see
    reconciliation_policy.FX_SPOT_RATE_POLICY's own docstring. Ingests
    every day the feed returns (up to boe_fx.client._LOOKBACK_DAYS back),
    not just the latest - each is its own day-scoped fact, same reasoning
    as the BoE yield curve's own multi-point-per-acquisition handling.
    """
    rights_id = await _rights_profile_id(session, BOE_FX_RIGHTS_PROFILE_CODE)
    async with httpx.AsyncClient() as client:
        connector = BoEFxConnector(client)
        try:
            payload = await connector.acquire()
        except httpx.HTTPError as exc:
            print(f"BoE FX: live fetch failed ({exc}).")
            return

        candidates_or_quarantine = validate_and_parse(connector, payload)
        if isinstance(candidates_or_quarantine, Quarantined):
            print(f"BoE FX: quarantined ({candidates_or_quarantine.reasons}).")
            return

        artifact = await _seed_source_artifact(
            session,
            source_code="boe",
            source_name="Bank of England (dev)",
            dataset_code="fx-daily-spot-rates",
            dataset_name="BoE Daily GBP/USD Spot Rate",
            media_type="text/csv",
            raw_bytes=payload.raw_bytes,
        )
        ingested = 0
        for candidate in candidates_or_quarantine:
            if not isinstance(candidate, FxRateCandidate):
                continue
            result = await ingest_fx_rate_candidate(
                session,
                candidate=candidate,
                source_artifact_id=artifact.id,
                source_code="boe",
                dataset_code="fx-daily-spot-rates",
                rights_profile_id=rights_id,
                fetched_at=payload.fetched_at,
            )
            if isinstance(result, FxIngestSkipped):
                print(f"  BoE FX {candidate.as_of}: skipped ({result.reason}).")
            else:
                ingested += 1
        await session.commit()
        print(f"BoE FX: ingested {ingested} day(s).")


async def ingest_macro_pilot(session: AsyncSession) -> None:
    rights_id = await _rights_profile_id(session, DBNOMICS_MACRO_RIGHTS_PROFILE_CODE)
    async with httpx.AsyncClient() as client:
        for provider_code, dataset_code, series_code, metric_id in MACRO_PILOT_SERIES:
            connector = DBnomicsMacroConnector(
                client,
                provider_code=provider_code,
                dataset_code=dataset_code,
                series_code=series_code,
            )
            try:
                payload = await connector.acquire()
            except httpx.HTTPError as exc:
                print(f"DBnomics {series_code}: live fetch failed ({exc}).")
                continue

            candidates_or_quarantine = validate_and_parse(connector, payload)
            if isinstance(candidates_or_quarantine, Quarantined):
                print(f"DBnomics {series_code}: quarantined ({candidates_or_quarantine.reasons}).")
                continue

            observations = [
                c for c in candidates_or_quarantine if isinstance(c, MacroObservationCandidate)
            ]
            if not observations:
                print(f"DBnomics {series_code}: no observations parsed.")
                continue
            # DBnomics' `observations=1` param means "include observations"
            # (a boolean flag), not a limit - a real response carries the
            # series' full history, so picking the latest is this script's
            # job, same as it filters the BoE curve feed to its latest date.
            latest = max(observations, key=lambda c: c.period_start_day)

            artifact = await _seed_source_artifact(
                session,
                source_code="dbnomics",
                source_name="DBnomics (dev)",
                dataset_code=f"{provider_code}.{dataset_code}",
                dataset_name=f"{provider_code} {dataset_code}",
                media_type="application/json",
                raw_bytes=payload.raw_bytes,
            )
            result = await ingest_macro_observation_candidate(
                session,
                candidate=latest,
                metric_id=metric_id,
                policy=_MACRO_POLICIES[metric_id],
                source_artifact_id=artifact.id,
                source_code="dbnomics",
                dataset_code=f"{provider_code}.{dataset_code}",
                rights_profile_id=rights_id,
                fetched_at=payload.fetched_at,
            )
            await session.commit()
            if isinstance(result, MacroIngestSkipped):
                print(f"DBnomics {series_code}: skipped ({result.reason}).")
            else:
                print(f"DBnomics {series_code}: ingested {latest.period} = {latest.value}.")


async def ingest_equity_pilot(session: AsyncSession) -> None:
    settings = get_settings()
    if not settings.twelve_data_api_key:
        print("Twelve Data: TWELVE_DATA_API_KEY not set - skipping equity ingestion.")
        return

    rights_id = await _rights_profile_id(session, TWELVE_DATA_EQUITY_RIGHTS_PROFILE_CODE)
    async with httpx.AsyncClient() as client:
        for _issuer_name, symbol in PILOT_EQUITIES:
            connector = TwelveDataEquityConnector(
                client,
                symbol=symbol,
                exchange=NSE_EXCHANGE_CODE,
                api_key=settings.twelve_data_api_key,
            )
            try:
                payload = await connector.acquire()
            except httpx.HTTPError as exc:
                print(f"Twelve Data {symbol}: live fetch failed ({exc}).")
                continue

            candidates_or_quarantine = validate_and_parse(connector, payload)
            if isinstance(candidates_or_quarantine, Quarantined):
                print(f"Twelve Data {symbol}: quarantined ({candidates_or_quarantine.reasons}).")
            else:
                artifact = await _seed_source_artifact(
                    session,
                    source_code="twelve-data",
                    source_name="Twelve Data (dev)",
                    dataset_code="eod-price",
                    dataset_name="Equity EOD Price",
                    media_type="application/json",
                    raw_bytes=payload.raw_bytes,
                )
                ingested = 0
                for candidate in candidates_or_quarantine:
                    if not isinstance(candidate, EquityEodPriceCandidate):
                        continue
                    result = await ingest_equity_eod_price_candidate(
                        session,
                        candidate=candidate,
                        source_artifact_id=artifact.id,
                        source_code="twelve-data",
                        dataset_code="eod-price",
                        rights_profile_id=rights_id,
                        fetched_at=payload.fetched_at,
                    )
                    if isinstance(result, EquityIngestSkipped):
                        print(f"  {symbol} {candidate.trade_date}: skipped ({result.reason}).")
                    else:
                        ingested += 1
                await session.commit()
                print(f"Twelve Data {symbol}: ingested {ingested} day(s).")

            if symbol != PILOT_EQUITIES[-1][1]:
                await asyncio.sleep(_TWELVE_DATA_THROTTLE_SECONDS)


async def ingest_all(session: AsyncSession) -> None:
    await ingest_fx_pilot(session)
    await ingest_boe_fx_pilot(session)
    await ingest_macro_pilot(session)
    await ingest_equity_pilot(session)
