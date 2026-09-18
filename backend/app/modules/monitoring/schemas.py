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


class RuleIn(BaseModel):
    metric_id: str
    predicate: str
    threshold_value: Decimal
    #: Required for instrument-scoped metrics (e.g. MODEL_IMPLIED_CLEAN_PRICE).
    instrument_isin: str | None = None
    #: Required for curve-point metrics (e.g. UK_GILT_NOMINAL_SPOT_CURVE).
    tenor_years: Decimal | None = None
    #: MON-001 §8 hysteresis. Unset means no hysteresis - every raw crossing fires.
    rearm_threshold: Decimal | None = None
    #: MON-001 §8 debounce. 0 means no debounce.
    debounce_seconds: int = 0


class RuleOut(BaseModel):
    """`id` is the stable rule id (MonitoringRule.id), not the current
    version's own id - a rule is addressed the same way across every
    version it's ever had, mirroring calculation_specification's own
    versioning discipline.
    """

    id: UUID
    status: str
    subject_type: str
    subject_id: UUID
    metric_id: str
    predicate: str
    threshold_value: Decimal
    rearm_threshold: Decimal | None
    debounce_seconds: int
    effective_from: dt.datetime
    created_at: dt.datetime
