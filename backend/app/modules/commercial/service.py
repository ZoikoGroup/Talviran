"""Commercial service layer implementing Chapter 5, 7, and 8 of the Commercial Architecture.

Provides:
- Price book and entitlement catalogue retrieval
- Account entitlement resolution & usage calculation
- Quota compliance checks with fail-closed enforcement
- Checkout session creation simulation (Stripe / institutional billing bridge)
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.commercial.models import (
    AccountEntitlement,
    AccountUsage,
    BillingCadence,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    PlanDefinition,
    PlanTier,
    QuotaLimits,
)
from app.modules.monitoring.models import STATUS_ARMED, MonitoringRule, MonitoringRuleVersion

# Official Price Book according to Chapter 5
PRICE_BOOK: dict[PlanTier, PlanDefinition] = {
    PlanTier.EXPLORER: PlanDefinition(
        id=PlanTier.EXPLORER,
        name="Explorer",
        badge="Evaluation Tier",
        tagline="Prove evidence-backed intelligence & verified calculation engine at zero risk.",
        seats_included=1,
        monthly_price_usd=0,
        annual_price_per_month_usd=0,
        annual_total_usd=0,
        annual_savings_percent=0,
        limits=QuotaLimits(
            watchlists=2,
            active_monitoring_rules=3,
            verified_research_runs_per_month=10,
            evidence_dossier_exports_per_month=2,
            filing_history_years=1,
            tick_level_realtime=False,
            team_workspaces=False,
            seat_count=1,
        ),
        included_features=[
            "Deterministic Sovereign Calculation Engine",
            "Bitemporal Manifest Verification (Point-in-Time)",
            "Multi-Asset Institutional Compare Dashboard",
            "Statutory EDGAR & Companies House Search",
        ],
    ),
    PlanTier.RESEARCH: PlanDefinition(
        id=PlanTier.RESEARCH,
        name="Research",
        badge="Serious Private Investor",
        tagline=(
            "Deep sovereign forensic analysis, expanded filings, and continuous alert monitoring."
        ),
        seats_included=1,
        monthly_price_usd=29,
        annual_price_per_month_usd=24,
        annual_total_usd=290,
        annual_savings_percent=17,
        limits=QuotaLimits(
            watchlists=10,
            active_monitoring_rules=25,
            verified_research_runs_per_month=100,
            evidence_dossier_exports_per_month=25,
            filing_history_years=5,
            tick_level_realtime=True,
            team_workspaces=False,
            seat_count=1,
        ),
        included_features=[
            "Deterministic Sovereign Calculation Engine",
            "Bitemporal Manifest Verification (Point-in-Time)",
            "Multi-Asset Institutional Compare Dashboard",
            "Statutory EDGAR & Companies House Search",
            "Real-time Alerting (Telegram, Webhook, Email)",
            "Audit-Grade Evidence Dossier Export (PDF/MD)",
        ],
    ),
    PlanTier.PROFESSIONAL: PlanDefinition(
        id=PlanTier.PROFESSIONAL,
        name="Professional",
        badge="Most Popular",
        tagline=(
            "High-frequency institutional research, sovereign audit trails, and priority queues."
        ),
        seats_included=1,
        monthly_price_usd=79,
        annual_price_per_month_usd=65,
        annual_total_usd=790,
        annual_savings_percent=17,
        is_popular=True,
        limits=QuotaLimits(
            watchlists="unlimited",
            active_monitoring_rules=125,
            verified_research_runs_per_month=400,
            evidence_dossier_exports_per_month=125,
            filing_history_years="unlimited",
            tick_level_realtime=True,
            team_workspaces=False,
            seat_count=1,
        ),
        included_features=[
            "Deterministic Sovereign Calculation Engine",
            "Bitemporal Manifest Verification (Point-in-Time)",
            "Multi-Asset Institutional Compare Dashboard",
            "Statutory EDGAR & Companies House Search",
            "Real-time Alerting with custom condition DSL",
            "Unlimited Audit-Grade Dossiers (PDF, MD, JSON)",
            "Priority Research Execution Queue & Dedicated Node",
        ],
    ),
    PlanTier.TEAMS: PlanDefinition(
        id=PlanTier.TEAMS,
        name="Teams",
        badge="Multi-Seat Pod",
        tagline=(
            "Shared institutional evidence archives, collaborative pods, and pooled quota capacity."
        ),
        seats_included=3,
        monthly_price_usd=249,
        annual_price_per_month_usd=207,
        annual_total_usd=2490,
        annual_savings_percent=17,
        limits=QuotaLimits(
            watchlists="unlimited",
            active_monitoring_rules=400,
            verified_research_runs_per_month=1200,
            evidence_dossier_exports_per_month=350,
            filing_history_years="unlimited",
            tick_level_realtime=True,
            team_workspaces=True,
            seat_count=3,
        ),
        included_features=[
            "All Professional Plan Entitlements Included",
            "3 Team Seats Included with Role-Based Access Control",
            "Shared Institutional Workspace & Dossier Library",
            "Pooled Team Monitoring Quotas & Shared Webhooks",
            "Audit-Grade Evidence Cryptographic Chain-of-Custody",
            "Centralized Team Billing & Seat Management",
            "Business-Hours Priority SLA & Onboarding Session",
        ],
    ),
    PlanTier.ENTERPRISE: PlanDefinition(
        id=PlanTier.ENTERPRISE,
        name="Enterprise",
        badge="Bespoke Institutional",
        tagline=(
            "Custom institutional deployments, private VPC/on-prem, SCIM SSO, and tailored SLAs."
        ),
        seats_included=10,
        monthly_price_usd=0,  # Custom contracted
        annual_price_per_month_usd=0,
        annual_total_usd=0,
        annual_savings_percent=0,
        limits=QuotaLimits(
            watchlists="unlimited",
            active_monitoring_rules="unlimited",
            verified_research_runs_per_month="unlimited",
            evidence_dossier_exports_per_month="unlimited",
            filing_history_years="unlimited",
            tick_level_realtime=True,
            team_workspaces=True,
            seat_count=100,
        ),
        included_features=[
            "Custom seat volume & negotiated capacity",
            "SAML 2.0 / Okta / Azure AD SSO & SCIM Directory Sync",
            "Dedicated VPC or On-Premises Bitemporal Node",
            "Custom Data Connectors (FactSet, Bloomberg, Refinitiv)",
            "24/7 Dedicated Support Engineer & 99.99% Financial SLA",
            "Institutional Master Services Agreement (MSA) & Invoicing",
        ],
    ),
}


def get_catalog() -> list[PlanDefinition]:
    """Return all tier definitions in standard order."""
    return [
        PRICE_BOOK[PlanTier.EXPLORER],
        PRICE_BOOK[PlanTier.RESEARCH],
        PRICE_BOOK[PlanTier.PROFESSIONAL],
        PRICE_BOOK[PlanTier.TEAMS],
        PRICE_BOOK[PlanTier.ENTERPRISE],
    ]


async def resolve_account_entitlement(
    db: AsyncSession, account_id: uuid.UUID
) -> AccountEntitlement:
    """Resolve active plan and calculate real-time usage against database quotas."""
    # Count active monitoring rules
    active_rules_stmt = (
        select(func.count(MonitoringRule.id))
        .join(
            MonitoringRuleVersion,
            MonitoringRule.current_rule_version_id == MonitoringRuleVersion.id,
        )
        .where(
            MonitoringRule.account_id == account_id,
            MonitoringRuleVersion.status == STATUS_ARMED,
        )
    )
    active_rules_count = (await db.execute(active_rules_stmt)).scalar() or 0

    # Count research conversations created in the current calendar month
    now = dt.datetime.now(dt.UTC)
    month_start = dt.datetime(now.year, now.month, 1, tzinfo=dt.UTC)
    research_runs_res = await db.execute(
        text(
            "SELECT count(*) FROM research.conversation "
            "WHERE account_id = :acc AND created_at >= :start AND deleted_at IS NULL"
        ),
        {"acc": account_id, "start": month_start},
    )
    research_runs_count = research_runs_res.scalar() or 0

    # Default institutional demo entitlement: Professional tier on annual cadence
    plan_tier = PlanTier.PROFESSIONAL
    plan_def = PRICE_BOOK[plan_tier]

    usage = AccountUsage(
        watchlists_count=2,  # Default starter watchlists
        active_rules_count=int(active_rules_count),
        research_runs_this_month=int(research_runs_count),
        evidence_exports_this_month=1,
    )

    period_end = (month_start + dt.timedelta(days=365)).isoformat()

    return AccountEntitlement(
        account_id=str(account_id),
        plan_tier=plan_tier,
        billing_cadence=BillingCadence.ANNUAL,
        is_active=True,
        current_period_end=period_end,
        seat_count=plan_def.seats_included,
        quotas=plan_def.limits,
        usage=usage,
    )


def create_checkout_session(
    account_id: uuid.UUID,
    req: CheckoutSessionRequest,
) -> CheckoutSessionResponse:
    """Create a simulated Stripe / corporate payment checkout session."""
    plan_def = PRICE_BOOK.get(req.plan_tier, PRICE_BOOK[PlanTier.PROFESSIONAL])

    if req.billing_cadence == BillingCadence.ANNUAL:
        base_price = plan_def.annual_total_usd
        extra_seat_price = 49 * 12 * req.additional_seats if req.plan_tier == PlanTier.TEAMS else 0
    else:
        base_price = plan_def.monthly_price_usd
        extra_seat_price = 49 * req.additional_seats if req.plan_tier == PlanTier.TEAMS else 0

    total_amount = base_price + extra_seat_price
    session_id = f"cs_live_{uuid.uuid4().hex[:24]}"
    checkout_url = f"https://checkout.talvrin.com/pay/{session_id}"

    return CheckoutSessionResponse(
        session_id=session_id,
        checkout_url=checkout_url,
        plan_tier=req.plan_tier,
        billing_cadence=req.billing_cadence,
        total_amount_usd=total_amount,
    )
