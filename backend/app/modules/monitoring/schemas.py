import datetime as dt
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_id: UUID
    rule_version_id: UUID
    evaluation_id: UUID
    alert_type: str
    subject_id: UUID
    metric_id: str
    observed_value: Decimal
    threshold_value: Decimal
    knowledge_time: dt.datetime
    evidence_bundle_id: UUID | None
    status: str
    created_at: dt.datetime
