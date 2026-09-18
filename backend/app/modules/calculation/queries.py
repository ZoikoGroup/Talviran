"""Shared calculation_result read queries used by more than one module -
consolidated here instead of re-copied per caller (the same reasoning as
market/queries.py: a query worth sharing is worth sharing once, not
duplicating quietly a second time).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import CalculationResult


async def latest_calculation_result(
    session: AsyncSession, *, subject_id: uuid.UUID, metric_id: str
) -> CalculationResult | None:
    """The most recent ACTIVE calculation_result for (subject_id, metric_id)
    - "whatever we most recently computed", not scoped to any particular
    calculation_specification_id (different spec versions legitimately
    coexist, calculation/models.py's own docstring - the caller doesn't
    care which methodology produced the latest number, only what it is).
    """
    return (
        await session.execute(
            select(CalculationResult)
            .where(
                CalculationResult.subject_id == subject_id,
                CalculationResult.metric_id == metric_id,
                CalculationResult.status == "ACTIVE",
            )
            .order_by(CalculationResult.as_of_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
