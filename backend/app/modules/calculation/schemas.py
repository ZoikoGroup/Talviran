import datetime as dt
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CalculationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    calculation_specification_id: UUID
    subject_type: str
    subject_id: UUID
    metric_id: str
    as_of_date: dt.date
    basis: str
    value: dict[str, Any]
    status: str


class CalculationInputOut(BaseModel):
    accepted_fact_id: UUID
    role: str


class CalculationResultDetailOut(CalculationResultOut):
    inputs: list[CalculationInputOut]
