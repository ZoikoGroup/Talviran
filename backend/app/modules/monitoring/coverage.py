"""Coverage tracking (MON-001 §12): "is this rule actually being evaluated
on schedule" - a concern independent of whether any evaluation ever
produces a MATCH. Two halves, deliberately separate calls (mirroring this
module's own composable-steps convention - evaluate/create-alert/deliver
are already three separate calls, not one auto-chaining function):

  record_successful_evaluation() - called right after a real (non-skipped)
  evaluation; always moves a rule back to HEALTHY and closes any open
  incident. This is presence-based: something happened.

  check_rule_coverage() - called periodically, independent of any specific
  evaluation; detects the ABSENCE of activity by comparing elapsed time
  since the last successful evaluation against expected_evaluation_interval
  (see models.py's docstring for why that's read from market.freshness
  rather than a new config column, and why the four-state ladder's
  multiples are a documented choice, not a MON-001 number).
"""

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.freshness import DEFAULT_PROFILES
from app.modules.monitoring.models import (
    COVERAGE_STATE_AT_RISK,
    COVERAGE_STATE_HEALTHY,
    COVERAGE_STATE_LAPSED,
    COVERAGE_STATE_SUSPENDED,
    MonitoringCoverage,
    MonitoringCoverageIncident,
    MonitoringRuleVersion,
    RuleEvaluation,
)

# Multiples of expected_evaluation_interval - a documented interpretation
# of §12.2's prose, not a MON-001-specified number (see models.py).
_AT_RISK_MULTIPLE = 2
_LAPSED_MULTIPLE = 4


@dataclass(frozen=True)
class CoverageSkipped:
    reason: str


@dataclass(frozen=True)
class CoverageChecked:
    rule_id: uuid.UUID
    coverage_state: str


async def _get_or_create_coverage(
    session: AsyncSession, *, rule_version: MonitoringRuleVersion
) -> MonitoringCoverage:
    coverage = (
        await session.execute(
            select(MonitoringCoverage).where(MonitoringCoverage.rule_id == rule_version.rule_id)
        )
    ).scalar_one_or_none()
    if coverage is None:
        coverage = MonitoringCoverage(
            account_id=rule_version.account_id,
            rule_id=rule_version.rule_id,
            current_rule_version_id=rule_version.id,
            coverage_state=COVERAGE_STATE_HEALTHY,
        )
        session.add(coverage)
        await session.flush()
    return coverage


async def record_successful_evaluation(
    session: AsyncSession, *, rule_evaluation_id: uuid.UUID
) -> CoverageChecked | CoverageSkipped:
    evaluation = await session.get(RuleEvaluation, rule_evaluation_id)
    if evaluation is None:
        return CoverageSkipped(reason=f"no rule_evaluation {rule_evaluation_id}")

    rule_version = await session.get(MonitoringRuleVersion, evaluation.rule_version_id)
    assert rule_version is not None  # FK guarantees this

    coverage = await _get_or_create_coverage(session, rule_version=rule_version)
    coverage.current_rule_version_id = rule_version.id
    coverage.last_successful_evaluation_at = evaluation.evaluated_at
    coverage.last_evaluation_outcome = evaluation.outcome
    coverage.coverage_state = COVERAGE_STATE_HEALTHY
    coverage.lapse_started_at = None

    if coverage.current_incident_id is not None:
        incident = await session.get(MonitoringCoverageIncident, coverage.current_incident_id)
        if incident is not None and incident.resolved_at is None:
            incident.resolved_at = evaluation.evaluated_at
        coverage.current_incident_id = None

    await session.flush()
    return CoverageChecked(rule_id=rule_version.rule_id, coverage_state=coverage.coverage_state)


async def check_rule_coverage(
    session: AsyncSession, *, rule_id: uuid.UUID, now: dt.datetime | None = None
) -> CoverageChecked | CoverageSkipped:
    """Detects a lapse independent of any new evaluation - the "absence of
    activity" half. Opens a new incident the moment coverage first crosses
    into LAPSED; an already-open incident is left as-is (it closes only
    via record_successful_evaluation, never by this function).
    """
    coverage = (
        await session.execute(
            select(MonitoringCoverage).where(MonitoringCoverage.rule_id == rule_id)
        )
    ).scalar_one_or_none()
    if coverage is None:
        return CoverageSkipped(reason=f"no monitoring_coverage row for rule {rule_id}")

    rule_version = await session.get(MonitoringRuleVersion, coverage.current_rule_version_id)
    assert rule_version is not None  # FK guarantees this

    profile = DEFAULT_PROFILES.get(rule_version.metric_id)
    if profile is None:
        return CoverageSkipped(
            reason=f"no FreshnessProfile registered for metric_id={rule_version.metric_id!r}"
        )
    expected_interval = profile.freshness_slo

    moment = now or dt.datetime.now(dt.UTC)
    reference_time = coverage.last_successful_evaluation_at or rule_version.effective_from
    age = moment - reference_time

    if age <= expected_interval:
        new_state = COVERAGE_STATE_HEALTHY
    elif age <= expected_interval * _AT_RISK_MULTIPLE:
        new_state = COVERAGE_STATE_AT_RISK
    elif age <= expected_interval * _LAPSED_MULTIPLE:
        new_state = COVERAGE_STATE_LAPSED
    else:
        new_state = COVERAGE_STATE_SUSPENDED

    was_healthy_or_at_risk = coverage.coverage_state in (
        COVERAGE_STATE_HEALTHY, COVERAGE_STATE_AT_RISK,
    )
    entering_lapse = was_healthy_or_at_risk and new_state in (
        COVERAGE_STATE_LAPSED, COVERAGE_STATE_SUSPENDED,
    )

    coverage.coverage_state = new_state
    if entering_lapse:
        coverage.lapse_started_at = moment
        incident = MonitoringCoverageIncident(
            account_id=coverage.account_id,
            rule_id=rule_id,
            started_at=moment,
            reason=(
                f"no successful evaluation since {reference_time.isoformat()} "
                f"(expected every {expected_interval})"
            ),
        )
        session.add(incident)
        await session.flush()
        coverage.current_incident_id = incident.id

    await session.flush()
    return CoverageChecked(rule_id=rule_id, coverage_state=new_state)
