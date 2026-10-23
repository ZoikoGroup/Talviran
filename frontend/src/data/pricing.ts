/**
 * Talvrin Commercial Estate Architecture (2026-10-23)
 * Chapter 5: Price Book & Billing Cadence
 * Chapter 7: Entitlement Engine & Feature Gating
 */

export type BillingCycle = 'monthly' | 'annual'

export interface PlanFeature {
  label: string
  included: boolean
  highlight?: boolean
}

export interface CommercialPlan {
  id: 'explorer' | 'research' | 'professional' | 'teams' | 'enterprise'
  name: string
  badge?: string
  tagline: string
  seats: string
  monthlyPrice: number // 0 for free or custom
  annualPricePerMonth: number // discounted monthly equivalent
  annualBilledTotal: number // upfront annual billed amount
  annualSavingsPercent: number // e.g. 17% (2 months free)
  isPopular?: boolean
  limits: {
    watchlists: string
    activeRules: string
    researchRuns: string
    evidenceExports: string
    filingHistory: string
    dataLatency: string
  }
  features: PlanFeature[]
  ctaText: string
  ctaVariant: 'outline' | 'primary' | 'team' | 'enterprise'
}

export const COMMERCIAL_PLANS: CommercialPlan[] = [
  {
    id: 'explorer',
    name: 'Explorer',
    badge: 'Evaluation Tier',
    tagline: 'Prove evidence-backed intelligence & verified calculation engine at zero risk.',
    seats: '1 Individual Seat',
    monthlyPrice: 0,
    annualPricePerMonth: 0,
    annualBilledTotal: 0,
    annualSavingsPercent: 0,
    limits: {
      watchlists: '2 saved watchlists',
      activeRules: '3 monitoring rules',
      researchRuns: '10 verified runs / mo',
      evidenceExports: '2 brief exports / mo',
      filingHistory: '1 year statutory filings',
      dataLatency: '15-min delayed quotes',
    },
    features: [
      { label: 'Deterministic Sovereign Calculation Engine', included: true },
      { label: 'Bitemporal Manifest Verification (Point-in-Time)', included: true },
      { label: 'Multi-Asset Institutional Compare Dashboard', included: true },
      { label: 'Statutory EDGAR & Companies House Search', included: true },
      { label: 'Real-time Tick-Level Monitoring & Alerting', included: false },
      { label: 'Audit-Grade Evidence Dossier Export (PDF/MD)', included: false },
      { label: 'Institutional Team Workspaces & Shared Evidence', included: false },
      { label: 'Enterprise SSO, SCIM & Dedicated SLA', included: false },
    ],
    ctaText: 'Current Plan',
    ctaVariant: 'outline',
  },
  {
    id: 'research',
    name: 'Research',
    badge: 'Serious Private Investor',
    tagline: 'Deep sovereign forensic analysis, expanded filings, and continuous alert monitoring.',
    seats: '1 Named Seat',
    monthlyPrice: 29,
    annualPricePerMonth: 24, // $290 / 12
    annualBilledTotal: 290,
    annualSavingsPercent: 17,
    limits: {
      watchlists: '10 saved watchlists',
      activeRules: '25 monitoring rules',
      researchRuns: '100 verified runs / mo',
      evidenceExports: '25 dossier exports / mo',
      filingHistory: '5 years statutory filings',
      dataLatency: 'Near real-time feeds',
    },
    features: [
      { label: 'Deterministic Sovereign Calculation Engine', included: true },
      { label: 'Bitemporal Manifest Verification (Point-in-Time)', included: true },
      { label: 'Multi-Asset Institutional Compare Dashboard', included: true },
      { label: 'Statutory EDGAR & Companies House Search', included: true },
      { label: 'Real-time Alerting (Telegram, Webhook, Email)', included: true },
      { label: 'Audit-Grade Evidence Dossier Export (PDF/MD)', included: true, highlight: true },
      { label: 'Institutional Team Workspaces & Shared Evidence', included: false },
      { label: 'Enterprise SSO, SCIM & Dedicated SLA', included: false },
    ],
    ctaText: 'Upgrade to Research',
    ctaVariant: 'outline',
  },
  {
    id: 'professional',
    name: 'Professional',
    badge: 'Most Popular',
    tagline: 'High-frequency institutional research, sovereign audit trails, and priority queues.',
    seats: '1 Named Seat',
    monthlyPrice: 79,
    annualPricePerMonth: 65, // $790 / 12
    annualBilledTotal: 790,
    annualSavingsPercent: 17,
    isPopular: true,
    limits: {
      watchlists: 'Unlimited watchlists',
      activeRules: '125 monitoring rules',
      researchRuns: '400 verified runs / mo',
      evidenceExports: '125 dossier exports / mo',
      filingHistory: '15+ years full historical corpus',
      dataLatency: 'Real-time tick & exchange feeds',
    },
    features: [
      { label: 'Deterministic Sovereign Calculation Engine', included: true },
      { label: 'Bitemporal Manifest Verification (Point-in-Time)', included: true },
      { label: 'Multi-Asset Institutional Compare Dashboard', included: true },
      { label: 'Statutory EDGAR & Companies House Search', included: true },
      { label: 'Real-time Alerting with custom condition DSL', included: true },
      { label: 'Unlimited Audit-Grade Dossiers (PDF, MD, JSON)', included: true, highlight: true },
      { label: 'Priority Research Execution Queue & Dedicated Node', included: true, highlight: true },
      { label: 'Enterprise SSO, SCIM & Dedicated SLA', included: false },
    ],
    ctaText: 'Upgrade to Professional',
    ctaVariant: 'primary',
  },
  {
    id: 'teams',
    name: 'Teams',
    badge: 'Multi-Seat Pod',
    tagline: 'Shared institutional evidence archives, collaborative pods, and pooled quota capacity.',
    seats: '3 Named Seats Included (+ $49/mo extra seat)',
    monthlyPrice: 249,
    annualPricePerMonth: 207, // $2,490 / 12
    annualBilledTotal: 2490,
    annualSavingsPercent: 17,
    limits: {
      watchlists: 'Unlimited pooled watchlists',
      activeRules: '400 active rules (pooled)',
      researchRuns: '1,200 verified runs / mo',
      evidenceExports: '350 dossier exports / mo',
      filingHistory: 'Full global historical corpus',
      dataLatency: 'Direct institutional data bridge',
    },
    features: [
      { label: 'All Professional Plan Entitlements Included', included: true },
      { label: '3 Team Seats Included with Role-Based Access Control', included: true, highlight: true },
      { label: 'Shared Institutional Workspace & Dossier Library', included: true, highlight: true },
      { label: 'Pooled Team Monitoring Quotas & Shared Webhooks', included: true },
      { label: 'Audit-Grade Evidence Cryptographic Chain-of-Custody', included: true },
      { label: 'Centralized Team Billing & Seat Management', included: true },
      { label: 'Business-Hours Priority SLA & Onboarding Session', included: true, highlight: true },
      { label: 'Enterprise SSO, SCIM & Dedicated SLA', included: false },
    ],
    ctaText: 'Start Teams Trial',
    ctaVariant: 'team',
  },
]

export const ENTERPRISE_TIER = {
  name: 'Enterprise',
  tagline: 'Custom institutional deployments, private VPC/on-prem, SCIM SSO, and tailored SLAs.',
  seats: 'Unlimited / Contracted Seats',
  features: [
    'Custom seat volume & negotiated capacity',
    'SAML 2.0 / Okta / Azure AD SSO & SCIM Directory Sync',
    'Dedicated VPC or On-Premises Bitemporal Node',
    'Custom Data Connectors (FactSet, Bloomberg, Refinitiv)',
    '24/7 Dedicated Support Engineer & 99.99% Financial SLA',
    'Institutional Master Services Agreement (MSA) & Invoicing',
  ],
  ctaText: 'Contact Institutional Sales',
}
