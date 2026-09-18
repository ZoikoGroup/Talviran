"""Read-only proof that the three new connectors' data landed correctly in
market.accepted_fact, with a sane freshness classification. Doesn't touch
evidence/service.py or the frontend — this phase deliberately stops at
"the data is verifiably correct in the database", not "a chat can answer
a question about it" (that's the next phase). Run with:

    uv run python -m scripts.verify_new_connectors
"""

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.modules.market.freshness import compute_freshness
from app.modules.market.pipeline.equity_ingest import equity_alias_value
from app.modules.market.pipeline.fx_ingest import fx_pair_subject_id
from app.modules.market.pipeline.macro_ingest import macro_series_subject_id
from app.modules.market.queries import latest_accepted_fact
from app.modules.reference.models import InstrumentAlias
from scripts._connector_registry import MACRO_PILOT_SERIES
from scripts.seed_dev import NSE_EXCHANGE_CODE, PILOT_EQUITIES


async def _print_fact(
    session: AsyncSession, *, label: str, subject_id: uuid.UUID, metric_id: str
) -> None:
    fact = await latest_accepted_fact(session, subject_id=subject_id, metric_id=metric_id)
    if fact is None:
        print(f"  {label}: NO ACCEPTED FACT FOUND")
        return
    knowledge_since = fact.knowledge_range.lower
    assert knowledge_since is not None, "an accepted_fact always has a lower knowledge bound"
    freshness = compute_freshness(metric_id=metric_id, knowledge_time=knowledge_since)
    print(f"  {label}: {fact.value} [{freshness}, known since {knowledge_since}]")


async def verify_fx(session: AsyncSession) -> None:
    print("FX rates (Frankfurter):")
    for base, quote in (("GBP", "INR"), ("USD", "GBP"), ("USD", "INR"), ("EUR", "INR")):
        await _print_fact(
            session,
            label=f"{base}/{quote}",
            subject_id=fx_pair_subject_id(base, quote),
            metric_id="FX_SPOT_RATE",
        )


async def verify_macro(session: AsyncSession) -> None:
    print("Macro series (DBnomics):")
    for provider_code, dataset_code, series_code, metric_id in MACRO_PILOT_SERIES:
        await _print_fact(
            session,
            label=series_code,
            subject_id=macro_series_subject_id(provider_code, dataset_code, series_code),
            metric_id=metric_id,
        )


async def verify_equities(session: AsyncSession) -> None:
    print("Equity EOD prices (Twelve Data):")
    for issuer_name, symbol in PILOT_EQUITIES:
        alias_value = equity_alias_value(NSE_EXCHANGE_CODE, symbol)
        instrument_id = (
            await session.execute(
                select(InstrumentAlias.instrument_id).where(
                    InstrumentAlias.alias_type == "TICKER",
                    InstrumentAlias.alias_value == alias_value,
                )
            )
        ).scalar_one_or_none()
        if instrument_id is None:
            print(f"  {issuer_name} ({alias_value}): NOT SEEDED - run scripts.seed_dev first")
            continue
        await _print_fact(
            session,
            label=f"{issuer_name} ({alias_value})",
            subject_id=instrument_id,
            metric_id="EQUITY_EOD_PRICE",
        )


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        await verify_fx(session)
        await verify_macro(session)
        await verify_equities(session)


if __name__ == "__main__":
    asyncio.run(main())
