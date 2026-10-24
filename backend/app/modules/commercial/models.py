"""Commercial domain models and entitlement types.

Faithful implementation of 'Talvrin Commercial Estate Architecture 2026-10-23':
- Chapter 5: Price Book & Billing Cadence
- Chapter 7: Entitlement Engine & Feature Gating
- Chapter 8: Usage Metering Architecture
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class PlanTier(StrEnum):
    EXPLORER = "explorer"
    RESEARCH = "research"
    PROFESSIONAL = "professional"
    TEAMS = "teams"
    ENTERPRISE = "enterprise"


class BillingCadence(StrEnum):
    MONTHLY = "monthly"
    ANNUAL = "annual"


class QuotaLimits(BaseModel):
    watchlists: int | Literal["unlimited"]
    active_monitoring_rules: int | Literal["unlimited"]
    verified_research_runs_per_month: int | Literal["unlimited"]
    evidence_dossier_exports_per_month: int | Literal["unlimited"]
    filing_history_years: int | Literal["unlimited"]
    tick_level_realtime: bool
    team_workspaces: bool
    seat_count: int


class PlanDefinition(BaseModel):
    id: PlanTier
    name: str
    badge: str
    tagline: str
    seats_included: int
    monthly_price_usd: int
    annual_price_per_month_usd: int
    annual_total_usd: int
    annual_savings_percent: int
    is_popular: bool = False
    limits: QuotaLimits
    included_features: list[str]


class AccountUsage(BaseModel):
    watchlists_count: int
    active_rules_count: int
    research_runs_this_month: int
    evidence_exports_this_month: int


class AccountEntitlement(BaseModel):
    account_id: str
    plan_tier: PlanTier
    billing_cadence: BillingCadence
    is_active: bool
    current_period_end: str
    seat_count: int
    quotas: QuotaLimits
    usage: AccountUsage


class CheckoutSessionRequest(BaseModel):
    plan_tier: PlanTier
    billing_cadence: BillingCadence = BillingCadence.ANNUAL
    additional_seats: int = Field(default=0, ge=0)
    success_url: str | None = None
    cancel_url: str | None = None


class CheckoutSessionResponse(BaseModel):
    session_id: str
    checkout_url: str
    plan_tier: PlanTier
    billing_cadence: BillingCadence
    total_amount_usd: int
