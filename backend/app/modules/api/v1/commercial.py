"""API v1 endpoints for commercial price book, account entitlements, and checkout."""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.api.v1.deps import IdentityDep, SessionDep
from app.modules.commercial.models import (
    AccountEntitlement,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    PlanDefinition,
)
from app.modules.commercial.service import (
    create_checkout_session,
    get_catalog,
    resolve_account_entitlement,
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


@router.post("/checkout", response_model=CheckoutSessionResponse)
async def start_checkout(
    identity: IdentityDep,
    req: CheckoutSessionRequest,
) -> CheckoutSessionResponse:
    """Initialize a verified checkout session for upgrades or seat additions."""
    return create_checkout_session(account_id=identity.account_id, req=req)
