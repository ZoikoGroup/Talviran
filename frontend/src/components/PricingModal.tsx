import { useState, useId } from 'react'
import {
  X,
  Check,
  Sparkles,
  ShieldCheck,
  Building2,
  Users,
  ArrowRight,
  Clock,
  BadgeCheck,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  COMMERCIAL_PLANS,
  ENTERPRISE_TIER,
  type BillingCycle,
  type CommercialPlan,
} from '@/data/pricing'

interface PricingModalProps {
  isOpen: boolean
  onClose: () => void
  currentPlanId?: string
  onSelectPlan?: (planId: string, cycle: BillingCycle) => void
}

export default function PricingModal({
  isOpen,
  onClose,
  currentPlanId = 'professional',
  onSelectPlan,
}: PricingModalProps) {
  const [cycle, setCycle] = useState<BillingCycle>('annual')
  const [hoveredPlan, setHoveredPlan] = useState<string | null>(null)
  const titleId = useId()

  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/80 backdrop-blur-md transition-opacity animate-in fade-in duration-200"
        onClick={onClose}
      />

      {/* Modal Dialog Body */}
      <div className="relative z-10 w-full max-w-6xl max-h-[92vh] overflow-y-auto rounded-2xl border border-border/80 bg-[#090d16] text-foreground shadow-2xl shadow-black/90 p-5 sm:p-8 flex flex-col gap-6 custom-scrollbar">
        {/* Top Header Row */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-0.5 text-[11px] font-semibold text-primary uppercase tracking-wider">
                <Sparkles className="h-3 w-3" />
                Institutional Pricing Architecture
              </span>
              <span className="hidden sm:inline-flex items-center gap-1 text-[11px] text-muted-foreground font-mono">
                <ShieldCheck className="h-3 w-3 text-emerald-400" />
                Deterministic & Audit-Verified
              </span>
            </div>
            <h2 id={titleId} className="mt-2 text-2xl sm:text-3xl font-bold tracking-tight text-white">
              Institutional Plans & Entitlements
            </h2>
            <p className="mt-1 text-sm text-muted-foreground max-w-2xl leading-relaxed">
              Transparent capacity tiers engineered for sovereign calculation rigor, real-time alerting, and verifiable chain-of-custody intelligence.
            </p>
          </div>

          <button
            onClick={onClose}
            aria-label="Close modal"
            className="rounded-xl border border-border/60 bg-muted/20 p-2 text-muted-foreground hover:bg-muted/50 hover:text-white transition-all shrink-0"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Billing Cadence Switcher with 17% Annual Discount Pill */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-y border-border/60 py-4 bg-muted/10 -mx-5 sm:-mx-8 px-5 sm:px-8">
          <div className="flex items-center gap-3">
            <span className="text-xs uppercase tracking-widest font-semibold text-muted-foreground">
              Billing Frequency:
            </span>
            <div className="inline-flex items-center rounded-xl border border-border bg-black/40 p-1">
              <button
                type="button"
                onClick={() => setCycle('monthly')}
                className={cn(
                  'rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all',
                  cycle === 'monthly'
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-white'
                )}
              >
                Monthly
              </button>
              <button
                type="button"
                onClick={() => setCycle('annual')}
                className={cn(
                  'inline-flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all',
                  cycle === 'annual'
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-white'
                )}
              >
                <span>Annual Billing</span>
                <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold text-emerald-300 border border-emerald-500/30">
                  Save 17% (2 Mo Free)
                </span>
              </button>
            </div>
          </div>

          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5 text-primary" />
              Instant Upgrade Provisioning
            </span>
            <span className="hidden sm:inline-block">•</span>
            <span className="hidden sm:flex items-center gap-1.5">
              <BadgeCheck className="h-3.5 w-3.5 text-emerald-400" />
              SOC2 & Statutory Audit Ready
            </span>
          </div>
        </div>

        {/* 4-Tier Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-5">
          {COMMERCIAL_PLANS.map((plan: CommercialPlan) => {
            const isCurrent = plan.id === currentPlanId
            const isPopular = plan.isPopular
            const isTeams = plan.id === 'teams'
            const isHovered = hoveredPlan === plan.id

            const priceDisplay =
              plan.monthlyPrice === 0
                ? '$0'
                : cycle === 'annual'
                ? `$${plan.annualPricePerMonth}`
                : `$${plan.monthlyPrice}`

            const billingSubtext =
              plan.monthlyPrice === 0
                ? 'Free forever'
                : cycle === 'annual'
                ? `Billed $${plan.annualBilledTotal}/yr`
                : 'Billed monthly'

            return (
              <div
                key={plan.id}
                onMouseEnter={() => setHoveredPlan(plan.id)}
                onMouseLeave={() => setHoveredPlan(null)}
                className={cn(
                  'relative flex flex-col rounded-2xl border p-5 transition-all duration-200',
                  isHovered && 'scale-[1.01]',
                  isPopular
                    ? 'border-primary/60 bg-gradient-to-b from-primary/10 via-card/80 to-card/50 shadow-lg shadow-primary/10 ring-1 ring-primary/40'
                    : isTeams
                    ? 'border-indigo-500/40 bg-gradient-to-b from-indigo-500/10 via-card/80 to-card/50 shadow-md'
                    : 'border-border/70 bg-card/40 hover:border-border hover:bg-card/70',
                  isCurrent && 'ring-2 ring-emerald-500/50'
                )}
              >
                {/* Popular or Teams Badge */}
                {isPopular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-0.5 text-[10px] font-bold uppercase tracking-wider text-primary-foreground shadow-md">
                    Most Popular
                  </div>
                )}
                {isTeams && !isPopular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-indigo-600 px-3 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white shadow-md">
                    Multi-Seat Pod
                  </div>
                )}

                {/* Plan Header */}
                <div className="flex items-center justify-between gap-2 mt-1">
                  <div>
                    <h3 className="text-lg font-bold text-white flex items-center gap-1.5">
                      {plan.name}
                      {isTeams && <Users className="h-4 w-4 text-indigo-400 inline" />}
                    </h3>
                    <p className="text-[11px] font-medium text-primary/90 mt-0.5">
                      {plan.badge}
                    </p>
                  </div>
                  {isCurrent && (
                    <span className="rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-bold tracking-wide text-emerald-400">
                      CURRENT
                    </span>
                  )}
                </div>

                {/* Price Display */}
                <div className="mt-4 pb-4 border-b border-border/50">
                  <div className="flex items-baseline gap-1">
                    <span className="text-3xl font-extrabold text-white tracking-tight">
                      {priceDisplay}
                    </span>
                    {plan.monthlyPrice > 0 && (
                      <span className="text-xs text-muted-foreground font-medium">
                        / mo
                      </span>
                    )}
                  </div>
                  <div className="mt-1 flex items-center justify-between text-[11px]">
                    <span className="text-muted-foreground">{billingSubtext}</span>
                    <span className="font-semibold text-slate-300">{plan.seats}</span>
                  </div>
                </div>

                {/* Tagline */}
                <p className="mt-3 text-xs text-muted-foreground leading-relaxed min-h-[38px]">
                  {plan.tagline}
                </p>

                {/* Capacity Limits Pillbox */}
                <div className="mt-4 rounded-xl border border-border/40 bg-black/30 p-2.5 space-y-1.5 text-[11px]">
                  <div className="flex items-center justify-between text-slate-300">
                    <span className="text-muted-foreground">Watchlists</span>
                    <span className="font-semibold">{plan.limits.watchlists}</span>
                  </div>
                  <div className="flex items-center justify-between text-slate-300">
                    <span className="text-muted-foreground">Monitoring Rules</span>
                    <span className="font-semibold">{plan.limits.activeRules}</span>
                  </div>
                  <div className="flex items-center justify-between text-slate-300">
                    <span className="text-muted-foreground">Research Runs</span>
                    <span className="font-semibold">{plan.limits.researchRuns}</span>
                  </div>
                  <div className="flex items-center justify-between text-slate-300">
                    <span className="text-muted-foreground">Evidence Exports</span>
                    <span className="font-semibold">{plan.limits.evidenceExports}</span>
                  </div>
                </div>

                {/* Feature Checklist */}
                <div className="mt-4 space-y-2 flex-1">
                  <div className="text-[10.5px] font-bold uppercase tracking-wider text-muted-foreground">
                    Included Entitlements
                  </div>
                  <ul className="space-y-2">
                    {plan.features.map((feat, idx) => (
                      <li
                        key={idx}
                        className={cn(
                          'flex items-start gap-2 text-xs leading-snug',
                          feat.included
                            ? feat.highlight
                              ? 'text-primary font-medium'
                              : 'text-slate-300'
                            : 'text-muted-foreground/50 line-through'
                        )}
                      >
                        {feat.included ? (
                          <Check
                            className={cn(
                              'h-3.5 w-3.5 shrink-0 mt-0.5',
                              feat.highlight ? 'text-primary' : 'text-emerald-400'
                            )}
                          />
                        ) : (
                          <X className="h-3.5 w-3.5 shrink-0 mt-0.5 text-muted-foreground/40" />
                        )}
                        <span>{feat.label}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Action CTA Button */}
                <div className="mt-5 pt-3 border-t border-border/40">
                  <button
                    type="button"
                    disabled={isCurrent}
                    onClick={() => {
                      if (!isCurrent) {
                        onSelectPlan?.(plan.id, cycle)
                      }
                    }}
                    className={cn(
                      'w-full flex items-center justify-center gap-1.5 rounded-xl py-2.5 px-3 text-xs font-semibold transition-all',
                      isCurrent
                        ? 'bg-muted/40 text-muted-foreground cursor-default border border-border/50'
                        : isPopular
                        ? 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-md hover:shadow-primary/20'
                        : isTeams
                        ? 'bg-indigo-600 text-white hover:bg-indigo-500 shadow-md'
                        : 'border border-border bg-muted/20 text-foreground hover:bg-muted/50 hover:border-primary/40'
                    )}
                  >
                    <span>{isCurrent ? 'Current Plan' : plan.ctaText}</span>
                    {!isCurrent && <ArrowRight className="h-3.5 w-3.5" />}
                  </button>
                </div>
              </div>
            )
          })}
        </div>

        {/* Enterprise Bespoke Footer Banner */}
        <div className="relative overflow-hidden rounded-2xl border border-indigo-500/30 bg-gradient-to-r from-indigo-950/40 via-card to-indigo-950/20 p-5 sm:p-6">
          <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6">
            <div className="space-y-2 max-w-3xl">
              <div className="flex items-center gap-2">
                <span className="rounded-md bg-indigo-500/20 border border-indigo-500/40 px-2 py-0.5 text-[10.5px] font-bold text-indigo-300 uppercase tracking-wider">
                  Enterprise Tier
                </span>
                <span className="text-xs text-muted-foreground font-mono">
                  Custom Capacity & Compliance
                </span>
              </div>
              <h4 className="text-lg font-bold text-white">
                Institutional & Sovereign Fund Deployments
              </h4>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {ENTERPRISE_TIER.tagline}
              </p>
              <div className="flex flex-wrap gap-x-6 gap-y-1.5 pt-1 text-xs text-slate-300">
                {ENTERPRISE_TIER.features.slice(0, 4).map((f, i) => (
                  <span key={i} className="flex items-center gap-1.5">
                    <Check className="h-3.5 w-3.5 text-indigo-400 shrink-0" />
                    {f}
                  </span>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={() => {
                onSelectPlan?.('enterprise', cycle)
              }}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-indigo-400/40 bg-indigo-600/80 hover:bg-indigo-600 px-5 py-3 text-xs font-semibold text-white transition-all shadow-lg shadow-indigo-950/50 whitespace-nowrap"
            >
              <Building2 className="h-4 w-4" />
              <span>{ENTERPRISE_TIER.ctaText}</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Modal Footer Note */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 text-[11.5px] text-muted-foreground/80 pt-2 border-t border-border/40">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            <span>All subscriptions include our 14-day institutional money-back guarantee. Invoices issued with full tax & VAT deduction.</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="hover:text-foreground cursor-pointer transition-colors">Commercial MSA</span>
            <span>•</span>
            <span className="hover:text-foreground cursor-pointer transition-colors">Entitlements FAQ</span>
            <span>•</span>
            <span className="hover:text-foreground cursor-pointer transition-colors">Support SLA</span>
          </div>
        </div>
      </div>
    </div>
  )
}
