"""calculation schema — everything Talvrin computes, as distinct from
everything it observes/reconciles (market.accepted_fact). This distinction
is load-bearing, not cosmetic: `calculation_result` is what backs the
`CALCULATION_RESULT` AllowedOutputType, `accepted_fact` backs
`FACTUAL_EVIDENCE` — a computed estimate must never be written into
`accepted_fact`, and a real observed value must never masquerade as a
calculation. See app/modules/calculation/specs/gilt_price_from_curve_v1's
docstring for why this matters concretely (a curve-implied gilt price is
not the same claim as an observed market price).

Unlike accepted_fact, calculation_result has no bitemporal exclusion
constraint: multiple calculation_specification versions — or entirely
different specs — legitimately coexist for the same subject/metric/date
(that's the whole point of calculation_specification_id being part of a
result's identity), so "one canonical value" isn't the invariant here the
way it is for accepted_fact.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

# calculation_input.accepted_fact_id below declares an FK to
# market.accepted_fact by string — same cross-module import-resolution
# lesson as policy/models.py (week 3) and market/models.py (week 9): the
# module declaring a cross-schema FK must guarantee its target is imported.
from app.modules.market import models as _market_models  # noqa: F401

STATUS_DRAFT = "DRAFT"
STATUS_APPROVED = "APPROVED"
STATUS_DEPRECATED = "DEPRECATED"

BASIS_MODEL_IMPLIED = "MODEL_IMPLIED"
BASIS_OBSERVED_YIELD_DERIVED = "OBSERVED_YIELD_DERIVED"


class CalculationSpecification(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One row per (code, version) — FIN-001's dual-implementation +
    golden-test gate is what moves a spec from DRAFT to APPROVED; nothing
    in this schema enforces that gate itself (it's a CI/release-process
    gate, not a DB constraint), so `status` here is a record of that
    decision, not something the app can set unilaterally at compute time.
    """

    __tablename__ = "calculation_specification"
    __table_args__ = {"schema": "calculation"}

    code: Mapped[str] = mapped_column(String(64), unique=True)  # e.g. gilt_price_yield_v1
    version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default=STATUS_DRAFT)
    description: Mapped[str] = mapped_column(String(500))


class CalculationResult(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """`basis` records whether this value is derived from a real observed
    input (OBSERVED_YIELD_DERIVED) or is an estimate Talvrin computed with
    no real market quote behind it (MODEL_IMPLIED) — surfaced to the
    evidence/citation layer so a model-implied value is never displayed
    with market-price wording.
    """

    __tablename__ = "calculation_result"
    __table_args__ = {"schema": "calculation"}

    calculation_specification_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("calculation.calculation_specification.id"), index=True
    )
    subject_type: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    metric_id: Mapped[str] = mapped_column(String(64), index=True)
    as_of_date: Mapped[dt.date]
    basis: Mapped[str] = mapped_column(String(32))
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), default=None)


class CalculationInput(UUIDPrimaryKeyMixin, Base):
    """Which accepted_fact row(s) fed a given calculation_result — NEVER a
    direct FK to source_observation (DATA-002: a calculation must be
    traceable to reconciled truth, not to an unreconciled raw candidate).
    """

    __tablename__ = "calculation_input"
    __table_args__ = {"schema": "calculation"}

    calculation_result_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("calculation.calculation_result.id"), index=True
    )
    accepted_fact_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("market.accepted_fact.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(32))  # e.g. CURVE_POINT, REFERENCE_TERMS


STATUS_JOB_PENDING = "PENDING"
STATUS_JOB_CLAIMED = "CLAIMED"
STATUS_JOB_DONE = "DONE"
STATUS_JOB_FAILED = "FAILED"


class CalculationJob(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The out-of-process handoff P2's plan calls for: a request/ingest path
    enqueues a row here instead of calling
    curve_pricing.compute_and_persist_model_implied_price synchronously in
    its own transaction — see pipeline/job_queue.py for the claim/run
    worker loop this feeds. Plain Postgres queue (`FOR UPDATE SKIP LOCKED`),
    not a broker: nowhere near the volume that would justify one.
    """

    __tablename__ = "calculation_job"
    __table_args__ = {"schema": "calculation"}

    calculation_specification_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("calculation.calculation_specification.id")
    )
    subject_type: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    as_of_date: Mapped[dt.date]
    status: Mapped[str] = mapped_column(String(16), default=STATUS_JOB_PENDING, index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String(1000), default=None)
    claimed_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    completed_at: Mapped[dt.datetime | None] = mapped_column(default=None)


class CalculationSupersession(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One row per recalculation that replaces a prior result — the
    calculation-side analogue of market.reconciliation_decision: why a new
    result exists, not just that it does (e.g. "curve updated" vs
    "methodology version bumped").
    """

    __tablename__ = "calculation_supersession"
    __table_args__ = {"schema": "calculation"}

    old_calculation_result_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("calculation.calculation_result.id"), index=True
    )
    new_calculation_result_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("calculation.calculation_result.id"), index=True
    )
    reason: Mapped[str] = mapped_column(String(500))
