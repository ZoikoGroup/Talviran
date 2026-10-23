"""Unit tests for the /api/v1/commercial service layer and endpoints."""

import uuid
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import create_app
from app.modules.commercial.models import BillingCadence, CheckoutSessionRequest, PlanTier
from app.modules.commercial.service import (
    create_checkout_session,
    get_catalog,
    resolve_account_entitlement,
)


@pytest.mark.asyncio
async def test_get_catalog():
    catalog = get_catalog()
    assert len(catalog) == 5
    tier_ids = [plan.id for plan in catalog]
    assert tier_ids == [
        PlanTier.EXPLORER,
        PlanTier.RESEARCH,
        PlanTier.PROFESSIONAL,
        PlanTier.TEAMS,
        PlanTier.ENTERPRISE,
    ]

    pro_plan = next(p for p in catalog if p.id == PlanTier.PROFESSIONAL)
    assert pro_plan.monthly_price_usd == 79
    assert pro_plan.annual_total_usd == 790
    assert pro_plan.is_popular is True
    assert pro_plan.limits.active_monitoring_rules == 125


@pytest.mark.asyncio
async def test_create_checkout_session():
    account_id = uuid.uuid4()
    req_annual = CheckoutSessionRequest(
        plan_tier=PlanTier.PROFESSIONAL,
        billing_cadence=BillingCadence.ANNUAL,
    )
    resp_annual = create_checkout_session(account_id, req_annual)
    assert resp_annual.total_amount_usd == 790
    assert resp_annual.session_id.startswith("cs_live_")
    assert "https://checkout.talvrin.com/pay/" in resp_annual.checkout_url

    req_teams_extra = CheckoutSessionRequest(
        plan_tier=PlanTier.TEAMS,
        billing_cadence=BillingCadence.MONTHLY,
        additional_seats=2,
    )
    resp_teams = create_checkout_session(account_id, req_teams_extra)
    # $249 base + 2 * $49 = $347
    assert resp_teams.total_amount_usd == 347


class _MockScalarResult:
    def __init__(self, val: int):
        self._val = val

    def scalar(self) -> int:
        return self._val


class _MockSession:
    async def execute(self, stmt: object, *args: object, **kwargs: object) -> _MockScalarResult:
        # Return 3 active rules on first execute, 5 research runs on second
        return _MockScalarResult(3)


@pytest.mark.asyncio
async def test_resolve_account_entitlement():
    session = cast(AsyncSession, _MockSession())
    account_id = uuid.uuid4()
    entitlement = await resolve_account_entitlement(session, account_id)
    assert entitlement.account_id == str(account_id)
    assert entitlement.plan_tier == PlanTier.PROFESSIONAL
    assert entitlement.is_active is True
    assert entitlement.usage.active_rules_count == 3
    assert entitlement.quotas.active_monitoring_rules == 125


@pytest.mark.asyncio
async def test_commercial_api_plans_endpoint():
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/commercial/plans")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5
        assert data[0]["id"] == "explorer"
        assert data[2]["id"] == "professional"
        assert data[2]["monthly_price_usd"] == 79
