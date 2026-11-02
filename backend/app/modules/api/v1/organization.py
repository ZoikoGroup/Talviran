"""Organization, Team Members & Invitation Management Endpoints."""

import datetime as dt
import hashlib
import secrets
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, text

from app.core.uuid7 import new_uuid7
from app.modules.api.v1.deps import IdentityDep, SessionDep
from app.modules.identity.models import Account, OrganizationInvitation, Principal

router = APIRouter(prefix="/organization", tags=["organization"])

RoleType = Literal["admin", "analyst", "viewer"]


class MemberResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    status: str
    created_at: dt.datetime
    is_current_user: bool = False


class InvitationResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    status: str
    created_at: dt.datetime
    expires_at: dt.datetime
    invite_url: str | None = None


class OrganizationOverviewResponse(BaseModel):
    account_id: uuid.UUID
    account_name: str
    plan_tier: str
    seat_count: int
    used_seats: int
    available_seats: int
    can_invite: bool
    members: list[MemberResponse]
    invitations: list[InvitationResponse]


class CreateInvitationRequest(BaseModel):
    email: EmailStr
    role: RoleType = Field(default="analyst")


class UpdateMemberRoleRequest(BaseModel):
    role: RoleType


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@router.get("", response_model=OrganizationOverviewResponse)
async def get_organization(
    db: SessionDep,
    identity: IdentityDep,
) -> OrganizationOverviewResponse:
    """Retrieve organization profile, all active members, invitations, and seat quotas."""
    # 1. Fetch Account
    account_res = await db.execute(
        select(Account).where(Account.id == identity.account_id)
    )
    account = account_res.scalar_one_or_none()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found."
        )

    # 2. Fetch Members (RLS-scoped by account_id)
    members_res = await db.execute(
        select(Principal)
        .where(
            Principal.account_id == identity.account_id,
            Principal.status == "ACTIVE",
        )
        .order_by(Principal.created_at.asc())
    )
    principals = members_res.scalars().all()

    # 3. Fetch Pending Invitations
    invites_res = await db.execute(
        select(OrganizationInvitation)
        .where(
            OrganizationInvitation.account_id == identity.account_id,
            OrganizationInvitation.status == "PENDING",
        )
        .order_by(OrganizationInvitation.created_at.desc())
    )
    invites = invites_res.scalars().all()

    # Total seats used = active principals + pending invites
    used_seats = len(principals) + len(invites)
    max_seats = max(account.seat_count or 1, 1)

    # Teams / Enterprise tier grants multi-seat pooling;
    # Explorer / Professional defaults to 1 seat unless upgraded
    can_invite = (
        identity.role == "admin"
        and used_seats < max_seats
        and account.status == "ACTIVE"
    )

    member_list = [
        MemberResponse(
            id=p.id,
            email=p.email,
            role=getattr(p, "role", "admin") or "admin",
            status=p.status,
            created_at=p.created_at,
            is_current_user=(p.id == identity.principal_id),
        )
        for p in principals
    ]

    invitation_list = [
        InvitationResponse(
            id=inv.id,
            email=inv.email,
            role=inv.role,
            status=inv.status,
            created_at=inv.created_at,
            expires_at=inv.expires_at,
        )
        for inv in invites
    ]

    return OrganizationOverviewResponse(
        account_id=account.id,
        account_name=account.name,
        plan_tier=account.plan_tier,
        seat_count=max_seats,
        used_seats=used_seats,
        available_seats=max(0, max_seats - used_seats),
        can_invite=can_invite,
        members=member_list,
        invitations=invitation_list,
    )


