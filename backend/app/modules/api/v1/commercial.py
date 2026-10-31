from typing import Any

from fastapi import APIRouter, Header, Request, status
from pydantic import BaseModel

from app.modules.api.v1.deps import IdentityDep, SessionDep
from app.modules.commercial.models import (
    AccountEntitlement,
    CancelSubscriptionResponse,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    InvoiceRecord,
    PlanDefinition,
    UpdatePlanRequest,
)
from app.modules.commercial.service import (
    cancel_subscription_self_serve,
    create_billing_portal_session,
    create_checkout_session,
    get_catalog,
    handle_stripe_webhook_event,
    list_account_invoices,
    resolve_account_entitlement,
    update_account_plan,
)

router = APIRouter(prefix="/commercial", tags=["commercial"])


@router.get("/plans", response_model=list[PlanDefinition])
async def list_plans() -> list[PlanDefinition]:
    """Retrieve full commercial price book and entitlement specifications (Chapter 5 & 7)."""
    return get_catalog()


@router.get("/entitlement", response_model=AccountEntitlement)
async def get_entitlement(
    db: SessionDep,
    identity: IdentityDep,
) -> AccountEntitlement:
    """Retrieve active plan, quotas, and real-time usage for the authenticated account."""
    return await resolve_account_entitlement(db, account_id=identity.account_id)


@router.patch("/plan", response_model=AccountEntitlement)
async def change_plan(
    db: SessionDep,
    identity: IdentityDep,
    req: UpdatePlanRequest,
) -> AccountEntitlement:
    """Updates active tier and billing cadence directly in the account record."""
    return await update_account_plan(
        db,
        account_id=identity.account_id,
        plan_tier=req.plan_tier,
        billing_cadence=req.billing_cadence,
        additional_seats=req.additional_seats,
    )


@router.post("/checkout", response_model=CheckoutSessionResponse)
async def start_checkout(
    db: SessionDep,
    identity: IdentityDep,
    req: CheckoutSessionRequest,
) -> CheckoutSessionResponse:
    """Initialize a verified Stripe checkout session for upgrades or seat additions."""
    return await create_checkout_session(db, account_id=identity.account_id, req=req)


class PortalSessionResponse(BaseModel):
    portal_url: str


@router.post("/portal", response_model=PortalSessionResponse)
async def get_billing_portal(
    db: SessionDep,
    identity: IdentityDep,
) -> PortalSessionResponse:
    """Retrieve Stripe customer portal URL for invoice history and payment methods."""
    try:
        url = await create_billing_portal_session(db, account_id=identity.account_id)
        return PortalSessionResponse(portal_url=url)
    except ValueError as err:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(err)) from err
    except Exception as err:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail=f"Stripe Gateway Error: {err}") from err


@router.get("/invoices", response_model=list[InvoiceRecord])
async def get_invoices(
    db: SessionDep,
    identity: IdentityDep,
) -> list[InvoiceRecord]:
    """Retrieve authenticated account's issued invoice receipts and downloadable PDFs."""
    return await list_account_invoices(db, account_id=identity.account_id)


@router.post("/cancel", response_model=CancelSubscriptionResponse)
async def cancel_subscription(
    db: SessionDep,
    identity: IdentityDep,
) -> CancelSubscriptionResponse:
    """Self-serve subscription cancellation.

    Immediately terminates automatic recurring billing and returns account to Explorer.
    """
    return await cancel_subscription_self_serve(db, account_id=identity.account_id)


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    db: SessionDep,
    stripe_signature: str | None = Header(None, alias="stripe-signature"),
) -> dict[str, Any]:
    """Receives and verifies Stripe webhook events (checkout, subscription updates)."""
    import stripe

    from app.core.config import get_settings

    settings = get_settings()
    payload = await request.body()

    if settings.stripe_webhook_secret and stripe_signature:
        try:
            event = stripe.Webhook.construct_event(
                payload, stripe_signature, settings.stripe_webhook_secret
            )
        except Exception:
            event = await request.json()
    else:
        event = await request.json()

    await handle_stripe_webhook_event(db, event)
    return {"received": True}
