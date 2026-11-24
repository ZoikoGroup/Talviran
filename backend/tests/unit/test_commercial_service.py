"""Unit tests for the /api/v1/commercial service layer and endpoints."""

import uuid
from typing import Any, cast

import pytest
import stripe
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.main import create_app
from app.modules.commercial.models import BillingCadence, CheckoutSessionRequest, PlanTier
from app.modules.commercial.service import (
    create_checkout_session,
    get_catalog,
    resolve_account_entitlement,
)


@pytest.mark.asyncio
async def test_get_catalog() -> None:
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
async def test_create_checkout_session() -> None:
    session = cast(AsyncSession, _MockSession())
    account_id = uuid.uuid4()
    req_annual = CheckoutSessionRequest(
        plan_tier=PlanTier.PROFESSIONAL,
        billing_cadence=BillingCadence.ANNUAL,
    )
    resp_annual = await create_checkout_session(session, account_id, req_annual)
    assert resp_annual.total_amount_usd == 790
    assert resp_annual.session_id.startswith("cs_")
    assert "checkout" in resp_annual.checkout_url

    req_teams_extra = CheckoutSessionRequest(
        plan_tier=PlanTier.TEAMS,
        billing_cadence=BillingCadence.MONTHLY,
        additional_seats=2,
    )
    resp_teams = await create_checkout_session(session, account_id, req_teams_extra)
    # $249 base + 2 * $49 = $347
    assert resp_teams.total_amount_usd == 347


class _MockRow:
    plan_tier = "professional"
    billing_cadence = "annual"
    seat_count = 1
    current_period_end = None
    name = "Test Account"
    stripe_customer_id = None
    stripe_subscription_id = None


class _MockScalarResult:
    def __init__(self, val: int):
        self._val = val

    def scalar(self) -> int:
        return self._val

    def first(self) -> _MockRow:
        return _MockRow()


class _MockSession:
    async def execute(self, stmt: object, *args: object, **kwargs: object) -> _MockScalarResult:
        # Return 3 active rules on first execute, 5 research runs on second
        return _MockScalarResult(3)


@pytest.mark.asyncio
async def test_resolve_account_entitlement() -> None:
    session = cast(AsyncSession, _MockSession())
    account_id = uuid.uuid4()
    entitlement = await resolve_account_entitlement(session, account_id)
    assert entitlement.account_id == str(account_id)
    assert entitlement.plan_tier == PlanTier.PROFESSIONAL
    assert entitlement.is_active is True
    assert entitlement.usage.active_rules_count == 3
    assert entitlement.quotas.active_monitoring_rules == 125


@pytest.mark.asyncio
async def test_commercial_api_plans_endpoint() -> None:
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


@pytest.mark.asyncio
async def test_enforce_quota_limit() -> None:
    from app.modules.commercial.models import PlanTier, QuotaLimits
    from app.modules.commercial.service import (
        PRICE_BOOK,
        QuotaExceededError,
        enforce_quota_limit,
    )

    session = cast(AsyncSession, _MockSession())
    account_id = uuid.uuid4()

    # active_rules_count is 3, while PROFESSIONAL quota is 125 -> should not raise
    await enforce_quota_limit(session, account_id, "active_monitoring_rules")

    # Unlimited watchlists on professional tier -> should not raise
    await enforce_quota_limit(session, account_id, "watchlists")

    # Temporarily set lower quota to verify QuotaExceededError is raised
    original_limits = PRICE_BOOK[PlanTier.PROFESSIONAL].limits
    try:
        PRICE_BOOK[PlanTier.PROFESSIONAL].limits = QuotaLimits(
            watchlists=1,
            active_monitoring_rules=2,  # Current is 3, so 2 should trigger exceed
            verified_research_runs_per_month=10,
            evidence_dossier_exports_per_month=2,
            filing_history_years=1,
            tick_level_realtime=True,
            team_workspaces=False,
            seat_count=1,
        )
        with pytest.raises(QuotaExceededError):
            await enforce_quota_limit(session, account_id, "active_monitoring_rules")
    finally:
        PRICE_BOOK[PlanTier.PROFESSIONAL].limits = original_limits


# --- G16: checkout decline/cancel + webhook signature verification -------
#
# None of this was covered before: test_create_checkout_session only proves
# session CREATION succeeds (the happy path where Stripe's hosted page
# returns a URL). What Stripe actually reports back about whether the buyer
# completed, abandoned, or had their card declined only ever arrives later,
# asynchronously, via the webhook - so that's the only place this can be
# tested, and it's exactly the gap G16 flags.


