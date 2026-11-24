"""deliver_alert against real Postgres: an IN_APP delivery records an
attempt and marks the alert DELIVERED, and re-delivering an already-
delivered alert is a no-op rather than a second attempt row. The EMAIL
transport tests mock send_transactional_email rather than hitting a real
mailbox - the same real, non-mocked code path support.py's ticket tests
use, just with the one external I/O boundary swapped out.
"""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity import service as identity_service
from app.modules.monitoring import delivery as delivery_module
from app.modules.monitoring.delivery import Delivered, DeliverySkipped, deliver_alert
from app.modules.monitoring.models import (
    ALERT_TYPE_CROSSING,
    ALERT_TYPE_INITIAL_STATE,
    DELIVERY_ATTEMPT_DELIVERED,
    DELIVERY_ATTEMPT_FAILED,
    PREDICATE_CROSSES_ABOVE,
    STATUS_ALERT_CREATED,
    STATUS_ALERT_DELIVERED,
    STATUS_ALERT_SUPPRESSED,
    STATUS_ARMED,
    SUBJECT_TYPE_INSTRUMENT,
    TRANSPORT_EMAIL,
    TRANSPORT_IN_APP,
    Alert,
    AlertDeliveryAttempt,
    MonitoringRule,
    MonitoringRuleVersion,
    RuleEvaluation,
)


async def _act_as(
    session: AsyncSession, *, account_id: uuid.UUID, principal_id: uuid.UUID
) -> None:
    await identity_service.apply_rls_context(
        session, account_id=account_id, principal_id=principal_id
    )


async def _seed_alert(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    principal_id: uuid.UUID,
    status: str = STATUS_ALERT_CREATED,
    alert_type: str = ALERT_TYPE_INITIAL_STATE,
) -> uuid.UUID:
    rule = MonitoringRule(account_id=account_id)
    session.add(rule)
    await session.flush()
    rule_version = MonitoringRuleVersion(
        account_id=account_id, rule_id=rule.id, version=1, status=STATUS_ARMED,
        subject_type=SUBJECT_TYPE_INSTRUMENT, subject_id=uuid.uuid4(),
        metric_id="UK_GILT_NOMINAL_SPOT_CURVE", predicate=PREDICATE_CROSSES_ABOVE,
        threshold_value=Decimal("5.0"), effective_from=dt.datetime.now(dt.UTC),
        created_by_principal_id=principal_id,
    )
    session.add(rule_version)
    await session.flush()

    evaluation = RuleEvaluation(
        account_id=account_id, evaluation_key=uuid.uuid4().hex, rule_version_id=rule_version.id,
        trigger_type="FACT_PUBLISHED", trigger_id=None, knowledge_time=dt.datetime.now(dt.UTC),
        evaluator_version="crossing_v1", outcome=alert_type,
    )
    session.add(evaluation)
    await session.flush()

    alert = Alert(
        account_id=account_id, rule_id=rule.id, rule_version_id=rule_version.id,
        evaluation_id=evaluation.id, alert_type=alert_type, subject_id=uuid.uuid4(),
        metric_id="UK_GILT_NOMINAL_SPOT_CURVE", observed_value=Decimal("4.5"),
        threshold_value=Decimal("5.0"), knowledge_time=dt.datetime.now(dt.UTC),
        status=status,
    )
    session.add(alert)
    await session.flush()
    return alert.id


async def test_delivering_a_new_alert_records_an_attempt_and_marks_delivered(
    db_session: AsyncSession,
) -> None:
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    alert_id = await _seed_alert(db_session, account_id=account_id, principal_id=principal_id)
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    result = await deliver_alert(db_session, alert_id=alert_id)

    assert isinstance(result, Delivered)
    alert = await db_session.get(Alert, alert_id)
    assert alert is not None
    assert alert.status == STATUS_ALERT_DELIVERED

    attempts = (
        await db_session.execute(
            select(AlertDeliveryAttempt).where(AlertDeliveryAttempt.alert_id == alert_id)
        )
    ).scalars().all()
    assert len(attempts) == 1
    assert attempts[0].transport == TRANSPORT_IN_APP
    assert attempts[0].status == DELIVERY_ATTEMPT_DELIVERED


