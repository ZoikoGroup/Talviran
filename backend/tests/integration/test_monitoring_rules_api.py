"""POST/GET /api/v1/monitoring-rules over HTTP: the one gap left in P3's
alerts surface - rules could previously only be created by a script or a
test fixture, never through the API a real user would use. Mirrors
test_alerts_api.py's make_client/_signed_in pattern (own engine, same
per-test-event-loop reasoning).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db import get_session
from app.main import app
from app.modules.api.v1 import auth as auth_module
from app.modules.calculation.pipeline.curve_pricing import METRIC_MODEL_IMPLIED_CLEAN_PRICE
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    curve_point_subject_id,
)
from app.modules.monitoring.rule_engine import evaluate_rule_version
from app.modules.policy.models import ActivationRecord, CapabilityStatus
from app.modules.reference.models import Instrument, InstrumentAlias, Issuer

PASSWORD = "correct-horse-9"


def _email() -> str:
    return f"rules-{uuid.uuid4().hex[:12]}@example.com"


ClientFactory = Callable[[], AbstractAsyncContextManager[AsyncClient]]


@pytest_asyncio.fixture
async def make_client(supabase_http: AsyncClient) -> AsyncIterator[ClientFactory]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[auth_module._http] = lambda: supabase_http

    @asynccontextmanager
    async def _client() -> AsyncIterator[AsyncClient]:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    yield _client

    app.dependency_overrides.clear()
    await engine.dispose()


async def _signed_in(client: AsyncClient) -> None:
    email = _email()
    r = await client.post("/api/v1/auth/signup", json={"email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text


async def _seed_pdp_prerequisites(db_session: AsyncSession) -> None:
    for code in ("monitoring.rules.create", "monitoring.rules.read"):
        db_session.add(
            CapabilityStatus(capability_code=code, jurisdiction_code=None, status="AVAILABLE")
        )
    db_session.add(
        ActivationRecord(
            jurisdiction_code="GB", operating_entity="Test Entity", status="ACTIVE",
            effective_from=dt.datetime.now(dt.UTC) - dt.timedelta(days=1), effective_to=None,
        )
    )
    await db_session.commit()


async def _seed_gilt(db_session: AsyncSession, *, isin: str) -> Instrument:
    issuer = Issuer(name="HM Treasury", country_code="GB", status="ACTIVE")
    db_session.add(issuer)
    await db_session.flush()
    instrument = Instrument(
        issuer_id=issuer.id, instrument_type="FI_SOVEREIGN",
        name="Test Gilt", currency_code="GBP", status="ACTIVE",
    )
    db_session.add(instrument)
    await db_session.flush()
    db_session.add(
        InstrumentAlias(instrument_id=instrument.id, alias_type="ISIN", alias_value=isin)
    )
    await db_session.commit()
    return instrument


async def test_create_rule_requires_a_session(make_client: ClientFactory) -> None:
    async with make_client() as client:
        response = await client.post(
            "/api/v1/monitoring-rules",
            json={
                "metric_id": METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
                "predicate": "CROSSES_ABOVE",
                "threshold_value": "5.0",
                "tenor_years": "10",
            },
        )
    assert response.status_code == 401


async def test_denies_before_governance_is_seeded(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    async with make_client() as client:
        await _signed_in(client)
        response = await client.post(
            "/api/v1/monitoring-rules",
            json={
                "metric_id": METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
                "predicate": "CROSSES_ABOVE",
                "threshold_value": "5.0",
                "tenor_years": "10",
            },
        )
    assert response.status_code == 403


async def test_create_curve_rule_by_tenor_is_immediately_evaluable(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)

    async with make_client() as client:
        await _signed_in(client)
        me = await client.get("/api/v1/auth/me")
        account_id = uuid.UUID(me.json()["account_id"])
        principal_id = uuid.UUID(me.json()["principal_id"])

        response = await client.post(
            "/api/v1/monitoring-rules",
            json={
                "metric_id": METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
                "predicate": "CROSSES_ABOVE",
                "threshold_value": "5.0",
                "tenor_years": "10",
                "rearm_threshold": "4.8",
                "debounce_seconds": 60,
            },
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "ARMED"
    assert body["subject_type"] == "YIELD_CURVE_POINT"
    assert body["subject_id"] == str(curve_point_subject_id(Decimal("10")))
    assert Decimal(body["threshold_value"]) == Decimal("5.0")
    assert Decimal(body["rearm_threshold"]) == Decimal("4.8")
    assert body["debounce_seconds"] == 60
    rule_id = uuid.UUID(body["id"])

    # Proves this isn't just a row - it's a rule the engine can actually
    # evaluate (skipped, not crashed, since no fact has been published for
    # this tenor yet in this test - MonitoringRuleVersion.id isn't the same
    # as MonitoringRule.id, so this also confirms rule.current_rule_version_id
    # was wired up correctly on creation).
    from app.modules.identity import service as identity_service
    from app.modules.monitoring.models import MonitoringRule
    from app.modules.monitoring.rule_engine import RuleEvaluationSkipped

    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )
    rule = await db_session.get(MonitoringRule, rule_id)
    assert rule is not None
    assert rule.current_rule_version_id is not None
    evaluation = await evaluate_rule_version(
        db_session,
        rule_version_id=rule.current_rule_version_id,
        trigger_type="SCHEDULED_SWEEP",
        trigger_id=None,
    )
    assert isinstance(evaluation, RuleEvaluationSkipped)


async def test_create_instrument_rule_by_isin_succeeds(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)
    isin = f"GB{uuid.uuid4().hex[:10].upper()}"
    instrument = await _seed_gilt(db_session, isin=isin)

    async with make_client() as client:
        await _signed_in(client)
        response = await client.post(
            "/api/v1/monitoring-rules",
            json={
                "metric_id": METRIC_MODEL_IMPLIED_CLEAN_PRICE,
                "predicate": "CROSSES_ABOVE",
                "threshold_value": "95.0",
                "instrument_isin": isin,
            },
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["subject_type"] == "INSTRUMENT"
    assert body["subject_id"] == str(instrument.id)


async def test_create_rule_with_unknown_metric_is_rejected(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)

    async with make_client() as client:
        await _signed_in(client)
        response = await client.post(
            "/api/v1/monitoring-rules",
            json={
                "metric_id": "NOT_A_REAL_METRIC",
                "predicate": "CROSSES_ABOVE",
                "threshold_value": "5.0",
            },
        )
    assert response.status_code == 422, response.text


async def test_create_instrument_rule_with_unknown_isin_is_rejected(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)

    async with make_client() as client:
        await _signed_in(client)
        response = await client.post(
            "/api/v1/monitoring-rules",
            json={
                "metric_id": METRIC_MODEL_IMPLIED_CLEAN_PRICE,
                "predicate": "CROSSES_ABOVE",
                "threshold_value": "95.0",
                "instrument_isin": "GB0000000000",
            },
        )
    assert response.status_code == 422, response.text


async def test_another_signed_in_user_cannot_see_someone_elses_rule(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)

    async with make_client() as client_a:
        await _signed_in(client_a)
        created = await client_a.post(
            "/api/v1/monitoring-rules",
            json={
                "metric_id": METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
                "predicate": "CROSSES_ABOVE",
                "threshold_value": "5.0",
                "tenor_years": "10",
            },
        )
        assert created.status_code == 201, created.text
        rule_id = created.json()["id"]

    async with make_client() as client_b:
        await _signed_in(client_b)
        listed = await client_b.get("/api/v1/monitoring-rules")
        assert listed.json()["items"] == []

        detail = await client_b.get(f"/api/v1/monitoring-rules/{rule_id}")
        assert detail.status_code == 404
