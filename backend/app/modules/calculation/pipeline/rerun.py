"""Re-runs a methodology's previously-computed subjects/dates under a newly
approved calculation_specification version - the "methodology version
bumped" half of P2's calculation_supersession rerun flow, distinct from
curve_pricing.py's within-spec supersession (which fires when an
instrument's own inputs change under the *same* spec).

calculation/models.py's own docstring is explicit that, unlike
accepted_fact, calculation_result has no single-canonical-value invariant:
"multiple calculation_specification versions ... legitimately coexist for
the same subject/metric/date". So this never marks a previous version's
results SUPERSEDED or touches them at all - it only produces new ACTIVE
rows under the new spec for whichever (subject, as_of_date) pairs already
had a result under the previous one, exactly as the plan specifies:
"produce new versioned results without mutating history".
"""

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import (
    STATUS_APPROVED,
    CalculationResult,
    CalculationSpecification,
)
from app.modules.calculation.pipeline.curve_pricing import (
    METRIC_MODEL_IMPLIED_CLEAN_PRICE,
    ModelImpliedPriceComputed,
    ModelImpliedPriceSkipped,
    compute_and_persist_model_implied_price,
)


@dataclass(frozen=True)
class RerunRefused:
    reason: str


@dataclass(frozen=True)
class RerunOutcome:
    subject_id: uuid.UUID
    as_of_date: dt.date
    result: ModelImpliedPriceComputed | ModelImpliedPriceSkipped


async def rerun_for_new_specification_version(
    session: AsyncSession,
    *,
    previous_specification_id: uuid.UUID,
    new_specification_id: uuid.UUID,
) -> list[RerunOutcome] | RerunRefused:
    # Same fail-closed discipline as compute_and_persist_model_implied_price
    # itself: refusing here, before even looking up candidates, means a
    # DRAFT/unapproved spec can never be the target of a rerun either.
    if previous_specification_id == new_specification_id:
        return RerunRefused(
            reason="previous and new calculation_specification_id are the same"
        )

    new_spec = await session.get(CalculationSpecification, new_specification_id)
    if new_spec is None or new_spec.status != STATUS_APPROVED:
        return RerunRefused(
            reason=(
                f"calculation_specification {new_specification_id} is not APPROVED "
                f"(status={new_spec.status if new_spec is not None else 'MISSING'}) - "
                "refusing to rerun under an unvetted methodology"
            )
        )

    pairs = (
        await session.execute(
            select(CalculationResult.subject_id, CalculationResult.as_of_date)
            .where(
                CalculationResult.calculation_specification_id == previous_specification_id,
                CalculationResult.metric_id == METRIC_MODEL_IMPLIED_CLEAN_PRICE,
                CalculationResult.status == "ACTIVE",
            )
            .distinct()
        )
    ).all()

    outcomes = []
    for subject_id, as_of_date in pairs:
        result = await compute_and_persist_model_implied_price(
            session,
            instrument_id=subject_id,
            as_of_date=as_of_date,
            calculation_specification_id=new_specification_id,
        )
        outcomes.append(RerunOutcome(subject_id=subject_id, as_of_date=as_of_date, result=result))
    return outcomes