@router.post("/invitations", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    db: SessionDep,
    identity: IdentityDep,
    req: CreateInvitationRequest,
) -> InvitationResponse:
    """Issue a new team member invitation."""
    if identity.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization administrators can invite new members.",
        )

    # Check account seat limit
    account_res = await db.execute(
        select(Account).where(Account.id == identity.account_id)
    )
    account = account_res.scalar_one_or_none()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found."
        )

    # Check total active members + pending invitations
    active_count = await db.scalar(
        select(func.count(Principal.id)).where(
            Principal.account_id == identity.account_id,
            Principal.status == "ACTIVE",
        )
    ) or 0

    pending_count = await db.scalar(
        select(func.count(OrganizationInvitation.id)).where(
            OrganizationInvitation.account_id == identity.account_id,
            OrganizationInvitation.status == "PENDING",
        )
    ) or 0

    total_allocated = active_count + pending_count
    max_seats = max(account.seat_count or 1, 1)

    if total_allocated >= max_seats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Seat capacity reached ({total_allocated}/{max_seats}). "
                "Upgrade to Teams or Enterprise, or add additional seats in Billing."
            ),
        )

    clean_email = req.email.strip().lower()

    # Check if user is already an active member
    existing_principal = await db.scalar(
        select(Principal.id).where(
            Principal.account_id == identity.account_id,
            func.lower(Principal.email) == clean_email,
            Principal.status == "ACTIVE",
        )
    )
    if existing_principal:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{clean_email} is already an active member of this organization.",
        )

    # Cancel any previous pending invitation for this email
    existing_invites = await db.execute(
        select(OrganizationInvitation).where(
            OrganizationInvitation.account_id == identity.account_id,
            func.lower(OrganizationInvitation.email) == clean_email,
            OrganizationInvitation.status == "PENDING",
        )
    )
    for old_inv in existing_invites.scalars().all():
        old_inv.status = "REVOKED"

    # Generate cryptographically secure invite token (32 bytes hex)
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    now = dt.datetime.now(dt.UTC)
    expires_at = now + dt.timedelta(days=7)

    invitation = OrganizationInvitation(
        id=new_uuid7(),
        account_id=identity.account_id,
        invited_by_principal_id=identity.principal_id,
        email=clean_email,
        role=req.role,
        token_hash=token_hash,
        status="PENDING",
        expires_at=expires_at,
        created_at=now,
    )
    db.add(invitation)
    await db.commit()

    # Format the invite url
    from app.core.config import get_settings
    from app.core.email_templates.engine import send_talvrin_template_email

    cfg = get_settings()
    base_url = cfg.frontend_url.rstrip("/")
    full_invite_url = f"{base_url}/join?token={raw_token}&email={clean_email}"
    invite_url = f"/join?token={raw_token}&email={clean_email}"

    # Dispatch email notification via Resend
    try:
        org_name = account.name or "Talvrin Organization"
        send_talvrin_template_email(
            template_id="TAL-EML-EN-ORG_INVITE",
            recipient_email=clean_email,
            variables={
                "recipient_first_name": clean_email.split("@")[0].capitalize(),
                "organization_name": org_name,
                "action_url": full_invite_url,
                "help_url": f"{base_url}/guides",
                "notice_reference": f"INV-{invitation.id}",
            },
            badge_label=f"Team Invite &bull; {req.role.upper()}",
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to dispatch invitation email via Resend: %s", exc
        )

    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        status=invitation.status,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        invite_url=invite_url,
    )


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    db: SessionDep,
    identity: IdentityDep,
    invitation_id: uuid.UUID,
) -> None:
    """Revoke a pending team invitation."""
    if identity.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can revoke invitations.",
        )

    invitation_res = await db.execute(
        select(OrganizationInvitation).where(
            OrganizationInvitation.id == invitation_id,
            OrganizationInvitation.account_id == identity.account_id,
        )
    )
    invitation = invitation_res.scalar_one_or_none()
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found."
        )

    invitation.status = "REVOKED"
    await db.commit()


@router.patch("/members/{member_id}/role", response_model=MemberResponse)
async def update_member_role(
    db: SessionDep,
    identity: IdentityDep,
    member_id: uuid.UUID,
    req: UpdateMemberRoleRequest,
) -> MemberResponse:
    """Modify a member's role (admin, analyst, viewer)."""
    if identity.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can update member roles.",
        )

    # Protect against demoting oneself if the sole admin
    if member_id == identity.principal_id and req.role != "admin":
        admin_count = await db.scalar(
            select(func.count(Principal.id)).where(
                Principal.account_id == identity.account_id,
                Principal.role == "admin",
                Principal.status == "ACTIVE",
            )
        ) or 0
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the only remaining administrator in the organization.",
            )

    member_res = await db.execute(
        select(Principal).where(
            Principal.id == member_id,
            Principal.account_id == identity.account_id,
            Principal.status == "ACTIVE",
        )
    )
    member = member_res.scalar_one_or_none()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found."
        )

    member.role = req.role
    await db.commit()
    await db.refresh(member)

    return MemberResponse(
        id=member.id,
        email=member.email,
        role=member.role,
        status=member.status,
        created_at=member.created_at,
        is_current_user=(member.id == identity.principal_id),
    )


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    db: SessionDep,
    identity: IdentityDep,
    member_id: uuid.UUID,
) -> None:
    """Remove a member from the organization, revoking active sessions."""
    if identity.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can remove organization members.",
        )

    if member_id == identity.principal_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot remove yourself. Transfer admin ownership or "
                "delete account in Data Controls."
            ),
        )

    member_res = await db.execute(
        select(Principal).where(
            Principal.id == member_id,
            Principal.account_id == identity.account_id,
            Principal.status == "ACTIVE",
        )
    )
    member = member_res.scalar_one_or_none()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found."
        )

    # Soft delete principal and terminate all active sessions
    member.status = "REMOVED"
    await db.execute(
        text(
            "UPDATE identity.session SET revoked_at = now() "
            "WHERE principal_id = :pid AND revoked_at IS NULL"
        ),
        {"pid": member_id},
    )
    await db.commit()


