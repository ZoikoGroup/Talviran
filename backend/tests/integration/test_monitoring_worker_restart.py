"""Restart/resume semantics for scripts.run_monitoring_worker's per-account
sweep loop (MON-001 / UAT gap-analysis G11's "restart" closure evidence):
the evaluator process crashing mid-sweep, then being restarted, must never
duplicate an alert whose evaluation had already committed, and must never
silently skip a rule it hadn't reached yet before the crash.

_sweep_account (unlike sweep_once, which owns its own app-engine session
factory tied to the real process) takes a caller-supplied session
specifically so it is directly testable against the real test database,
exactly like every other monitoring integration test exercises its real
functions rather than mocking them.

The crash itself is simulated by making the first deliver_alert call in a
sweep raise, then rolling the session back before "restarting" (a fresh
sweep_account call). This is an honest proxy for a hard process crash, not
a shortcut: a real crash drops the connection and Postgres server-side
aborts whatever transaction was still open, discarding every flushed-but-
uncommitted row exactly as session.rollback() does here - the two
_sweep_account's own `await session.commit()` calls per rule (first right
after evaluate_rule_version, second after coverage/alert/delivery) are the
only durability boundaries either way, so what a manual rollback discards
is exactly what a dropped connection would have discarded too.
"""

import datetime as dt
import uuid
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

import scripts.run_monitoring_worker as worker_module
from app.modules.identity import service as identity_service
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    SUBJECT_TYPE_YIELD_CURVE_POINT,
    curve_point_subject_id,
)
from app.modules.monitoring.delivery import deliver_alert as real_deliver_alert
from app.modules.monitoring.models import (
    PREDICATE_CROSSES_ABOVE,
    STATUS_ALERT_DELIVERED,
    STATUS_ARMED,
    SUBJECT_TYPE_INSTRUMENT,
    Alert,
    MonitoringRule,
    MonitoringRuleVersion,
    RuleEvaluation,
)
from app.modules.policy.models import ActivationRecord, CapabilityStatus
from app.modules.rights.models import RightsGrant, RightsProfile

_TENOR_A = Decimal("10")
_TENOR_B = Decimal("5")
_SUBJECT_A = curve_point_subject_id(_TENOR_A)
_SUBJECT_B = curve_point_subject_id(_TENOR_B)

_PASSWORD = "correct-horse-9"


def _email() -> str:
    return f"mon-restart-{uuid.uuid4().hex[:12]}@example.com"


async def _act_as(
    session: AsyncSession, *, account_id: uuid.UUID, principal_id: uuid.UUID
) -> None:
    await identity_service.apply_rls_context(
        session, account_id=account_id, principal_id=principal_id
    )


async def _register_tenant(
    session: AsyncSession, http: httpx.AsyncClient
) -> tuple[uuid.UUID, uuid.UUID]:
    login = await identity_service.register(
        session, email=_email(), password=_PASSWORD, http=http
    )
    await session.commit()
    await _act_as(
        session, account_id=login.identity.account_id, principal_id=login.identity.principal_id
    )
    return login.identity.account_id, login.identity.principal_id


async def _seed_governance(session: AsyncSession) -> None:
    session.add(
        CapabilityStatus(
            capability_code="monitoring.alerts.create", jurisdiction_code=None, status="AVAILABLE"
        )
    )
    session.add(
        ActivationRecord(
            jurisdiction_code="GB", operating_entity="Test Entity", status="ACTIVE",
            effective_from=dt.datetime.now(dt.UTC) - dt.timedelta(days=1), effective_to=None,
        )
    )
    await session.flush()


async def _seed_boe_rights(session: AsyncSession) -> None:
    profile = RightsProfile(code="boe.yield-curve", status="ACTIVE")
    session.add(profile)
    await session.flush()
    session.add(
        RightsGrant(rights_profile_id=profile.id, action="display", permission_state="ALLOW")
    )
    await session.flush()


async def _seed_rule_version(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    principal_id: uuid.UUID,
    subject_id: uuid.UUID,
) -> uuid.UUID:
    rule = MonitoringRule(account_id=account_id)
    session.add(rule)
    await session.flush()
    rule_version = MonitoringRuleVersion(
        account_id=account_id,
        rule_id=rule.id,
        version=1,
        status=STATUS_ARMED,
        subject_type=SUBJECT_TYPE_INSTRUMENT,
        subject_id=subject_id,
        metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
        predicate=PREDICATE_CROSSES_ABOVE,
        threshold_value=Decimal("5.0"),
        effective_from=dt.datetime.now(dt.UTC),
        created_by_principal_id=principal_id,
    )
    session.add(rule_version)
    await session.flush()
    rule.current_rule_version_id = rule_version.id
    return rule_version.id


async def _seed_curve_point(
    session: AsyncSession, *, subject_id: uuid.UUID, spot_rate_pct: str, valid_on: dt.date
) -> None:
    session.add(
        AcceptedFact(
            subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT,
            subject_id=subject_id,
            metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
            valid_range=Range(
                lower=dt.datetime.combine(valid_on, dt.time.min, tzinfo=dt.UTC),
                upper=dt.datetime.combine(
                    valid_on + dt.timedelta(days=1), dt.time.min, tzinfo=dt.UTC
                ),
                bounds="[)",
            ),
            knowledge_range=Range(
                lower=dt.datetime.combine(valid_on, dt.time(8), tzinfo=dt.UTC),
                upper=None, bounds="[)",
            ),
            value={"tenor_years": "n/a", "spot_rate_pct": spot_rate_pct},
            status="ACTIVE",
        )
    )
    await session.flush()


async def test_crash_mid_sweep_then_resume_is_exactly_once_per_rule(
    db_session: AsyncSession, supabase_http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_id, principal_id = await _register_tenant(db_session, supabase_http)
    await _seed_governance(db_session)
    await _seed_boe_rights(db_session)

    rule_a = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id, subject_id=_SUBJECT_A
    )
    rule_b = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id, subject_id=_SUBJECT_B
    )

    # Rule A already has a value that is a genuine MATCH once evaluated;
    # rule B has its first-ever value (INITIAL_STATE once evaluated).
    # Neither has been evaluated yet - both are "pending work" the first
    # sweep is about to discover.
    await _seed_curve_point(
        db_session, subject_id=_SUBJECT_A, spot_rate_pct="5.5", valid_on=dt.date(2026, 9, 10)
    )
    await _seed_curve_point(
        db_session, subject_id=_SUBJECT_B, spot_rate_pct="4.5", valid_on=dt.date(2026, 9, 10)
    )
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    # Simulate the evaluator process dying mid-sweep: the FIRST call to
    # deliver_alert (whichever rule the sweep reaches first - the ARMED
    # rule_versions query makes no ordering guarantee) raises instead of
    # completing, as if the process had been killed right there.
    call_count = {"n": 0}

    async def _flaky_deliver_alert(
        session: AsyncSession, *, alert_id: uuid.UUID, recipient_email: str | None = None
    ) -> object:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated evaluator crash mid-sweep")
        return await real_deliver_alert(session, alert_id=alert_id, recipient_email=recipient_email)

    monkeypatch.setattr(worker_module, "deliver_alert", _flaky_deliver_alert)

    with pytest.raises(RuntimeError, match="simulated evaluator crash"):
        await worker_module._sweep_account(
            db_session, account_id=account_id, principal_id=principal_id
        )

    # The crash takes down whatever that rule's own in-flight transaction
    # had flushed (its coverage upsert, its new Alert row) since none of it
    # had reached _sweep_account's own second `await session.commit()` yet
    # - a dropped connection would have discarded exactly the same rows.
    # The OTHER rule was never even reached: the raise propagated out of
    # the for-loop before its iteration began.
    await db_session.rollback()

    # "Restart": a fresh RLS context (a real restart gets a brand-new
    # connection too). _flaky_deliver_alert stays installed rather than
    # being swapped back to real_deliver_alert here - it already delegates
    # to the real function for every call past the first, and re-patching
    # to the raw function would silently disconnect call_count from the
    # resumed sweep's deliveries, making the "exactly 3 calls total"
    # assertion below fail even when delivery itself is correct.
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    processed = await worker_module._sweep_account(
        db_session, account_id=account_id, principal_id=principal_id
    )
    await db_session.commit()
    # That commit ends the transaction holding app.account_id/app.principal_id
    # (SET LOCAL is transaction-scoped - the exact lesson _sweep_account's own
    # docstring/comments spell out for its internal commits). Without
    # reapplying it, the SELECTs below run with no RLS context at all and
    # monitoring.rule_evaluation/monitoring.alert's fail-closed RLS policies
    # hide every row - reading back as "nothing was created", which looks
    # identical to a real missed-alert bug but isn't one.
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    assert processed == 2, "resume must finish the interrupted rule AND reach the untouched one"

    for rule_version_id in (rule_a, rule_b):
        alerts = (
            await db_session.execute(
                select(Alert).where(Alert.rule_version_id == rule_version_id)
            )
        ).scalars().all()
        assert len(alerts) == 1, (
            f"rule_version {rule_version_id} must end up with exactly one alert after "
            "crash+resume, never zero (missed) and never two (duplicated)"
        )
        assert alerts[0].status == STATUS_ALERT_DELIVERED

        evaluations = (
            await db_session.execute(
                select(RuleEvaluation).where(RuleEvaluation.rule_version_id == rule_version_id)
            )
        ).scalars().all()
        assert len(evaluations) == 1, (
            "evaluate_rule_version's own evaluation_key idempotency must prevent a second "
            "evaluation row for the same (rule_version, trigger, knowledge_time) on resume"
        )

    # 1 crashed attempt (the rule the first sweep reached) + 2 real
    # deliveries on resume (that same rule's re-created alert, plus the
    # other rule the first sweep never got to).
    assert call_count["n"] == 3, "exactly one crashed attempt, then exactly two real deliveries"
