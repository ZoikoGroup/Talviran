"""monitoring schema (PLT-MON-001) — rule definitions and their evaluation
history. First slice only: enough to define a rule watching a single
scalar metric with a crossing predicate, and to record each evaluation of
it. Deliberately NOT modelled yet, because nothing in this slice's engine
uses them (adding unused columns "for later" is exactly the premature
schema design MON-001 itself doesn't hand down concrete values for
anyway — see rule_engine.py's docstring):
  - threshold_unit, comparison_basis, evaluation_window (needed for
    CHANGES_BY/ENTERS_STATE/DOCUMENT_PUBLISHED/EVENT_SCHEDULED — only
    CROSSES_ABOVE/CROSSES_BELOW are implemented so far)
  - market_hours_mode, user_timezone, quiet_hours_policy_id. Both §8
    concepts ARE modelled now: rearm_threshold (hysteresis, with a
    concrete worked example, §8.1) and debounce_seconds (defined only
    conceptually in §8's own table - "minimum interval between qualifying
    business fires for the same rule version" - with no field name, no
    worked example, and no default duration anywhere in the spec; 0 is the
    only sensible non-configured default, meaning "no debounce", since a
    positive default would silently change a rule's economic meaning,
    which §8.2 explicitly forbids doing without the user's explicit
    choice).
  - schedule_id, delivery_profile_id (no scheduler or notification/alert
    delivery module exists yet — those are separate later slices)
  - SUSPENDED as a RuleVersion.status value: resolved, not just deferred,
    now that coverage tracking is real (see MonitoringCoverage below).
    §12.1's own CoverageRecord.coverage_state enum lists both SUSPENDED
    and PAUSED as coverage states in their own right - RuleVersion.status
    keeps §4.1's literal DRAFT/ARMED/PAUSED/RETIRED list unchanged; a
    rule's coverage can independently become SUSPENDED without its
    RuleVersion.status itself ever changing.

Rules are user-owned, unlike reference/calculation data — every table
here carries account_id and gets a real Postgres RLS policy in the
migration that creates it (identity.principal/session, governance.
policy_decision and every research.* table already follow this; the
lesson from that pattern is "cheap now, expensive retrofitted").

input_fact_ids in MON-001's own example DDL (§19.2) is a plain uuid[]
array column. This project already has an established, queryable pattern
for "which accepted_fact rows fed this decision" — calculation_input,
a proper join table — used for the exact same evidence-traceability
requirement. RuleEvaluationInput mirrors that instead of introducing a
new array-column idiom for one table.

Alert (MON-001 §13.1) is trimmed the same way as RuleVersion: `unit`,
`valid_time`, `input_freshness_state` aren't populated by anything yet, so
they're left out rather than added as always-null columns. evidence_bundle_id
is real, not deferred: evidence.evidence_bundle already exists (P1 week 13)
and alerts.py links every alert to the same accepted_fact its triggering
evaluation used, exactly like evidence/service.py already does for
research replies.

AlertDeliveryAttempt/delivery.py (MON-001 §14) implement exactly one
transport, IN_APP - an alert becomes "delivered" the moment it's visible
through GET /api/v1/alerts, which needs no external provider/credentials
at all (matching "prove it in Postgres first" applied to delivery, not
just ingestion). Real push transports (email/SMS/webhook) and §14.2's
retry policy are separate, later slices - QUEUED as an Alert.status value
and retry/backoff bookkeeping on AlertDeliveryAttempt are left out
because nothing here needs them yet: IN_APP delivery either succeeds
synchronously or the whole request fails, there is no in-between state to
model. SUPPRESSED/ACKNOWLEDGED/CORRECTED need suppression rules and user
acknowledgement actions that don't exist yet either.

MonitoringCoverage/MonitoringCoverageIncident (MON-001 §12) answer "is
this rule actually being evaluated on schedule" - a concern completely
independent of whether any evaluation ever produces a MATCH. No
scheduler exists yet (schedule_id is still deferred), so
expected_evaluation_interval isn't a new per-rule config surface: it's
read straight from market.freshness's existing per-metric
FreshnessProfile.freshness_slo - "how often is this metric expected to
publish" and "how often should a rule watching it be re-evaluated" are
the same cadence, and reusing that registry avoids inventing a second one
MON-001 doesn't hand down numbers for either. The four-state ladder
(HEALTHY -> AT_RISK -> LAPSED -> SUSPENDED) is a documented interpretation
of §12.2's prose ("beyond the permitted gap... LAPSED and then SUSPENDED
according to the approved threshold") using simple multiples of
expected_evaluation_interval, the same kind of explicit, stated
simplification as freshness.py's own threshold choices - not a literal
transcription, since MON-001 gives no concrete numbers here either.

CoverageIncident has no field-level shape in MON-001 itself (§3.1 gives
only a one-line purpose statement) - this is this module's own minimal
design: who/what lapsed, when, and when (if ever) it recovered.

The dead-man watcher itself (§12.3 - an independently-deployed process
watching the evaluator's own heartbeat, a different failure mode than
"is a specific rule stale") is a genuinely separate script
(scripts.run_deadman_watcher), not a function called from inside the
evaluator - MON-001's own explicit doctrine ("An evaluator process cannot
be trusted to report that it has died") rules out anything less: it must
be a second real process, run and deployed independently of
scripts.run_monitoring_worker.
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

# rule_evaluation_input.accepted_fact_id/calculation_result_id and
# alert.evidence_bundle_id below declare cross-schema FKs by string - same
# import-resolution requirement as calculation/models.py and
# policy/models.py before it: the module declaring the FK must guarantee
# its target is imported.
from app.modules.calculation import models as _calculation_models  # noqa: F401
from app.modules.evidence import models as _evidence_models  # noqa: F401
from app.modules.market import models as _market_models  # noqa: F401

STATUS_DRAFT = "DRAFT"
STATUS_ARMED = "ARMED"
STATUS_PAUSED = "PAUSED"
STATUS_RETIRED = "RETIRED"

SUBJECT_TYPE_INSTRUMENT = "INSTRUMENT"

PREDICATE_CROSSES_ABOVE = "CROSSES_ABOVE"
PREDICATE_CROSSES_BELOW = "CROSSES_BELOW"

TRIGGER_TYPE_FACT_PUBLISHED = "FACT_PUBLISHED"

RULE_INPUT_KIND_FACT = "FACT"
RULE_INPUT_KIND_CALCULATION = "CALCULATION"

ALERT_TYPE_CROSSING = "CROSSING"
ALERT_TYPE_INITIAL_STATE = "INITIAL_STATE"

STATUS_ALERT_CREATED = "CREATED"
STATUS_ALERT_SUPPRESSED = "SUPPRESSED"
STATUS_ALERT_DELIVERED = "DELIVERED"
STATUS_ALERT_DELIVERY_FAILED = "DELIVERY_FAILED"

SUPPRESSION_REASON_DEBOUNCE = "DEBOUNCE"

TRANSPORT_IN_APP = "IN_APP"

DELIVERY_ATTEMPT_DELIVERED = "DELIVERED"
DELIVERY_ATTEMPT_FAILED = "FAILED"

OUTCOME_INITIAL_STATE = "INITIAL_STATE"
OUTCOME_MATCH = "MATCH"
OUTCOME_STILL_MATCHED = "STILL_MATCHED"
OUTCOME_NO_MATCH = "NO_MATCH"
OUTCOME_REARMED = "REARMED"
OUTCOME_ERROR = "ERROR"

# Outcomes that mean "the rule is currently disarmed - it has fired and not
# yet passed back through its rearm_threshold" (MON-001 §8's own worked
# example: STILL_MATCHED persists through a wobble in the dead zone: only
# dropping past rearm_threshold produces REARMED, and only a *subsequent*
# re-crossing of the primary threshold after that produces a fresh MATCH).
DISARMED_OUTCOMES = (OUTCOME_MATCH, OUTCOME_STILL_MATCHED)

COVERAGE_STATE_HEALTHY = "HEALTHY"
COVERAGE_STATE_AT_RISK = "AT_RISK"
COVERAGE_STATE_LAPSED = "LAPSED"
COVERAGE_STATE_SUSPENDED = "SUSPENDED"


class MonitoringRule(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The stable identity a rule keeps across versions (MON-001 §3.1) — a
    rule is edited by creating a new MonitoringRuleVersion, never by
    mutating one in place (mirrors calculation_specification's own
    versioning discipline).
    """

    __tablename__ = "monitoring_rule"
    __table_args__ = {"schema": "monitoring"}

    account_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    current_rule_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), default=None
    )


class MonitoringRuleVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One version of one rule's definition (MON-001 §4.1's RuleVersion,
    trimmed to this slice's implemented fields — see module docstring).
    """

    __tablename__ = "monitoring_rule_version"
    __table_args__ = {"schema": "monitoring"}

    account_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("monitoring.monitoring_rule.id"), index=True
    )
    version: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), default=STATUS_DRAFT)
    subject_type: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    metric_id: Mapped[str] = mapped_column(String(64))
    predicate: Mapped[str] = mapped_column(String(32))
    threshold_value: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    # MON-001 §8: hysteresis is modelled as a second absolute threshold, not
    # a percentage/margin field - `rearm_below` in the spec's own worked
    # example, generalized here to rearm_threshold since the same field
    # means "rearm above" for CROSSES_BELOW. Optional: unset means no
    # hysteresis at all, and the rule fires on every raw crossing exactly
    # as it did before this feature existed - §8.2 itself gives no default
    # margin ("must not encode an investment view... the user must
    # explicitly choose it"), so there is no sensible non-None default.
    rearm_threshold: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), default=None)
    # MON-001 §8: "minimum interval between qualifying business fires for
    # the same rule version" - measured against knowledge_time (when each
    # fact became known), not wall-clock processing time, for the same
    # bitemporal-consistency reason every other time comparison in this
    # module uses knowledge_time. 0 means no debounce (the only sensible
    # default - see module docstring).
    debounce_seconds: Mapped[int] = mapped_column(default=0)
    effective_from: Mapped[dt.datetime]
    effective_to: Mapped[dt.datetime | None] = mapped_column(default=None)
    created_by_principal_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True))


class RuleEvaluation(UUIDPrimaryKeyMixin, Base):
    """One immutable, deterministic evaluation result for one rule version
    at one trigger point (MON-001 §3.1/§7.1). evaluation_key enforces the
    idempotency §7.1 requires: the same rule version + trigger + knowledge
    time + evaluator version must never produce a second row.
    """

    __tablename__ = "rule_evaluation"
    __table_args__ = {"schema": "monitoring"}

    account_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    evaluation_key: Mapped[str] = mapped_column(String(128), unique=True)
    rule_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("monitoring.monitoring_rule_version.id"), index=True
    )
    trigger_type: Mapped[str] = mapped_column(String(32))
    trigger_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), default=None)
    knowledge_time: Mapped[dt.datetime]
    evaluator_version: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(32))
    evaluated_at: Mapped[dt.datetime] = mapped_column(default=lambda: dt.datetime.now(dt.UTC))


class RuleEvaluationInput(UUIDPrimaryKeyMixin, Base):
    """Which fact or calculation result fed a given evaluation — a
    discriminated union via `kind` + nullable FKs, exactly one populated
    per row, mirroring evidence.EvidenceMember's identical pattern for the
    identical problem ("could be one of several truth-bearing tables").
    NEVER a direct reference to a raw source_observation, same
    evidence-traceability rule as calculation_input.
    """

    __tablename__ = "rule_evaluation_input"
    __table_args__ = {"schema": "monitoring"}

    account_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    rule_evaluation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("monitoring.rule_evaluation.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))  # FACT | CALCULATION
    accepted_fact_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("market.accepted_fact.id"), index=True, default=None
    )
    calculation_result_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("calculation.calculation_result.id"),
        index=True, default=None,
    )
    role: Mapped[str] = mapped_column(String(32))  # e.g. CURRENT_VALUE, PREVIOUS_VALUE


class Alert(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One user-facing alert, created from a MATCH/INITIAL_STATE evaluation
    (MON-001 §13.1, trimmed - see module docstring). At most one alert per
    evaluation: evaluation_id is unique, matching §19.1's "Alert references
    exactly one evaluation_id" constraint.
    """

    __tablename__ = "alert"
    __table_args__ = {"schema": "monitoring"}

    account_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("monitoring.monitoring_rule.id"), index=True
    )
    rule_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("monitoring.monitoring_rule_version.id"), index=True
    )
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("monitoring.rule_evaluation.id"), unique=True
    )
    alert_type: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    metric_id: Mapped[str] = mapped_column(String(64))
    observed_value: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    threshold_value: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    knowledge_time: Mapped[dt.datetime]
    evidence_bundle_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence.evidence_bundle.id"), default=None
    )
    status: Mapped[str] = mapped_column(String(16), default=STATUS_ALERT_CREATED)


class AlertSuppression(UUIDPrimaryKeyMixin, Base):
    """MON-001 §15.2's alert_suppression, only the DEBOUNCE reason
    implemented this slice (QUIET_HOURS/RATE_LIMIT/FLAPPING/DIGEST all need
    features that don't exist yet - quiet-hours policies, per-account rate
    limits, flap detection, digests).

    A debounced alert is still created (status=SUPPRESSED, not skipped
    entirely) - the crossing genuinely happened and must stay in the
    historical record; only its delivery is withheld. Matches DATA-002's
    own doctrine elsewhere in this codebase: never silently drop a real
    event, record what happened and why it wasn't surfaced.
    """

    __tablename__ = "alert_suppression"
    __table_args__ = {"schema": "monitoring"}

    account_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    alert_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("monitoring.alert.id"), index=True
    )
    reason: Mapped[str] = mapped_column(String(32))
    policy_version: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[dt.datetime]
    expires_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    released_via_alert_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("monitoring.alert.id"), default=None
    )


class AlertDeliveryAttempt(UUIDPrimaryKeyMixin, Base):
    """One row per delivery attempt (MON-001 §14, monitoring_alert_delivery_attempt
    → simplified here to alert_delivery_attempt, matching this slice's only
    transport). At-least-once semantics start with recording every attempt,
    even a same-transport retry - never overwriting a prior attempt's row.
    """

    __tablename__ = "alert_delivery_attempt"
    __table_args__ = {"schema": "monitoring"}

    account_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    alert_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("monitoring.alert.id"), index=True
    )
    transport: Mapped[str] = mapped_column(String(16))
    attempt_number: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(String(500), default=None)
    attempted_at: Mapped[dt.datetime] = mapped_column(default=lambda: dt.datetime.now(dt.UTC))


