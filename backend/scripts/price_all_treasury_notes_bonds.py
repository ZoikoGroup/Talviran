"""Prices every onboarded US Treasury Note/Bond against the latest US
Treasury par-yield curve, via treasury_price_from_curve_v1.

Unlike onboard_all_gilts.py's own dev pricing trigger (ingest_dev_data.py
enqueues a single demo job for the one seed gilt), this script is the
actual batch-pricing action for the real onboarded universe - mirrors
P2's job-table handoff (job_queue.py) exactly: enqueue, then drain via
run_next_job in a loop, never calling compute_and_persist_* directly.

Run with (after onboard_all_treasury_securities and a Treasury curve
ingest have both already happened):

    uv run python -m scripts.price_all_treasury_notes_bonds

Idempotent: re-running recomputes every Note/Bond against whatever the
curve looks like now - NO_CHANGE for anything unchanged, a real supersede
for anything that moved, same as every other calculation pipeline here.
"""

import asyncio

from sqlalchemy import select

from app.core.db import get_session_factory
from app.modules.calculation.models import CalculationSpecification
from app.modules.calculation.pipeline.job_queue import (
    JobRun,
    enqueue_treasury_model_implied_price_job,
    run_next_job,
)
from app.modules.calculation.pipeline.treasury_curve_pricing import (
    TreasuryModelImpliedPriceSkipped,
)
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.treasury_curve_ingest import (
    METRIC_US_TREASURY_PAR_YIELD_CURVE,
    treasury_curve_point_subject_id,
)
from app.modules.market.pipeline.treasury_securities_ingest import (
    METRIC_TREASURY_SECURITY_REFERENCE_TERMS,
)
from app.modules.market.queries import latest_accepted_fact

_SPEC_CODE = "treasury_price_from_curve_v1"
_PRICEABLE_SECURITY_TYPES = frozenset({"Note", "Bond"})
#: BC_10YEAR is always published whenever the curve is published at all -
#: a reliable anchor for "what's the latest curve date", same role
#: evidence/service.py's own _latest_curve_date logic plays for the UI.
_ANCHOR_TENOR_FIELD = "BC_10YEAR"


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        spec = (
            await session.execute(
                select(CalculationSpecification).where(
                    CalculationSpecification.code == _SPEC_CODE
                )
            )
        ).scalar_one_or_none()
        if spec is None:
            raise SystemExit(
                f"{_SPEC_CODE} calculation_specification not found - run scripts.seed_dev first."
            )

        anchor_fact = await latest_accepted_fact(
            session,
            subject_id=treasury_curve_point_subject_id(_ANCHOR_TENOR_FIELD),
            metric_id=METRIC_US_TREASURY_PAR_YIELD_CURVE,
        )
        if anchor_fact is None:
            raise SystemExit(
                "No US Treasury par-yield curve data found - ingest the curve "
                "(scripts.ingest_dev_data or the treasury curve connector) first."
            )
        assert anchor_fact.valid_range.lower is not None
        as_of_date = anchor_fact.valid_range.lower.date()

        reference_facts = (
            (
                await session.execute(
                    select(AcceptedFact).where(
                        AcceptedFact.metric_id == METRIC_TREASURY_SECURITY_REFERENCE_TERMS,
                        AcceptedFact.status == "ACTIVE",
                    )
                )
            )
            .scalars()
            .all()
        )
        priceable_instrument_ids = [
            fact.subject_id
            for fact in reference_facts
            if fact.value.get("security_type") in _PRICEABLE_SECURITY_TYPES
        ]
        await session.commit()

        print(
            f"Pricing {len(priceable_instrument_ids)} Note/Bond instruments as of "
            f"{as_of_date} against the US Treasury par-yield curve..."
        )

        for instrument_id in priceable_instrument_ids:
            await enqueue_treasury_model_implied_price_job(
                session, instrument_id=instrument_id, as_of_date=as_of_date,
                calculation_specification_id=spec.id,
            )
        await session.commit()

        computed = skipped = 0
        skip_reasons: dict[str, int] = {}
        while True:
            result: JobRun | None = await run_next_job(session)
            if result is None:
                break
            if isinstance(result.outcome, TreasuryModelImpliedPriceSkipped):
                skipped += 1
                # Bucket by the stable prefix before any instrument-specific
                # detail, so the summary stays readable even with hundreds
                # of jobs.
                reason_key = result.outcome.reason.split(" - ")[0].split(" for ")[0][:60]
                skip_reasons[reason_key] = skip_reasons.get(reason_key, 0) + 1
            else:
                computed += 1

        print(f"\nComputed {computed}, skipped {skipped}.")
        if skip_reasons:
            print("Skip reasons:")
            for reason, count in sorted(skip_reasons.items(), key=lambda kv: -kv[1]):
                print(f"  {count:4d}  {reason}")


if __name__ == "__main__":
    asyncio.run(main())
