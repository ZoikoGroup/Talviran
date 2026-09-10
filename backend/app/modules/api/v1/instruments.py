from fastapi import APIRouter, Query

from app.modules.api.v1.deps import SessionDep
from app.modules.reference import service
from app.modules.reference.schemas import InstrumentOut, PageOut

router = APIRouter(prefix="/instruments", tags=["reference"])


@router.get("", response_model=PageOut[InstrumentOut])
async def list_instruments(
    session: SessionDep,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> PageOut[InstrumentOut]:
    page = await service.list_instruments(session, cursor=cursor, limit=limit)
    return PageOut[InstrumentOut](
        items=[InstrumentOut.model_validate(row) for row in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )
