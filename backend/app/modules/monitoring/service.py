"""Read access to a signed-in user's own alerts (GET /api/v1/alerts) - the
first user-facing surface for anything monitoring produces. RLS already
scopes every query here to the caller's own account (alert carries
account_id and FORCE ROW LEVEL SECURITY, same as research.message); this
adds the PDP gate on top, exactly like every other response path
(evidence/service.py, calculation/service.py) - RLS restricts WHICH rows
exist for this account, the PDP decides whether this capability is even
switched on at all (kill-switch/jurisdiction/rights precedence).

A GET-only endpoint never has another natural commit point in this
project's per-request session lifecycle (core/db.get_session's own
docstring: "callers commit explicitly") - _enforce_read_access commits
right after evaluate() so the PDP's own audit-log write persists
regardless of whether the request goes on to succeed, mirroring
calculation/service.py's identical need for the identical reason.

Unlike calculation_result, alert is RLS-scoped - and set_config(...,
is_local=true)'s GUC is transaction-local (migration 0002's own reasoning
for using it at all). Committing ends that transaction, which silently
clears app.account_id along with it: the SELECT that follows would run
with no RLS context and match nothing, not "everything" or "an error" -
the single most dangerous failure mode for GUC-based RLS applies here
just as much as to a pooled connection reused across requests. Re-
applying the context immediately after the commit, in the same
already-known account/principal, is what keeps a PERMIT actually able to
read the rows RLS itself allows.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, TalvrinAPIError
from app.core.pagination import Page, paginate_by_id
from app.modules.identity.service import apply_rls_context
from app.modules.market.pipeline.curve_ingest import (
    SUBJECT_TYPE_YIELD_CURVE_POINT,
    curve_point_subject_id,
)
from app.modules.monitoring.models import (
    PREDICATE_CROSSES_ABOVE,
    PREDICATE_CROSSES_BELOW,
    STATUS_ARMED,
    SUBJECT_TYPE_INSTRUMENT,
    Alert,
    MonitoringRule,
    MonitoringRuleVersion,
)
from app.modules.monitoring.rule_engine import CALCULATION_SCALAR_VALUE_KEYS, SCALAR_VALUE_KEYS
from app.modules.policy.allowed_output_type import AllowedOutputType
from app.modules.policy.pdp import PolicyContext, evaluate
from app.modules.reference.models import Instrument, InstrumentAlias

_DEV_JURISDICTION = "GB"
MONITORING_ALERTS_READ_CAPABILITY = "monitoring.alerts.read"
MONITORING_RULES_READ_CAPABILITY = "monitoring.rules.read"
MONITORING_RULES_CREATE_CAPABILITY = "monitoring.rules.create"


@dataclass(frozen=True)
class RuleRejected:
    reason: str


async def _enforce_access(
    session: AsyncSession, *, principal_id: uuid.UUID, account_id: uuid.UUID, capability_code: str
) -> None:
    ctx = PolicyContext(
        principal_id=principal_id,
        account_id=account_id,
        jurisdiction_code=_DEV_JURISDICTION,
        capability_code=capability_code,
        requested_output_type=AllowedOutputType.USER_RULE_ALERT,
    )
    decision = await evaluate(session, ctx)
    await session.commit()
    await apply_rls_context(session, account_id=account_id, principal_id=principal_id)

    if not decision.is_permit:
        raise TalvrinAPIError(
            ErrorCode.POLICY_BLOCKED,
            "Access to this resource is not currently permitted.",
            details={"reason_codes": decision.reason_codes},
        )


async def list_my_alerts(
    session: AsyncSession,
    *,
    principal_id: uuid.UUID,
    account_id: uuid.UUID,
    cursor: str | None,
    limit: int,
) -> Page[Alert]:
    await _enforce_access(
        session,
        principal_id=principal_id,
        account_id=account_id,
        capability_code=MONITORING_ALERTS_READ_CAPABILITY,
    )
    stmt = select(Alert)
    return await paginate_by_id(
        session, stmt, Alert.id, cursor=cursor, limit=limit, get_id=lambda row: row.id
    )


async def get_my_alert(
    session: AsyncSession, *, alert_id: uuid.UUID, principal_id: uuid.UUID, account_id: uuid.UUID
) -> Alert | None:
    await _enforce_access(
        session,
        principal_id=principal_id,
        account_id=account_id,
        capability_code=MONITORING_ALERTS_READ_CAPABILITY,
    )
    return await session.get(Alert, alert_id)


async def create_rule(
    session: AsyncSession,
    *,
    principal_id: uuid.UUID,
    account_id: uuid.UUID,
    metric_id: str,
    predicate: str,
    threshold_value: Decimal,
    instrument_isin: str | None,
    tenor_years: Decimal | None,
    rearm_threshold: Decimal | None,
    debounce_seconds: int,
) -> MonitoringRuleVersion | RuleRejected:
    """Creates a rule, already ARMED (MON-001 §4) - this slice has no
    separate draft/activate flow, so a rule stuck in DRAFT would just be a
    rule that silently never evaluates.

    subject_type/subject_id are never taken from the caller - both
    watchable metrics already have an established resolution path
    elsewhere in this codebase (curve_ingest's deterministic tenor->UUID5
    derivation; instrument_alias's ISIN lookup, the same one evidence/
    service.py's gilt-facts branch uses). A caller-supplied subject_id
    would let someone create a rule that looks valid but silently never
    fires, because nothing ever publishes a fact/result under that id -
    worse than rejecting the request outright. A new watchable metric
    registers its own resolution here, and in rule_engine.py's
    SCALAR_VALUE_KEYS/CALCULATION_SCALAR_VALUE_KEYS, not by widening this
    function's parameter list.
    """
    await _enforce_access(
        session,
        principal_id=principal_id,
        account_id=account_id,
        capability_code=MONITORING_RULES_CREATE_CAPABILITY,
    )

    if predicate not in (PREDICATE_CROSSES_ABOVE, PREDICATE_CROSSES_BELOW):
        return RuleRejected(reason=f"unknown predicate {predicate!r}")
    if debounce_seconds < 0:
        return RuleRejected(reason="debounce_seconds must be >= 0")

    if metric_id in SCALAR_VALUE_KEYS:
        if tenor_years is None:
            return RuleRejected(reason=f"metric {metric_id!r} requires tenor_years")
        subject_type = SUBJECT_TYPE_YIELD_CURVE_POINT
        subject_id = curve_point_subject_id(tenor_years)
    elif metric_id in CALCULATION_SCALAR_VALUE_KEYS:
        if instrument_isin is None:
            return RuleRejected(reason=f"metric {metric_id!r} requires instrument_isin")
        instrument = (
            await session.execute(
                select(Instrument)
                .join(InstrumentAlias, InstrumentAlias.instrument_id == Instrument.id)
                .where(
                    InstrumentAlias.alias_type == "ISIN",
                    InstrumentAlias.alias_value == instrument_isin,
                )
            )
        ).scalar_one_or_none()
        if instrument is None:
            return RuleRejected(reason=f"no instrument found for ISIN {instrument_isin!r}")
        subject_type = SUBJECT_TYPE_INSTRUMENT
        subject_id = instrument.id
    else:
        return RuleRejected(reason=f"unknown or unwatchable metric_id {metric_id!r}")

    rule = MonitoringRule(account_id=account_id)
    session.add(rule)
    await session.flush()
    rule_version = MonitoringRuleVersion(
        account_id=account_id,
        rule_id=rule.id,
        version=1,
        status=STATUS_ARMED,
        subject_type=subject_type,
        subject_id=subject_id,
        metric_id=metric_id,
        predicate=predicate,
        threshold_value=threshold_value,
        rearm_threshold=rearm_threshold,
        debounce_seconds=debounce_seconds,
        effective_from=dt.datetime.now(dt.UTC),
        created_by_principal_id=principal_id,
    )
    session.add(rule_version)
    await session.flush()
    rule.current_rule_version_id = rule_version.id
    await session.flush()
    return rule_version


async def list_my_rules(
    session: AsyncSession,
    *,
    principal_id: uuid.UUID,
    account_id: uuid.UUID,
    cursor: str | None,
    limit: int,
) -> Page[MonitoringRuleVersion]:
    """Only each rule's *current* version - a rule's edit history isn't a
    user-facing list yet, matching calculation_result's own "read the
    current answer, not every superseded one" default.
    """
    await _enforce_access(
        session,
        principal_id=principal_id,
        account_id=account_id,
        capability_code=MONITORING_RULES_READ_CAPABILITY,
    )
    stmt = select(MonitoringRuleVersion).join(
        MonitoringRule, MonitoringRule.current_rule_version_id == MonitoringRuleVersion.id
    )
    return await paginate_by_id(
        session,
        stmt,
        MonitoringRuleVersion.id,
        cursor=cursor,
        limit=limit,
        get_id=lambda row: row.id,
    )


async def get_my_rule(
    session: AsyncSession, *, rule_id: uuid.UUID, principal_id: uuid.UUID, account_id: uuid.UUID
) -> MonitoringRuleVersion | None:
    await _enforce_access(
        session,
        principal_id=principal_id,
        account_id=account_id,
        capability_code=MONITORING_RULES_READ_CAPABILITY,
    )
    rule = await session.get(MonitoringRule, rule_id)
    if rule is None or rule.current_rule_version_id is None:
        return None
    return await session.get(MonitoringRuleVersion, rule.current_rule_version_id)
