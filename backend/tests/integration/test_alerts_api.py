"""GET /api/v1/alerts and /api/v1/alerts/{id} over HTTP: a real signed-in
user only ever sees their own account's alerts (RLS), and only when
signed in and PDP-permitted at all - mirrors test_research_endpoint.py's
make_client/_signed_in pattern (own engine, same per-test-event-loop
reasoning), minus the redis/crypto overrides research needs that alerts
don't.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db import get_session
from app.main import app
from app.modules.identity import service as identity_service
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    SUBJECT_TYPE_YIELD_CURVE_POINT,
    curve_point_subject_id,
)
from app.modules.monitoring.alerts import AlertCreated, create_alert_for_evaluation
from app.modules.monitoring.models import (
    PREDICATE_CROSSES_ABOVE,
    STATUS_ARMED,
    SUBJECT_TYPE_INSTRUMENT,
    MonitoringRule,
    MonitoringRuleVersion,
)
from app.modules.monitoring.rule_engine import RuleEvaluationRecorded, evaluate_rule_version
from app.modules.policy.models import ActivationRecord, CapabilityStatus
from app.modules.rights.models import RightsGrant, RightsProfile

PASSWORD = "correct-horse-9"
_TENOR = Decimal("10")
_SUBJECT_ID = curve_point_subject_id(_TENOR)


def _email() -> str:
    return f"alerts-{uuid.uuid4().hex[:12]}@example.com"


ClientFactory = Callable[[], AbstractAsyncContextManager[AsyncClient]]


@pytest_asyncio.fixture
async def make_client() -> AsyncIterator[ClientFactory]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session_override

    @asynccontextmanager
    async def _client() -> AsyncIterator[AsyncClient]:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    yield _client

    app.dependency_overrides.clear()
    await engine.dispose()


async def _signed_in(client: AsyncClient) -> str:
    email = _email()
    r = await client.post("/api/v1/auth/signup", json={"email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return email


async def _seed_pdp_prerequisites(db_session: AsyncSession) -> None:
    for code in ("monitoring.alerts.create", "monitoring.alerts.read"):
        db_session.add(
            CapabilityStatus(capability_code=code, jurisdiction_code=None, status="AVAILABLE")
        )
    db_session.add(
        ActivationRecord(
            jurisdiction_code="GB", operating_entity="Test Entity", status="ACTIVE",
            effective_from=dt.datetime.now(dt.UTC) - dt.timedelta(days=1), effective_to=None,
        )
    )
    profile = RightsProfile(code="boe.yield-curve", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    db_session.add(
        RightsGrant(rights_profile_id=profile.id, action="display", permission_state="ALLOW")
    )
    await db_session.commit()


async def _seed_alert_for(
    db_session: AsyncSession, *, account_id: uuid.UUID, principal_id: uuid.UUID
) -> uuid.UUID:
    """Creates a real alert end to end (rule -> fact -> evaluation ->
    alert) for the given already-registered account, reusing the real
    engine/alerts pipeline rather than inserting an Alert row by hand.
    """
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )
    rule = MonitoringRule(account_id=account_id)
    db_session.add(rule)
    await db_session.flush()
    rule_version = MonitoringRuleVersion(
        account_id=account_id, rule_id=rule.id, version=1, status=STATUS_ARMED,
        subject_type=SUBJECT_TYPE_INSTRUMENT, subject_id=_SUBJECT_ID,
        metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE, predicate=PREDICATE_CROSSES_ABOVE,
        threshold_value=Decimal("5.0"), effective_from=dt.datetime.now(dt.UTC),
        created_by_principal_id=principal_id,
    )
    db_session.add(rule_version)
    await db_session.flush()
    valid_on = dt.date(2026, 9, 10)
    db_session.add(
        AcceptedFact(
            subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT, subject_id=_SUBJECT_ID,
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
            value={"tenor_years": str(_TENOR), "spot_rate_pct": "4.5"},
            status="ACTIVE",
        )
    )
    await db_session.commit()
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    evaluation = await evaluate_rule_version(
        db_session, rule_version_id=rule_version.id, trigger_type="FACT_PUBLISHED",
        trigger_id=None,
    )
    assert isinstance(evaluation, RuleEvaluationRecorded)
    result = await create_alert_for_evaluation(
        db_session, rule_evaluation_id=evaluation.rule_evaluation_id
    )
    await db_session.commit()
    assert isinstance(result, AlertCreated)
    return result.alert_id


async def test_alerts_requires_a_session(make_client: ClientFactory) -> None:
    async with make_client() as client:
        response = await client.get("/api/v1/alerts")
    assert response.status_code == 401


async def test_denies_before_governance_is_seeded(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    async with make_client() as client:
        await _signed_in(client)
        response = await client.get("/api/v1/alerts")
    assert response.status_code == 403


async def test_signed_in_user_sees_only_their_own_alert(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)

    async with make_client() as client:
        await _signed_in(client)
        me = await client.get("/api/v1/auth/me")
        assert me.status_code == 200, me.text
        account_id = uuid.UUID(me.json()["account_id"])
        principal_id = uuid.UUID(me.json()["principal_id"])

        alert_id = await _seed_alert_for(
            db_session, account_id=account_id, principal_id=principal_id
        )

        listed = await client.get("/api/v1/alerts")
        assert listed.status_code == 200, listed.text
        body = listed.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["id"] == str(alert_id)

        detail = await client.get(f"/api/v1/alerts/{alert_id}")
        assert detail.status_code == 200, detail.text
        assert Decimal(detail.json()["observed_value"]) == Decimal("4.5")


async def test_another_signed_in_user_cannot_see_someone_elses_alert(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)

    async with make_client() as client_a:
        await _signed_in(client_a)
        me_a = await client_a.get("/api/v1/auth/me")
        account_a = uuid.UUID(me_a.json()["account_id"])
        principal_a = uuid.UUID(me_a.json()["principal_id"])
        alert_id = await _seed_alert_for(
            db_session, account_id=account_a, principal_id=principal_a
        )

    async with make_client() as client_b:
        await _signed_in(client_b)
        listed = await client_b.get("/api/v1/alerts")
        assert listed.json()["items"] == []

        detail = await client_b.get(f"/api/v1/alerts/{alert_id}")
        assert detail.status_code == 404
