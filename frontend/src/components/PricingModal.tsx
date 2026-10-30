import { useState, useId } from 'react'
import {
  X,
  CheckCircle2,
  Users,
  Building2,
  Sparkles,
  ShieldCheck,
  Check,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  type BillingCycle,
} from '@/data/pricing'

interface PricingModalProps {
  isOpen: boolean
  onClose: () => void
  currentPlanId?: string
  onSelectPlan?: (planId: string, cycle: BillingCycle) => void
}

interface PlanCardDef {
  id: string
  name: string
  badge?: string
  monthlyPrice: number
  annualPrice: number
  crossedPrice?: number
  isFree?: boolean
  isPopular?: boolean
  targetAudience: string
  features: string[]
}

const MODAL_PLANS: PlanCardDef[] = [
  {
    id: 'explorer',
    name: 'Basic',
    isFree: true,
    monthlyPrice: 0,
    annualPrice: 0,
    targetAudience: 'Perfect for individuals',
    features: [
      'Automated Meeting Scheduling',
      'Basic Calendar Sync',
      'Daily Schedule Overview',
      'Email Reminders',
      'Task Management',
      '24/7 Customer Support',
      'Single User Access',
      'Basic Reporting',
      'Mobile App Access',
    ],
  },
  {
    id: 'research',
    name: 'Pro',
    isPopular: true,
    badge: 'Popular',
    monthlyPrice: 29,
    annualPrice: 24,
    crossedPrice: 39,
    targetAudience: 'Ideal for small teams',
    features: [
      'All Basic Plan Features',
      'Advanced Calendar Integrations',
      'Customizable Notifications',
      'Priority Support',
      'Analytics and Insights',
      'Group Scheduling',
      'Multiple User Roles',
      'Advanced Reporting',
      'Custom Branding Options',
    ],
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    monthlyPrice: 99,
    annualPrice: 79,
    crossedPrice: 129,
    targetAudience: 'Perfect for large scale companies',
    features: [
      'All Pro Plan Features',
      'Dedicated Account Manager',
      'Custom Integrations',
      'Advanced Security Features',
      'Team Collaboration Tools',
      'Onboarding and Training',
      'Unlimited Users',
      'API Access with Higher Limits',
      'Advanced Audit Logs',
    ],
  },
]

