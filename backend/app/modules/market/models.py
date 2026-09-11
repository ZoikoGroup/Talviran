"""market schema — the ingestion-side of DATA-002's pipeline: source ->
dataset -> source_artifact -> source_observation. Platform-wide, not
account-scoped: no RLS here (contrast identity.*).

This is deliberately just the ingestion side (P1 week 7). Reconciliation
and accepted_fact (the only stage allowed to publish truth, per
DATA-002 doctrine) land in week 9 once identity resolution and a
ReconciliationPolicy exist — building accepted_fact before there's a real
reconciliation policy to populate it correctly would invite exactly the
"silently pick a source" anti-pattern DATA-002 forbids.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, TSTZRANGE, Range
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

# SourceObservation.rights_profile_id below declares an FK to
# governance.rights_profile by string. SQLAlchemy only resolves that once
# the target model class has been imported somewhere in the process — see
# app/modules/policy/models.py for the identical lesson (week 3), caught
# the exact same way: passing when the full suite happens to import
# app.modules.rights.models first, failing when a narrower test file
# (e.g. test_market_evidence_schema.py) doesn't. The module declaring the
# cross-schema FK is responsible for guaranteeing its target is loaded.
from app.modules.rights import models as _rights_models  # noqa: F401


class Source(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One row per external data source (e.g. "uk-dmo"). RIGHTS-001's
    Source Registry lifecycle (DISCOVERED -> ... -> PRODUCTION) is not
    modelled yet — `status` is a placeholder until that's built.
    """

    __tablename__ = "source"
    __table_args__ = {"schema": "market"}

    code: Mapped[str] = mapped_column(String(64), unique=True)  # e.g. "uk-dmo"
    name: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class Dataset(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One row per distinct feed within a source (e.g. "gilts-in-issue" vs
    "gilt-closing-prices" are two datasets under the same uk-dmo source).
    """

    __tablename__ = "dataset"
    __table_args__ = {"schema": "market"}

    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("market.source.id"), index=True
    )
    code: Mapped[str] = mapped_column(String(64))  # e.g. "gilts-in-issue"
    name: Mapped[str] = mapped_column(String(300))


class SourceArtifact(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Immutable manifest of one raw acquisition — nothing is parsed or
    transformed without one existing first (DATA-002 §3.1). `storage_ref`
    points at where the raw bytes actually live; the object-storage
    backend itself (S3-compatible per ENG-ARCH-003) isn't wired up yet —
    week 8's connector work decides that alongside the first real writer.
    """

    __tablename__ = "source_artifact"
    __table_args__ = {"schema": "market"}

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("market.dataset.id"), index=True
    )
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_ref: Mapped[str] = mapped_column(String(500))
    media_type: Mapped[str] = mapped_column(String(120))
    byte_length: Mapped[int]
    retrieved_at: Mapped[dt.datetime]
    published_at: Mapped[dt.datetime | None] = mapped_column(default=None)


class SourceObservation(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Raw, append-only candidate values from one source — never truth by
    itself (DATA-002/ENG-ARCH-003 D-1: three truth classes, never merged).
    `rights_profile_id` is now a real FK (week 9 closes the loop promised
    in week 7/8: the first real write path — app.modules.market.pipeline —
    lands this week, so every row genuinely carries a rights profile from
    here on). subject_id is nullable until identity resolution
    (deterministic ISIN match, never fuzzy) assigns it.
    """

    __tablename__ = "source_observation"
    __table_args__ = {"schema": "market"}

    source_artifact_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("market.source_artifact.id"), index=True
    )
    rights_profile_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("governance.rights_profile.id")
    )
    subject_type: Mapped[str] = mapped_column(String(32))  # e.g. INSTRUMENT
    subject_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), default=None)
    metric_id: Mapped[str] = mapped_column(String(64), index=True)  # e.g. CLEAN_PRICE
    # Idempotent-write key: hash of source+dataset+record_key+subject+metric
    # +valid_from/as-of (DATA-002 §3). Unique so a connector re-running over
    # the same source data never double-inserts.
    semantic_observation_key: Mapped[str] = mapped_column(String(128), unique=True)
    raw_value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    valid_from: Mapped[dt.date | None] = mapped_column(default=None)
    observed_at: Mapped[dt.datetime]


class AcceptedFact(UUIDPrimaryKeyMixin, Base):
    """Canonical, bitemporal truth (ENG-ARCH-003 D-1) — the only table
    reconciliation is allowed to write. `valid_range`/`knowledge_range` are
    the two temporal axes DATA-001 mandates; a GiST exclusion constraint
    (added via raw SQL in the migration, using btree_gist) enforces at the
    DB level that no two versions of the same (subject_id, metric_id) can
    overlap on BOTH ranges simultaneously — this is a real constraint, not
    just an app-level check, precisely because app-level checks don't
    survive concurrent writers.
    """

    __tablename__ = "accepted_fact"
    __table_args__ = {"schema": "market"}

    subject_type: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    metric_id: Mapped[str] = mapped_column(String(64), index=True)
    valid_range: Mapped[Range[dt.datetime]] = mapped_column(TSTZRANGE)
    knowledge_range: Mapped[Range[dt.datetime]] = mapped_column(TSTZRANGE)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # ACTIVE | SUPERSEDED | REVOKED
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), default=None)


class ReconciliationDecision(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One row per reconciliation attempt, regardless of outcome — this is
    what lets "why does this fact say what it says" be reconstructed later
    (ENG-ARCH-003's auditability doctrine), including the CONFLICT cases
    that produced no accepted_fact at all.
    """

    __tablename__ = "reconciliation_decision"
    __table_args__ = {"schema": "market"}

    subject_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    metric_id: Mapped[str] = mapped_column(String(64), index=True)
    decision: Mapped[str] = mapped_column(String(16))  # ACCEPTED | CONFLICT | NO_CHANGE
    reason: Mapped[str] = mapped_column(String(500))
    accepted_fact_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("market.accepted_fact.id"), default=None
    )


class FactObservationLink(UUIDPrimaryKeyMixin, Base):
    """Many-to-many: which source_observation row(s) fed a given
    accepted_fact, and in what role (DATA-001)."""

    __tablename__ = "fact_observation_link"
    __table_args__ = {"schema": "market"}

    accepted_fact_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("market.accepted_fact.id"), index=True
    )
    source_observation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("market.source_observation.id"), index=True
    )
    # PRIMARY | CONFIRMING | CONFLICTING | DERIVATION_INPUT
    role: Mapped[str] = mapped_column(String(20))


class OutboxEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Transactional outbox — written in the same transaction as the
    accepted_fact it announces (ENG-ARCH-003: outbox + durable job table in
    Postgres, no Kafka at launch). Nothing consumes this yet (P3 monitoring
    will) — it exists now so `publish` is genuinely transactional from day
    one, not retrofitted once a consumer exists.
    """

    __tablename__ = "outbox_event"
    __table_args__ = {"schema": "market"}

    event_type: Mapped[str] = mapped_column(String(64))  # e.g. accepted_fact.published
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    processed_at: Mapped[dt.datetime | None] = mapped_column(default=None)