class MonitoringCoverage(UUIDPrimaryKeyMixin, Base):
    """One row per rule (MON-001 §12.1) - upserted, not appended, since
    only the current health matters here; MonitoringCoverageIncident below
    is the append-only history.
    """

    __tablename__ = "monitoring_coverage"
    __table_args__ = {"schema": "monitoring"}

    account_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("monitoring.monitoring_rule.id"), unique=True
    )
    current_rule_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("monitoring.monitoring_rule_version.id")
    )
    last_successful_evaluation_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    last_evaluation_outcome: Mapped[str | None] = mapped_column(String(32), default=None)
    coverage_state: Mapped[str] = mapped_column(String(16), default=COVERAGE_STATE_HEALTHY)
    lapse_started_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    current_incident_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), default=None
    )


class MonitoringCoverageIncident(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only lapse/suspension history (MON-001 §3.1's CoverageIncident
    - no field shape given there beyond a one-line purpose statement, so
    this is this module's own minimal design).
    """

    __tablename__ = "monitoring_coverage_incident"
    __table_args__ = {"schema": "monitoring"}

    account_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("monitoring.monitoring_rule.id"), index=True
    )
    started_at: Mapped[dt.datetime]
    resolved_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    reason: Mapped[str] = mapped_column(String(500))


class EvaluatorHeartbeat(UUIDPrimaryKeyMixin, Base):
    """MON-001 §12.3's dead-man control: the evaluator process (scripts.
    run_monitoring_worker) writes here on every sweep; a genuinely separate
    process (scripts.run_deadman_watcher) reads it. Platform-wide
    operational data, not user data - no account_id/RLS, same reasoning as
    governance.kill_switch (one row per named worker, not per tenant).
    """

    __tablename__ = "evaluator_heartbeat"
    __table_args__ = {"schema": "monitoring"}

    worker_id: Mapped[str] = mapped_column(String(64), unique=True)
    last_heartbeat_at: Mapped[dt.datetime]