export default function PricingModal({
  isOpen,
  onClose,
  currentPlanId = 'professional',
  onSelectPlan,
}: PricingModalProps) {
  const [cycle, setCycle] = useState<BillingCycle>('monthly')
  const titleId = useId()

  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      {/* Dark sleek backdrop */}
      <div
        className="fixed inset-0 bg-black/90 backdrop-blur-md transition-opacity animate-in fade-in duration-200"
        onClick={onClose}
      />

      {/* Main Container */}
      <div className="relative z-10 w-full max-w-5xl max-h-[95vh] overflow-y-auto rounded-3xl border border-white/[0.08] bg-[#090A0F] text-foreground shadow-2xl p-6 sm:p-10 flex flex-col gap-8 custom-scrollbar">
        {/* Top Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-medium text-slate-300">
                <Sparkles className="h-3 w-3 text-purple-400" />
                Flexible Subscription Plans
              </span>
            </div>
            <h2 id={titleId} className="mt-3 text-2xl sm:text-3xl font-semibold tracking-tight text-white">
              Choose the right plan for your workflow
            </h2>
            <p className="mt-1 text-sm text-slate-400 max-w-xl">
              Simple, transparent pricing designed to scale from individual researchers to large institutions.
            </p>
          </div>

          <button
            onClick={onClose}
            aria-label="Close modal"
            className="rounded-xl border border-white/10 bg-white/5 p-2 text-slate-400 hover:bg-white/10 hover:text-white transition-all shrink-0"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Monthly / Annual Toggle Switch */}
        <div className="flex items-center justify-center">
          <div className="inline-flex items-center rounded-2xl border border-white/10 bg-white/[0.03] p-1.5 shadow-inner">
            <button
              type="button"
              onClick={() => setCycle('monthly')}
              className={cn(
                'rounded-xl px-4 py-1.5 text-xs font-medium transition-all',
                cycle === 'monthly'
                  ? 'bg-white text-black font-semibold shadow-sm'
                  : 'text-slate-400 hover:text-white'
              )}
            >
              Monthly billing
            </button>
            <button
              type="button"
              onClick={() => setCycle('annual')}
              className={cn(
                'inline-flex items-center gap-2 rounded-xl px-4 py-1.5 text-xs font-medium transition-all',
                cycle === 'annual'
                  ? 'bg-white text-black font-semibold shadow-sm'
                  : 'text-slate-400 hover:text-white'
              )}
            >
              <span>Annual billing</span>
              <span className="rounded-full bg-purple-500/20 px-2 py-0.5 text-[10px] font-semibold text-purple-300 border border-purple-500/30">
                Save 20%
              </span>
            </button>
          </div>
        </div>

        {/* 3 Dark Sleek Plan Cards Grid (Exactly Matching Mockup) */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 lg:gap-6">
          {MODAL_PLANS.map((plan) => {
            const isCurrent =
              currentPlanId === plan.id ||
              (plan.id === 'explorer' && currentPlanId === 'free')
            const price = cycle === 'annual' ? plan.annualPrice : plan.monthlyPrice
            const crossed = plan.crossedPrice

            return (
              <div
                key={plan.id}
                className={cn(
                  'relative flex flex-col justify-between rounded-2xl border p-6 transition-all duration-200',
                  'bg-[#13151B] border-white/[0.08]',
                  plan.isPopular && 'border-white/20 ring-1 ring-white/10 shadow-xl shadow-black/60',
                  'hover:border-white/20'
                )}
              >
                {/* Upper Section */}
                <div>
                  {/* Top Bar inside Card: Icon + Name + Badge */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-slate-300">
                      {plan.id === 'explorer' && <Users className="h-4 w-4 text-slate-400" />}
                      {plan.id === 'research' && <Sparkles className="h-4 w-4 text-slate-400" />}
                      {plan.id === 'enterprise' && <Building2 className="h-4 w-4 text-slate-400" />}
                      <span className="text-[13.5px] font-medium text-slate-300">{plan.name}</span>
                    </div>

                    {plan.badge && (
                      <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-0.5 text-[11px] font-medium text-slate-300">
                        {plan.badge}
                      </span>
                    )}
                  </div>

                  {/* Price Display */}
                  <div className="mt-5 flex items-baseline justify-between">
                    {plan.isFree ? (
                      <div className="text-3xl font-bold tracking-tight text-white">
                        Free
                      </div>
                    ) : (
                      <div className="flex items-baseline gap-1">
                        <span className="text-3xl font-bold tracking-tight text-white">
                          ${price}
                        </span>
                        <span className="text-xs text-slate-400">/month</span>
                      </div>
                    )}

                    {crossed && (
                      <span className="text-sm text-slate-500 line-through">
                        ${crossed}
                      </span>
                    )}
                  </div>

                  {/* CTA Button */}
                  <div className="mt-5">
                    <button
                      type="button"
                      disabled={isCurrent}
                      onClick={() => onSelectPlan?.(plan.id, cycle)}
                      className={cn(
                        'w-full rounded-xl py-2.5 px-4 text-xs font-semibold transition-all flex items-center justify-center gap-1.5',
                        plan.isPopular
                          ? 'bg-white text-black hover:bg-slate-200 shadow-md font-semibold'
                          : 'border border-white/10 bg-white/5 text-white hover:bg-white/10'
                      )}
                    >
                      <span>{isCurrent ? 'Current Plan' : 'Get Started'}</span>
                    </button>
                  </div>

                  {/* Divider and Subtext */}
                  <div className="mt-7 pt-4 border-t border-white/[0.06]">
                    <div className="text-xs text-slate-400 font-medium mb-4">
                      {plan.targetAudience}
                    </div>

                    {/* Feature Items List with Circular Check Icons */}
                    <ul className="space-y-3">
                      {plan.features.map((feature, idx) => (
                        <li key={idx} className="flex items-start gap-2.5 text-xs text-slate-300">
                          <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-white/20 text-slate-300">
                            <Check className="h-2.5 w-2.5" />
                          </span>
                          <span className="leading-snug">{feature}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                {/* Bottom Footer Note inside card */}
                {isCurrent && (
                  <div className="mt-6 pt-3 border-t border-white/[0.06] text-center">
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-400">
                      <CheckCircle2 className="h-3 w-3" />
                      Active on your account
                    </span>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Modal Bottom Subtitle */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-400 pt-2 border-t border-white/[0.06]">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            <span>Secure 256-bit encrypted checkout. Cancel anytime with a 14-day refund policy.</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="hover:text-white cursor-pointer transition-colors">Terms of Service</span>
            <span>•</span>
            <span className="hover:text-white cursor-pointer transition-colors">Privacy Policy</span>
          </div>
        </div>
      </div>
    </div>
  )
}
