from fastapi import APIRouter, Query

from app.modules.api.v1.deps import SessionDep
from app.modules.reference import service
from app.modules.reference.schemas import IssuerOut, PageOut

router = APIRouter(prefix="/issuers", tags=["reference"])


@router.get("", response_model=PageOut[IssuerOut])
async def list_issuers(
    session: SessionDep,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> PageOut[IssuerOut]:
    page = await service.list_issuers(session, cursor=cursor, limit=limit)
    return PageOut[IssuerOut](
        items=[IssuerOut.model_validate(row) for row in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )
