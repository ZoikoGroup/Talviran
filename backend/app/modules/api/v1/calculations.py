"""GET /api/v1/calculations (P2) - calculation_result was only ever
surfaced indirectly before this, embedded in a POST /api/v1/research
reply's fact table. Mirrors instruments.py/issuers.py's shape exactly:
unauthenticated, PDP-gated (platform-owned rights profile), cursor-paginated.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.errors import ErrorCode, TalvrinAPIError
from app.core.pagination import PageOut
from app.modules.api.v1.deps import SessionDep
from app.modules.calculation import service
from app.modules.calculation.schemas import (
    CalculationInputOut,
    CalculationResultDetailOut,
    CalculationResultOut,
)

router = APIRouter(prefix="/calculations", tags=["calculations"])


def _not_found() -> TalvrinAPIError:
    return TalvrinAPIError(code=ErrorCode.NOT_FOUND, message="Not found.")


@router.get("", response_model=PageOut[CalculationResultOut])
async def list_calculations(
    session: SessionDep,
    subject_id: Annotated[uuid.UUID | None, Query()] = None,
    metric_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> PageOut[CalculationResultOut]:
    page = await service.list_calculation_results(
        session, subject_id=subject_id, metric_id=metric_id, cursor=cursor, limit=limit
    )
    return PageOut[CalculationResultOut](
        items=[CalculationResultOut.model_validate(row) for row in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get("/{result_id}", response_model=CalculationResultDetailOut)
async def get_calculation(
    result_id: uuid.UUID, session: SessionDep
) -> CalculationResultDetailOut:
    found = await service.get_calculation_result(session, result_id=result_id)
    if found is None:
        raise _not_found()
    result, inputs = found
    return CalculationResultDetailOut(
        **CalculationResultOut.model_validate(result).model_dump(),
        inputs=[
            CalculationInputOut(accepted_fact_id=i.accepted_fact_id, role=i.role) for i in inputs
        ],
    )