async def test_redelivering_an_already_delivered_alert_does_not_add_a_second_attempt(
    db_session: AsyncSession,
) -> None:
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    alert_id = await _seed_alert(db_session, account_id=account_id, principal_id=principal_id)
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    first = await deliver_alert(db_session, alert_id=alert_id)
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    second = await deliver_alert(db_session, alert_id=alert_id)

    assert isinstance(first, Delivered)
    assert isinstance(second, Delivered)
    attempts = (
        await db_session.execute(
            select(AlertDeliveryAttempt).where(AlertDeliveryAttempt.alert_id == alert_id)
        )
    ).scalars().all()
    assert len(attempts) == 1, "re-delivering an already-DELIVERED alert must not attempt again"


async def test_nonexistent_alert_is_skipped_not_a_crash(db_session: AsyncSession) -> None:
    result = await deliver_alert(db_session, alert_id=uuid.uuid4())
    assert isinstance(result, DeliverySkipped)


async def test_a_suppressed_alert_is_never_delivered(db_session: AsyncSession) -> None:
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    alert_id = await _seed_alert(
        db_session, account_id=account_id, principal_id=principal_id,
        status=STATUS_ALERT_SUPPRESSED,
    )
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    result = await deliver_alert(db_session, alert_id=alert_id)

    assert isinstance(result, DeliverySkipped)
    assert "suppressed" in result.reason
    alert = await db_session.get(Alert, alert_id)
    assert alert is not None
    assert alert.status == STATUS_ALERT_SUPPRESSED, "must not silently move a suppressed alert on"


async def test_delivering_with_a_recipient_email_also_attempts_email_transport(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_to: list[str] = []

    def _fake_send(to_email: str, subject: str, html_content: str) -> bool:
        sent_to.append(to_email)
        return True

    monkeypatch.setattr(delivery_module, "send_transactional_email", _fake_send)

    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    alert_id = await _seed_alert(
        db_session, account_id=account_id, principal_id=principal_id,
        alert_type=ALERT_TYPE_CROSSING,
    )
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    result = await deliver_alert(
        db_session, alert_id=alert_id, recipient_email="analyst@example.com"
    )

    assert isinstance(result, Delivered)
    assert sent_to == ["analyst@example.com"]
    attempts = (
        await db_session.execute(
            select(AlertDeliveryAttempt).where(AlertDeliveryAttempt.alert_id == alert_id)
        )
    ).scalars().all()
    transports = {a.transport: a.status for a in attempts}
    assert transports[TRANSPORT_IN_APP] == DELIVERY_ATTEMPT_DELIVERED
    assert transports[TRANSPORT_EMAIL] == DELIVERY_ATTEMPT_DELIVERED


async def test_email_transport_failure_is_recorded_but_in_app_still_succeeds(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delivery_module, "send_transactional_email", lambda *a, **k: False)

    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    alert_id = await _seed_alert(
        db_session, account_id=account_id, principal_id=principal_id,
        alert_type=ALERT_TYPE_CROSSING,
    )
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    result = await deliver_alert(
        db_session, alert_id=alert_id, recipient_email="analyst@example.com"
    )

    assert isinstance(result, Delivered), "an email outage must never block in-app delivery"
    alert = await db_session.get(Alert, alert_id)
    assert alert is not None
    assert alert.status == STATUS_ALERT_DELIVERED
    attempts = (
        await db_session.execute(
            select(AlertDeliveryAttempt).where(AlertDeliveryAttempt.alert_id == alert_id)
        )
    ).scalars().all()
    transports = {a.transport: a.status for a in attempts}
    assert transports[TRANSPORT_EMAIL] == DELIVERY_ATTEMPT_FAILED


async def test_no_recipient_email_means_no_email_attempt(db_session: AsyncSession) -> None:
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    alert_id = await _seed_alert(db_session, account_id=account_id, principal_id=principal_id)
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    await deliver_alert(db_session, alert_id=alert_id)

    attempts = (
        await db_session.execute(
            select(AlertDeliveryAttempt).where(AlertDeliveryAttempt.alert_id == alert_id)
        )
    ).scalars().all()
    assert [a.transport for a in attempts] == [TRANSPORT_IN_APP]
