"""Fetches real UK gilt closing prices from Tradeweb Market InSite and
ingests them through the real pipeline (rights check -> identity
resolve -> observation write -> reconcile/publish) - a genuine market
quote (GILT_MARKET_CLOSE_PRICE), not the model-implied estimate
calculation.pipeline.curve_pricing produces.

Run with (after `uv run python -m scripts.seed_dev` and
`uv run python -m scripts.onboard_all_gilts`):

    uv run python -m scripts.ingest_tradeweb_gilt_prices

Requires TRADEWEB_USERNAME/TRADEWEB_PASSWORD in .env - a real registered
Market InSite account (see market/connectors/tradeweb_gilts/client.py's
docstring for the live-verified login/export flow and its
"non-professional and non-commercial use" licensing).

Only rows for GB-ISIN Conventional gilts are ingested - the same
universe scripts.onboard_all_gilts already onboarded reference terms
for (index-linked gilts, Treasury Bills, and non-UK sovereigns present
in the same export are real data but out of scope for what this
codebase's instrument registry and calculation engine currently cover).
A row whose ISIN isn't already a registered instrument is skipped, not
guessed at (DATA-002: never auto-create identity from a price feed).

Deliberately NOT meant to run repeatedly/rapidly - see the connector's
own docstring on the login endpoint's apparent rate-limiting. Run at
most once a day; EOD close data doesn't change more often than that
anyway.
"""

import asyncio
import datetime as dt
import hashlib
import uuid

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.modules.calculation.models import CalculationSpecification
from app.modules.calculation.pipeline.job_queue import (
    enqueue_gilt_risk_metrics_job,
    run_next_job,
)
from app.modules.market.connectors.tradeweb_gilts.client import (
    TradewebAuthError,
    fetch_gilt_closing_prices_csv,
)
from app.modules.market.connectors.tradeweb_gilts.mapping import RecordIssue, parse_rows
from app.modules.market.models import Dataset, Source, SourceArtifact
from app.modules.market.pipeline.identity_resolution import (
    ResolvedIdentity,
    resolve_instrument_by_isin,
)
from app.modules.market.pipeline.tradeweb_price_ingest import (
    TradewebIngestSkipped,
    ingest_tradeweb_price_candidate,
)
from app.modules.rights.models import RightsProfile
from scripts.seed_dev import TRADEWEB_GILT_PRICES_RIGHTS_PROFILE_CODE

_GILT_RISK_METRICS_SPEC_CODE = "gilt_risk_metrics_v1"

_IN_SCOPE_TYPE = "Conventional"
_SOURCE_CODE = "tradeweb"
_DATASET_CODE = "gilt-closing-prices"


async def main() -> None:
    settings = get_settings()
    if not settings.tradeweb_username or not settings.tradeweb_password:
        raise SystemExit(
            "TRADEWEB_USERNAME/TRADEWEB_PASSWORD not configured - a real "
            "registered Market InSite account is required, there is no "
            "anonymous path."
        )

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await fetch_gilt_closing_prices_csv(
                client, username=settings.tradeweb_username, password=settings.tradeweb_password
            )
        except TradewebAuthError as exc:
            raise SystemExit(f"Tradeweb login/export failed: {exc}") from None

        csv_bytes = response.content
        records = parse_rows(csv_bytes.decode("utf-8-sig"))

    factory = get_session_factory()
    async with factory() as session:
        rights_profile_id = (
            await session.execute(
                select(RightsProfile.id).where(
                    RightsProfile.code == TRADEWEB_GILT_PRICES_RIGHTS_PROFILE_CODE
                )
            )
        ).scalar_one_or_none()
        if rights_profile_id is None:
            raise SystemExit(
                f"rights_profile {TRADEWEB_GILT_PRICES_RIGHTS_PROFILE_CODE!r} not seeded - "
                "run `uv run python -m scripts.seed_dev` first"
            )

        source = (
            await session.execute(select(Source).where(Source.code == _SOURCE_CODE))
        ).scalar_one_or_none()
        if source is None:
            source = Source(code=_SOURCE_CODE, name="Tradeweb Market InSite")
            session.add(source)
            await session.flush()

        dataset = (
            await session.execute(select(Dataset).where(Dataset.code == _DATASET_CODE))
        ).scalar_one_or_none()
        if dataset is None:
            dataset = Dataset(
                source_id=source.id, code=_DATASET_CODE, name="Gilt Closing Prices"
            )
            session.add(dataset)
            await session.flush()

        artifact = SourceArtifact(
            dataset_id=dataset.id, sha256=hashlib.sha256(csv_bytes).hexdigest(),
            storage_ref=f"tradeweb-live://{uuid.uuid4().hex[:8]}",
            media_type="text/csv", byte_length=len(csv_bytes),
            retrieved_at=dt.datetime.now(dt.UTC),
        )
        session.add(artifact)
        await session.flush()
        await session.commit()

        # Looked up once, not per-row: a missing/unapproved spec means the
        # risk-metrics job is skipped for every row below, but price
        # ingestion itself must still complete - this script's primary job
        # is the real market price, not the derived analytic.
        risk_metrics_spec = (
            await session.execute(
                select(CalculationSpecification).where(
                    CalculationSpecification.code == _GILT_RISK_METRICS_SPEC_CODE
                )
            )
        ).scalar_one_or_none()
        if risk_metrics_spec is None:
            print(
                f"No {_GILT_RISK_METRICS_SPEC_CODE} calculation_specification found - "
                "run scripts.seed_dev first. Skipping risk-metrics jobs for this run."
            )

        ingested = skipped_out_of_scope = skipped_unresolved = skipped_other = 0
        for record in records:
            if isinstance(record, RecordIssue):
                skipped_other += 1
                print(f"  ! parse issue for {record.raw_isin}: {record.reason}")
                continue
            if record.instrument_type != _IN_SCOPE_TYPE or not record.isin.startswith("GB"):
                skipped_out_of_scope += 1
                continue

            result = await ingest_tradeweb_price_candidate(
                session, candidate=record, source_artifact_id=artifact.id,
                source_code=_SOURCE_CODE, dataset_code=_DATASET_CODE,
                rights_profile_id=rights_profile_id, fetched_at=dt.datetime.now(dt.UTC),
            )
            await session.commit()
            if isinstance(result, TradewebIngestSkipped):
                skipped_unresolved += 1
                print(f"  ! skipped {record.isin} ({record.instrument_name}): {result.reason}")
            else:
                ingested += 1
                print(
                    f"  + {record.instrument_name} ({record.isin}): "
                    f"clean={record.clean_price} yield={record.yield_pct}%"
                )
                if risk_metrics_spec is not None:
                    identity = await resolve_instrument_by_isin(session, record.isin)
                    if isinstance(identity, ResolvedIdentity):
                        await enqueue_gilt_risk_metrics_job(
                            session,
                            instrument_id=identity.instrument_id,
                            as_of_date=record.close_of_business_date,
                            calculation_specification_id=risk_metrics_spec.id,
                        )
                        await session.commit()
                        job_result = await run_next_job(session)
                        if job_result is not None:
                            print(f"    risk metrics: {job_result.outcome}")

        print(
            f"\nIngested {ingested} real gilt closing prices. Skipped {skipped_out_of_scope} "
            f"out-of-scope rows (non-GB or non-Conventional), {skipped_unresolved} unresolved "
            f"ISINs (not yet onboarded), {skipped_other} unparseable rows."
        )


if __name__ == "__main__":
    asyncio.run(main())
