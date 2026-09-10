from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PageOut[T](BaseModel):
    """API-001's cursor-pagination envelope, shared by every list endpoint."""

    items: list[T]
    next_cursor: str | None
    has_more: bool


class IssuerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    country_code: str | None
    status: str


class InstrumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    issuer_id: UUID
    instrument_type: str
    name: str
    currency_code: str
    status: str