class _RecordingSession:
    """Mock session that records every raw-SQL execute() call instead of
    returning canned query results (contrast with _MockSession above, which
    is read-oriented) - lets a test assert *whether* and *how*
    handle_stripe_webhook_event touched the database, without a real
    Postgres. commit()/rollback() are counted, not simulated, since
    handle_stripe_webhook_event's own try/except around the update is what's
    under test, not transactional semantics."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, dict[str, Any]]] = []
        self.committed = 0
        self.rolled_back = 0

    async def execute(
        self, stmt: object, params: dict[str, Any] | None = None
    ) -> _MockScalarResult:
        self.executed.append((str(stmt), dict(params or {})))
        return _MockScalarResult(0)

    async def commit(self) -> None:
        self.committed += 1

    async def rollback(self) -> None:
        self.rolled_back += 1


def _checkout_session_object(
    *, status: str, payment_status: str, account_id: uuid.UUID
) -> dict[str, Any]:
    """A Stripe Checkout Session object shaped from what
    commercial/service.py's create_checkout_session() actually requests
    (mode="subscription", the same `metadata` dict literally set on
    stripe.checkout.Session.create at service.py line ~451) - not an
    independently-guessed shape. Stripe carries a session's metadata
    unchanged across its whole lifecycle, so `checkout.session.expired`
    carries the identical metadata block as `checkout.session.completed`,
    differing only in `status`/`payment_status`."""
    return {
        "id": f"cs_test_{uuid.uuid4().hex[:24]}",
        "object": "checkout.session",
        "status": status,
        "payment_status": payment_status,
        "subscription": f"sub_test_{uuid.uuid4().hex[:16]}" if status == "complete" else None,
        "metadata": {
            "account_id": str(account_id),
            "plan_tier": "professional",
            "billing_cadence": "annual",
            "seats": "1",
        },
    }


@pytest.mark.asyncio
async def test_handle_stripe_webhook_checkout_completed_updates_entitlement() -> None:
    """Contrast case for the decline/expiry tests below: a genuinely
    completed checkout must still update identity.account."""
    from app.modules.commercial.service import handle_stripe_webhook_event

    account_id = uuid.uuid4()
    session = _RecordingSession()
    event = {
        "id": "evt_test_completed",
        "type": "checkout.session.completed",
        "data": {
            "object": _checkout_session_object(
                status="complete", payment_status="paid", account_id=account_id
            )
        },
    }

    handled = await handle_stripe_webhook_event(cast(AsyncSession, session), event)

    assert handled is True
    assert session.committed == 1
    assert len(session.executed) == 1
    stmt_text, params = session.executed[0]
    assert "UPDATE identity.account" in stmt_text
    assert params["pt"] == "professional"
    assert params["bc"] == "annual"
    assert params["aid"] == account_id


@pytest.mark.asyncio
async def test_handle_stripe_webhook_checkout_session_expired_is_noop() -> None:
    """A buyer who abandons or never completes Stripe Checkout produces
    `checkout.session.expired`, not `checkout.session.completed`. This must
    never grant entitlement: handle_stripe_webhook_event only dispatches on
    ("checkout.session.completed", "customer.subscription.updated",
    "customer.subscription.deleted") - `.expired` falls through to its final
    bare `return False` with no database write attempted at all."""
    from app.modules.commercial.service import handle_stripe_webhook_event

    account_id = uuid.uuid4()
    session = _RecordingSession()
    event = {
        "id": "evt_test_expired",
        "type": "checkout.session.expired",
        "data": {
            "object": _checkout_session_object(
                status="expired", payment_status="unpaid", account_id=account_id
            )
        },
    }

    handled = await handle_stripe_webhook_event(cast(AsyncSession, session), event)

    assert handled is False
    assert session.executed == []
    assert session.committed == 0


@pytest.mark.asyncio
async def test_handle_stripe_webhook_payment_intent_failed_is_noop() -> None:
    """A declined card on the Checkout page fires `payment_intent.payment_failed`
    against the underlying PaymentIntent, not the Checkout Session -
    service.py's create_checkout_session never sets `payment_intent_data`,
    so Stripe's real PaymentIntent for one of our sessions carries no
    `account_id` metadata at all; this event type isn't even in
    handle_stripe_webhook_event's dispatch tuple, so it must be a guaranteed
    no-op regardless of metadata content."""
    from app.modules.commercial.service import handle_stripe_webhook_event

    session = _RecordingSession()
    event = {
        "id": "evt_test_payment_failed",
        "type": "payment_intent.payment_failed",
        "data": {
            "object": {
                "id": f"pi_test_{uuid.uuid4().hex[:16]}",
                "object": "payment_intent",
                "status": "requires_payment_method",
                "last_payment_error": {
                    "type": "card_error",
                    "code": "card_declined",
                    "message": "Your card was declined.",
                },
                "metadata": {},
            }
        },
    }

    handled = await handle_stripe_webhook_event(cast(AsyncSession, session), event)

    assert handled is False
    assert session.executed == []
    assert session.committed == 0


@pytest.mark.asyncio
async def test_handle_stripe_webhook_subscription_deleted_downgrades_to_explorer() -> None:
    """A subscription cancelled straight from Stripe's own Customer Portal
    (rather than Talvrin's self-serve /commercial/cancel) must still
    downgrade the account - this is the real "cancel" path
    handle_stripe_webhook_event already implements but had no test."""
    from app.modules.commercial.service import handle_stripe_webhook_event

    session = _RecordingSession()
    sub_id = f"sub_test_{uuid.uuid4().hex[:16]}"
    event = {
        "id": "evt_test_sub_deleted",
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": sub_id, "object": "subscription", "status": "canceled"}},
    }

    handled = await handle_stripe_webhook_event(cast(AsyncSession, session), event)

    assert handled is True
    assert session.committed == 1
    stmt_text, params = session.executed[0]
    assert "plan_tier = 'explorer'" in stmt_text
    assert params["sub"] == sub_id


@pytest.mark.asyncio
async def test_stripe_webhook_endpoint_rejects_invalid_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-closed: with STRIPE_WEBHOOK_SECRET configured (production-shaped
    config), a request whose Stripe-Signature header doesn't verify must be
    rejected before handle_stripe_webhook_event ever runs - anyone could
    otherwise POST a fabricated "payment succeeded" event and grant
    themselves a paid plan for free."""
    from app.core.config import get_settings

    base_settings = get_settings()
    webhook_secret = "whsec_test_fake_secret_for_unit_test"
    patched_settings = base_settings.model_copy(
        update={"stripe_webhook_secret": SecretStr(webhook_secret)}
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: patched_settings)

    recorder = _RecordingSession()

    async def _override_session() -> Any:
        yield recorder

    app = create_app()
    app.dependency_overrides[get_session] = _override_session
    try:
        payload = _checkout_session_object(
            status="complete", payment_status="paid", account_id=uuid.uuid4()
        )
        body = {
            "id": "evt_bad_sig",
            "type": "checkout.session.completed",
            "data": {"object": payload},
        }
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/commercial/webhook",
                content=__import__("json").dumps(body),
                headers={
                    "content-type": "application/json",
                    "stripe-signature": "t=1700000000,v1=0000deadbeef0000",
                },
            )
        assert resp.status_code == 400
        assert "signature" in resp.json()["error"]["message"].lower()
        # Fail-closed means no DB write happens before the signature check.
        assert recorder.executed == []
        assert recorder.committed == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_stripe_webhook_endpoint_accepts_valid_signature_and_updates_entitlement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A genuinely Stripe-signed event must both verify and actually update
    entitlement state - the positive case paired with the rejection test
    above. Uses stripe.WebhookSignature.generate_signature_header, the
    library's own documented test helper ("Useful for signing payloads in
    unit tests"), not a hand-rolled HMAC, so this stays correct if Stripe's
    signing scheme ever changes."""
    import json

    from app.core.config import get_settings

    base_settings = get_settings()
    webhook_secret = "whsec_test_fake_secret_for_unit_test"
    patched_settings = base_settings.model_copy(
        update={"stripe_webhook_secret": SecretStr(webhook_secret)}
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: patched_settings)

    recorder = _RecordingSession()

    async def _override_session() -> Any:
        yield recorder

    app = create_app()
    app.dependency_overrides[get_session] = _override_session
    try:
        account_id = uuid.uuid4()
        payload_obj = _checkout_session_object(
            status="complete", payment_status="paid", account_id=account_id
        )
        event_body = {
            "id": "evt_good_sig",
            "type": "checkout.session.completed",
            "data": {"object": payload_obj},
        }
        raw_body = json.dumps(event_body)
        signature_header = stripe.WebhookSignature.generate_signature_header(
            payload=raw_body, secret=webhook_secret
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/commercial/webhook",
                content=raw_body,
                headers={
                    "content-type": "application/json",
                    "stripe-signature": signature_header,
                },
            )

        assert resp.status_code == 200
        assert resp.json() == {"received": True}
        assert recorder.committed == 1
        stmt_text, params = recorder.executed[0]
        assert "UPDATE identity.account" in stmt_text
        assert params["aid"] == account_id
        assert params["pt"] == "professional"
    finally:
        app.dependency_overrides.clear()