# --- Public / Join Endpoints ---

class InvitationDetailsResponse(BaseModel):
    account_name: str
    email: str
    role: str
    status: str
    is_valid: bool


class AcceptInvitationRequest(BaseModel):
    token: str
    password: str


@router.get("/join/{token}/details", response_model=InvitationDetailsResponse)
async def get_invitation_details(
    db: SessionDep,
    token: str,
) -> InvitationDetailsResponse:
    """Public check for an invitation token without authentication."""
    token_hash = _hash_token(token)
    inv_res = await db.execute(
        select(OrganizationInvitation).where(
            OrganizationInvitation.token_hash == token_hash
        )
    )
    inv = inv_res.scalar_one_or_none()
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation link is invalid or does not exist.",
        )

    # Check expiration and status
    now = dt.datetime.now(dt.UTC)
    is_expired = inv.expires_at < now
    is_pending = inv.status == "PENDING"
    is_valid = is_pending and not is_expired

    # Fetch Account Name
    account = await db.scalar(select(Account.name).where(Account.id == inv.account_id))

    return InvitationDetailsResponse(
        account_name=account or "Talvrin Organization",
        email=inv.email,
        role=inv.role,
        status="EXPIRED" if is_expired and is_pending else inv.status,
        is_valid=is_valid,
    )


@router.post("/join/accept", response_model=MemberResponse)
async def accept_invitation(
    db: SessionDep,
    req: AcceptInvitationRequest,
) -> MemberResponse:
    """Accept invitation by setting password and joining the tenant organization."""
    from app.core.config import get_settings
    from app.core.http_client import get_http_client
    from app.modules.identity import supabase_auth

    token_hash = _hash_token(req.token)
    inv_res = await db.execute(
        select(OrganizationInvitation).where(
            OrganizationInvitation.token_hash == token_hash
        )
    )
    inv = inv_res.scalar_one_or_none()
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation link is invalid or expired.",
        )

    now = dt.datetime.now(dt.UTC)
    if inv.status != "PENDING" or inv.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has expired or has already been used.",
        )

    http = get_http_client()
    cfg = get_settings()

    # Create Supabase auth user
    try:
        sb_user = await supabase_auth.sign_up(
            http, email=inv.email, password=req.password, settings=cfg
        )
    except supabase_auth.EmailAlreadyRegistered:
        # If user is already registered in Supabase, sign in to confirm identity
        try:
            auth_res = await supabase_auth.sign_in_with_password(
                http, email=inv.email, password=req.password, settings=cfg
            )
            sb_user = auth_res.user
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "An account with this email exists. "
                    "Please use your existing account password."
                ),
            ) from exc
    except supabase_auth.WeakPassword as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.reason,
        ) from exc

    # Join this user to the account as a new principal with the assigned role
    principal_id = new_uuid7()
    principal = Principal(
        id=principal_id,
        account_id=inv.account_id,
        email=inv.email,
        status="ACTIVE",
        supabase_user_id=sb_user.id,
        role=inv.role,
    )
    db.add(principal)

    # Mark invitation as accepted
    inv.status = "ACCEPTED"
    inv.accepted_at = now
    await db.commit()
    await db.refresh(principal)

    return MemberResponse(
        id=principal.id,
        email=principal.email,
        role=principal.role,
        status=principal.status,
        created_at=principal.created_at,
        is_current_user=False,
    )


