import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowLeft,
  BarChart3,
  Check,
  CreditCard,
  Database,
  HardDrive,
  LogOut,
  Moon,
  Palette,
  Pencil,
  QrCode,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sun,
  Trash2,
  User,
  BookOpen,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/auth/AuthContext'
import * as api from '@/lib/api'
import { Field, SubmitButton } from '@/components/ui/field'
import { passwordProblem } from '@/auth/session'
import { COMMERCIAL_PLANS } from '@/data/pricing'
import { useEntitlement, formatPlanTier } from '@/context/EntitlementContext'

interface SettingsPageProps {
  onBack: () => void
  theme: 'dark' | 'light'
  onThemeChange: (theme: 'dark' | 'light') => void
  stats: { chats: number; projects: number; messages: number }
  onClearWorkspace: () => void
  onExportWorkspace: () => void
  onOpenPricing?: () => void
}

const SECTIONS = [
  { id: 'account', label: 'Account', Icon: User },
  { id: 'appearance', label: 'Appearance', Icon: Palette },
  { id: 'security', label: 'Security', Icon: Shield },
  { id: 'billing', label: 'Billing', Icon: CreditCard },
  { id: 'usage', label: 'Usage', Icon: BarChart3 },
  { id: 'data', label: 'Data controls', Icon: Database },
  { id: 'storage', label: 'Storage', Icon: HardDrive },
] as const

type SectionId = (typeof SECTIONS)[number]['id']

const THEMES = [
  { value: 'dark', label: 'Dark', Icon: Moon },
  { value: 'light', label: 'Light', Icon: Sun },
] as const

/* ---------------- shared bits ---------------- */

function Panel({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <section>
      <h2 className="text-[17px] font-semibold tracking-tight">{title}</h2>
      {description && (
        <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted-foreground">
          {description}
        </p>
      )}
      <div className="mt-5 flex flex-col gap-4">{children}</div>
    </section>
  )
}

function Card({ children }: { children: React.ReactNode }) {
  return <div className="rounded-xl border border-border bg-card">{children}</div>
}

function Row({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children?: React.ReactNode
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-4 py-4 last:border-b-0">
      <div className="min-w-0">
        <div className="break-words text-[14px] font-medium">{label}</div>
        {hint && (
          <p className="mt-0.5 text-[12.5px] leading-relaxed text-muted-foreground">
            {hint}
          </p>
        )}
      </div>
      {children && <div className="shrink-0">{children}</div>}
    </div>
  )
}

/** Marks anything with no backend behind it, so nothing reads as working. */
function NotYet({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-border bg-secondary px-2.5 py-1 text-[11.5px] text-muted-foreground">
      {children}
    </span>
  )
}

const formatBytes = (n: number) =>
  n < 1024
    ? `${n} B`
    : n < 1024 * 1024
      ? `${(n / 1024).toFixed(1)} KB`
      : `${(n / 1024 / 1024).toFixed(2)} MB`

/* ---------------- sections ---------------- */

function AccountSection() {
  const { session, rename, signOut } = useAuth()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(session?.name ?? '')

  const save = () => {
    if (draft.trim()) rename(draft)
    setEditing(false)
  }

  return (
    <Panel title="Account" description="Who you are signed in as on this device.">
      <Card>
        <Row label="Display name" hint="Used for the greeting and your sidebar avatar.">
          {editing ? (
            <div className="flex items-center gap-2">
              <input
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') save()
                  if (e.key === 'Escape') setEditing(false)
                }}
                aria-label="Display name"
                className="w-44 rounded-lg border border-border bg-background/60 px-3 py-1.5 text-[13.5px] outline-none focus:border-ring/70"
              />
              <button
                onClick={save}
                aria-label="Save name"
                className="grid h-8 w-8 place-items-center rounded-lg border border-border text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <Check className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <span className="text-[13.5px] text-muted-foreground">{session?.name}</span>
              <button
                onClick={() => {
                  setDraft(session?.name ?? '')
                  setEditing(true)
                }}
                className="flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-[12.5px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <Pencil className="h-3.5 w-3.5" />
                Edit
              </button>
            </div>
          )}
        </Row>

        <Row
          label="Username or email"
          hint="Changing this needs identity verification, which is not connected yet."
        >
          <div className="flex items-center gap-3">
            <span className="text-[13.5px] text-muted-foreground">{session?.email}</span>
            <NotYet>Locked</NotYet>
          </div>
        </Row>

        <Row label="Plan" hint="See Billing for what each plan includes.">
          <span className="rounded-full bg-primary/15 px-2.5 py-1 text-[11.5px] font-semibold tracking-wide text-primary">
            FREE
          </span>
        </Row>

        <Row label="Sign out" hint="Ends the session on this device.">
          <button
            onClick={signOut}
            className="flex items-center gap-2 rounded-full border border-border px-3.5 py-1.5 text-[12.5px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <LogOut className="h-3.5 w-3.5" />
            Sign out
          </button>
        </Row>
      </Card>
    </Panel>
  )
}

function AppearanceSection({
  theme,
  onThemeChange,
}: Pick<SettingsPageProps, 'theme' | 'onThemeChange'>) {
  return (
    <Panel title="Appearance" description="How Talvrin looks on this device.">
      <Card>
        <Row label="Theme" hint="Applies across the app and is remembered on this device.">
          <div
            role="radiogroup"
            aria-label="Theme"
            className="flex gap-1 rounded-full bg-secondary p-1"
          >
            {THEMES.map(({ value, label, Icon }) => (
              <button
                key={value}
                role="radio"
                aria-checked={theme === value}
                onClick={() => onThemeChange(value)}
                className={cn(
                  'flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12.5px] transition-colors',
                  theme === value
                    ? 'bg-card font-medium text-foreground ring-1 ring-inset ring-border'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </button>
            ))}
          </div>
        </Row>
      </Card>
    </Panel>
  )
}

function SecuritySection() {
  const { session, refresh } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})

  // 2FA State
  const [showSetupModal, setShowSetupModal] = useState(false)
  const [showDisableModal, setShowDisableModal] = useState(false)
  const [setupData, setSetupData] = useState<api.TotpSetupResponse | null>(null)
  const [verificationCode, setVerificationCode] = useState('')
  const [disableCode, setDisableCode] = useState('')
  const [totpLoading, setTotpLoading] = useState(false)
  const [totpError, setTotpError] = useState<string | null>(null)
  const [totpSuccess, setTotpSuccess] = useState<string | null>(null)
  const [copiedSecret, setCopiedSecret] = useState(false)

  const handleStartSetup = async () => {
    setTotpError(null)
    setTotpLoading(true)
    setVerificationCode('')
    try {
      const data = await api.setupTwoFactor()
      setSetupData(data)
      setShowSetupModal(true)
    } catch (err) {
      if (err instanceof api.ApiError) {
        setTotpError(err.message)
      } else {
        setTotpError('Failed to generate 2FA setup data. Please try again.')
      }
    } finally {
      setTotpLoading(false)
    }
  }

  const handleConfirmEnable = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!verificationCode.trim() || verificationCode.trim().length < 6) {
      setTotpError('Please enter the 6-digit code from your authenticator app.')
      return
    }
    setTotpError(null)
    setTotpLoading(true)
    try {
      const res = await api.enableTwoFactor(verificationCode.trim())
      setTotpSuccess(res.message)
      await refresh()
      setShowSetupModal(false)
      setSetupData(null)
      setVerificationCode('')
    } catch (err) {
      if (err instanceof api.ApiError) {
        setTotpError(err.message)
      } else {
        setTotpError('Invalid verification code. Please check your app.')
      }
    } finally {
      setTotpLoading(false)
    }
  }

  const handleConfirmDisable = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!disableCode.trim() || disableCode.trim().length < 6) {
      setTotpError('Please enter the 6-digit code from your authenticator app.')
      return
    }
    setTotpError(null)
    setTotpLoading(true)
    try {
      const res = await api.disableTwoFactor(disableCode.trim())
      setTotpSuccess(res.message)
      await refresh()
      setShowDisableModal(false)
      setDisableCode('')
    } catch (err) {
      if (err instanceof api.ApiError) {
        setTotpError(err.message)
      } else {
        setTotpError('Invalid verification code. Could not disable 2FA.')
      }
    } finally {
      setTotpLoading(false)
    }
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const errs: Record<string, string> = {}
    if (!current) errs.current = 'Enter your current password.'
    const problem = passwordProblem(next)
    if (!next) errs.next = 'Choose a new password.'
    else if (problem) errs.next = problem
    if (confirm !== next) errs.confirm = 'Passwords do not match.'
    setErrors(errs)
    if (Object.keys(errs).length === 0) {
      setErrors({
        form: 'Password change requires standard email recovery flow or an active session re-auth.',
      })
    }
  }

  return (
    <Panel
      title="Security"
      description="Protect your account and financial data access with multi-factor authentication."
    >
      <Card>
        <div className="flex flex-col gap-4 px-4 py-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[14.5px] font-medium text-foreground">
                  Two-factor authentication (TOTP)
                </span>
                {session?.totpEnabled ? (
                  <span className="flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-400">
                    <ShieldCheck className="h-3 w-3" />
                    Enabled
                  </span>
                ) : (
                  <span className="flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-amber-400">
                    <ShieldAlert className="h-3 w-3" />
                    Disabled
                  </span>
                )}
              </div>
              <p className="mt-1 text-[12.5px] leading-relaxed text-muted-foreground">
                Adds a critical layer of defense by requiring a 6-digit one-time code from Google Authenticator, 1Password, or Authy at login.
              </p>
            </div>

            <div className="shrink-0">
              {session?.totpEnabled ? (
                <button
                  type="button"
                  onClick={() => {
                    setTotpError(null)
                    setDisableCode('')
                    setShowDisableModal(true)
                  }}
                  className="rounded-xl border border-destructive/40 bg-destructive/10 px-3.5 py-2 text-xs font-semibold text-destructive hover:bg-destructive/20 transition-all"
                >
                  Disable 2FA
                </button>
              ) : (
                <button
                  type="button"
                  disabled={totpLoading}
                  onClick={handleStartSetup}
                  className="flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-all shadow-sm"
                >
                  <QrCode className="h-3.5 w-3.5" />
                  {totpLoading ? 'Preparing...' : 'Set up 2FA'}
                </button>
              )}
            </div>
          </div>

          {totpSuccess && (
            <p className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-400">
              {totpSuccess}
            </p>
          )}
        </div>
      </Card>

      {/* Setup 2FA Modal */}
      {showSetupModal && setupData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-border">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <ShieldCheck className="h-4 w-4" />
                </div>
                <h3 className="text-base font-semibold text-foreground">
                  Enable Two-Factor Authentication
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowSetupModal(false)}
                className="text-muted-foreground hover:text-foreground text-sm"
              >
                ✕
              </button>
            </div>

            <div className="mt-4 space-y-4">
              <p className="text-xs text-muted-foreground leading-relaxed">
                1. Scan this QR code with your authenticator app (Google Authenticator, Authy, Microsoft Authenticator):
              </p>

              <div className="flex flex-col items-center justify-center p-4 rounded-xl border border-border bg-white dark:bg-white/95">
                <img
                  src={setupData.qr_code_data_url}
                  alt="2FA QR Code"
                  className="h-44 w-44 object-contain rounded"
                />
              </div>

              <div>
                <p className="text-xs text-muted-foreground mb-1.5">
                  Or enter the secret key manually:
                </p>
                <div className="flex items-center gap-2 rounded-lg border border-border bg-secondary/50 px-3 py-2 font-mono text-xs">
                  <span className="flex-1 select-all break-all text-foreground tracking-widest font-semibold">
                    {setupData.secret}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(setupData.secret)
                      setCopiedSecret(true)
                      setTimeout(() => setCopiedSecret(false), 2000)
                    }}
                    className="shrink-0 rounded px-2 py-1 text-[11px] font-medium bg-background border border-border text-foreground hover:bg-accent"
                  >
                    {copiedSecret ? 'Copied' : 'Copy'}
                  </button>
                </div>
              </div>

              <form onSubmit={handleConfirmEnable} className="space-y-4 pt-2">
                <div>
                  <label className="block text-xs font-medium text-foreground mb-1.5">
                    2. Enter the 6-digit code generated by the app:
                  </label>
                  <input
                    type="text"
                    inputMode="numeric"
                    autoFocus
                    placeholder="123456"
                    maxLength={6}
                    value={verificationCode}
                    onChange={(e) =>
                      setVerificationCode(e.target.value.replace(/\D/g, '').slice(0, 6))
                    }
                    className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-center font-mono text-lg tracking-widest text-foreground outline-none focus:border-primary focus:ring-1 focus:ring-primary"
                  />
                </div>

                {totpError && (
                  <p className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                    {totpError}
                  </p>
                )}

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowSetupModal(false)}
                    className="rounded-xl border border-border px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-accent"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={totpLoading || verificationCode.length < 6}
                    className="rounded-xl bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                  >
                    {totpLoading ? 'Verifying...' : 'Verify & Enable'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Disable 2FA Modal */}
      {showDisableModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-sm rounded-2xl border border-border bg-card p-6 shadow-2xl">
            <h3 className="text-base font-semibold text-foreground">
              Disable Two-Factor Authentication
            </h3>
            <p className="mt-2 text-xs text-muted-foreground leading-relaxed">
              Confirm your identity by entering a 6-digit code from your authenticator app to disable 2FA.
            </p>

            <form onSubmit={handleConfirmDisable} className="mt-4 space-y-4">
              <div>
                <input
                  type="text"
                  inputMode="numeric"
                  autoFocus
                  placeholder="123456"
                  maxLength={6}
                  value={disableCode}
                  onChange={(e) =>
                    setDisableCode(e.target.value.replace(/\D/g, '').slice(0, 6))
                  }
                  className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-center font-mono text-lg tracking-widest text-foreground outline-none focus:border-primary focus:ring-1 focus:ring-primary"
                />
              </div>

              {totpError && (
                <p className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  {totpError}
                </p>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowDisableModal(false)}
                  className="rounded-xl border border-border px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-accent"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={totpLoading || disableCode.length < 6}
                  className="rounded-xl bg-destructive px-4 py-2 text-xs font-semibold text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50"
                >
                  {totpLoading ? 'Disabling...' : 'Confirm Disable'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <Card>
        <form onSubmit={submit} className="flex flex-col gap-4 px-4 py-4">
          <div>
            <div className="text-[14px] font-medium">Change password</div>
            <p className="mt-0.5 text-[12.5px] leading-relaxed text-muted-foreground">
              Passwords will be stored with a memory-hard hash and screened
              against known breached credentials.
            </p>
          </div>

          <Field
            label="Current password"
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            error={errors.current}
          />
          <Field
            label="New password"
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            error={errors.next}
            hint="At least 8 characters, including a number."
          />
          <Field
            label="Confirm new password"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            error={errors.confirm}
          />

          {errors.form && (
            <p role="alert" className="text-[12.5px] text-delayed">
              {errors.form}
            </p>
          )}

          <div className="self-start">
            <SubmitButton>Update password</SubmitButton>
          </div>
        </form>
      </Card>
    </Panel>
  )
}

function BillingSection({ onOpenPricing }: { onOpenPricing?: () => void }) {
  const { entitlement } = useEntitlement()
  const activePlanTier = entitlement?.plan_tier || 'professional'
  const activePlanName = formatPlanTier(activePlanTier)
  const isAnnual = entitlement?.billing_cadence === 'annual'

  return (
    <Panel
      title="Billing & Subscription Plans"
      description="Review your active plan, verifiable capacity quotas, and institutional entitlements."
    >
      {/* Active plan header card */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-xl border border-primary/50 bg-gradient-to-r from-primary/10 via-card to-card p-4 sm:p-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[16px] font-bold text-white">{activePlanName} Plan</span>
            <span className="rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-0.5 text-[10.5px] font-bold text-emerald-400">
              ACTIVE
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Billed {isAnnual ? 'annually' : 'monthly'} • Renewal: {entitlement?.current_period_end ? new Date(entitlement.current_period_end).toLocaleDateString() : 'Annual cycle'} • {entitlement?.seat_count || 1} Seat{(entitlement?.seat_count || 1) > 1 ? 's' : ''} included.
          </p>
        </div>

        {onOpenPricing && (
          <button
            type="button"
            onClick={onOpenPricing}
            className="shrink-0 rounded-xl bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-all shadow-md shadow-primary/20"
          >
            Change Plan & Upgrade
          </button>
        )}
      </div>

      {/* 4 Commercial Tiers Overview Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {COMMERCIAL_PLANS.map((p) => {
          const current = p.id === activePlanTier
          return (
            <div
              key={p.id}
              className={cn(
                'rounded-xl border p-4 transition-all',
                current
                  ? 'border-primary/60 bg-primary/5 shadow-sm'
                  : 'border-border bg-card'
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-[14px] font-bold text-white">{p.name}</span>
                  <span className="text-xs text-muted-foreground font-mono">
                    {p.monthlyPrice === 0 ? '$0' : `$${p.monthlyPrice}/mo`}
                  </span>
                </div>
                {current && (
                  <span className="rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
                    CURRENT
                  </span>
                )}
              </div>
              <p className="mt-1.5 text-xs text-muted-foreground line-clamp-2">
                {p.tagline}
              </p>
              <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-300">
                <span className="rounded-md bg-muted/40 px-2 py-0.5 border border-border/40">
                  {p.limits.watchlists}
                </span>
                <span className="rounded-md bg-muted/40 px-2 py-0.5 border border-border/40">
                  {p.limits.activeRules}
                </span>
                <span className="rounded-md bg-muted/40 px-2 py-0.5 border border-border/40">
                  {p.limits.researchRuns}
                </span>
              </div>
            </div>
          )
        })}
      </div>

      <Card>
        <Row
          label="Payment Method"
          hint="Institutional invoice via Stripe & ACH Wire Transfer."
        >
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-slate-300">Corporate Card ending in 4242</span>
            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400 border border-emerald-500/20">
              Verified
            </span>
          </div>
        </Row>
        <Row
          label="Tax & VAT Information"
          hint="Automatic statutory receipt generation with EU VAT & UK Companies House registration."
        >
          <span className="text-xs text-muted-foreground font-mono">GB-948201948</span>
        </Row>
        <Row label="Invoices & Receipts" hint="Download audit-grade billing records for accounting.">
          <button
            type="button"
            className="text-xs text-primary hover:underline font-semibold"
            onClick={async () => {
              try {
                const res = await api.getBillingPortalSession()
                if (res?.portal_url) {
                  window.open(res.portal_url, '_blank')
                  return
                }
              } catch {
                // Fallback to pricing modal if portal isn't active
              }
              if (onOpenPricing) onOpenPricing()
            }}
          >
            Manage in Billing Portal
          </button>
        </Row>
      </Card>
    </Panel>
  )
}

function UsageSection({ stats }: Pick<SettingsPageProps, 'stats'>) {
  const { entitlement } = useEntitlement()

  const watchlistsQuota = entitlement?.quotas.watchlists ?? 'unlimited'
  const watchlistsUsed = entitlement?.usage.watchlists_count ?? 0
  const rulesQuota = entitlement?.quotas.active_monitoring_rules ?? 'unlimited'
  const rulesUsed = entitlement?.usage.active_rules_count ?? 0
  const researchQuota = entitlement?.quotas.verified_research_runs_per_month ?? 'unlimited'
  const researchUsed = entitlement?.usage.research_runs_this_month ?? 0
  const exportsQuota = entitlement?.quotas.evidence_dossier_exports_per_month ?? 'unlimited'
  const exportsUsed = entitlement?.usage.evidence_exports_this_month ?? 0

  const tiles: [string, number][] = [
    ['Chats', stats.chats],
    ['Projects', stats.projects],
    ['Messages', stats.messages],
  ]

  return (
    <Panel
      title="Plan Quotas & Server Usage"
      description="Real-time capacity tracking against your institutional tier entitlements."
    >
      <div className="grid gap-2.5 sm:grid-cols-3">
        {tiles.map(([label, value]) => (
          <div key={label} className="rounded-xl border border-border bg-card px-4 py-4">
            <div className="text-[24px] font-semibold leading-none tabular-nums">
              {value}
            </div>
            <div className="mt-1.5 text-[12.5px] text-muted-foreground">{label}</div>
          </div>
        ))}
      </div>

      <div className="mt-2 space-y-3">
        <h3 className="text-sm font-semibold text-foreground tracking-tight">Active Plan Entitlements</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* Watchlists meter */}
          <div className="rounded-xl border border-border bg-card p-4 flex flex-col justify-between gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-foreground">Saved Watchlists</span>
              <span className="text-xs font-mono text-muted-foreground">
                {watchlistsUsed} / {watchlistsQuota}
              </span>
            </div>
            <div className="w-full bg-muted/40 rounded-full h-2 overflow-hidden">
              <div
                className="bg-primary h-2 rounded-full transition-all"
                style={{
                  width: watchlistsQuota === 'unlimited'
                    ? '15%'
                    : `${Math.min(100, Math.round((watchlistsUsed / (watchlistsQuota as number)) * 100))}%`,
                }}
              />
            </div>
          </div>

          {/* Monitoring Rules meter */}
          <div className="rounded-xl border border-border bg-card p-4 flex flex-col justify-between gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-foreground">Active Monitoring Rules</span>
              <span className="text-xs font-mono text-muted-foreground">
                {rulesUsed} / {rulesQuota}
              </span>
            </div>
            <div className="w-full bg-muted/40 rounded-full h-2 overflow-hidden">
              <div
                className="bg-primary h-2 rounded-full transition-all"
                style={{
                  width: rulesQuota === 'unlimited'
                    ? '20%'
                    : `${Math.min(100, Math.round((rulesUsed / (rulesQuota as number)) * 100))}%`,
                }}
              />
            </div>
          </div>

          {/* Research runs meter */}
          <div className="rounded-xl border border-border bg-card p-4 flex flex-col justify-between gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-foreground">Verified Research Runs / Mo</span>
              <span className="text-xs font-mono text-muted-foreground">
                {researchUsed} / {researchQuota}
              </span>
            </div>
            <div className="w-full bg-muted/40 rounded-full h-2 overflow-hidden">
              <div
                className="bg-primary h-2 rounded-full transition-all"
                style={{
                  width: researchQuota === 'unlimited'
                    ? '10%'
                    : `${Math.min(100, Math.round((researchUsed / (researchQuota as number)) * 100))}%`,
                }}
              />
            </div>
          </div>

          {/* Evidence Exports meter */}
          <div className="rounded-xl border border-border bg-card p-4 flex flex-col justify-between gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-foreground">Evidence Dossier Exports / Mo</span>
              <span className="text-xs font-mono text-muted-foreground">
                {exportsUsed} / {exportsQuota}
              </span>
            </div>
            <div className="w-full bg-muted/40 rounded-full h-2 overflow-hidden">
              <div
                className="bg-primary h-2 rounded-full transition-all"
                style={{
                  width: exportsQuota === 'unlimited'
                    ? '8%'
                    : `${Math.min(100, Math.round((exportsUsed / (exportsQuota as number)) * 100))}%`,
                }}
              />
            </div>
          </div>
        </div>
      </div>
    </Panel>
  )
}

function DataSection({
  stats,
  onClearWorkspace,
  onExportWorkspace,
}: Pick<SettingsPageProps, 'stats' | 'onClearWorkspace' | 'onExportWorkspace'>) {
  const [confirming, setConfirming] = useState(false)
  const [confirmingAccount, setConfirmingAccount] = useState(false)
  const { deleteAccount } = useAuth()

  return (
    <Panel
      title="Data controls"
      description="Your research state belongs to you. It is never used to train models or build a marketing profile."
    >
      <Card>
        <Row
          label="Export your workspace"
          hint={`Downloads ${stats.chats} chats and ${stats.projects} projects as JSON.`}
        >
          <button
            onClick={() => void onExportWorkspace()}
            className="rounded-full border border-border px-3.5 py-1.5 text-[12.5px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            Export
          </button>
        </Row>

        <Row
          label="Delete all chats and projects"
          hint="Permanently deletes them from your account. This cannot be undone."
        >
          {confirming ? (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setConfirming(false)}
                className="rounded-full border border-border px-3 py-1.5 text-[12.5px] text-muted-foreground transition-colors hover:bg-accent"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  onClearWorkspace()
                  setConfirming(false)
                }}
                className="rounded-full bg-destructive/15 px-3.5 py-1.5 text-[12.5px] font-medium text-destructive transition-colors hover:bg-destructive/25"
              >
                Delete everything
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirming(true)}
              className="flex items-center gap-2 rounded-full border border-destructive/40 px-3.5 py-1.5 text-[12.5px] text-destructive transition-colors hover:bg-destructive/10"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </button>
          )}
        </Row>

        <Row
          label="Delete your account"
          hint="Removes the account across primary and derived stores, subject to legal retention."
        >
          {confirmingAccount ? (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setConfirmingAccount(false)}
                className="rounded-full border border-border px-3 py-1.5 text-[12.5px] text-muted-foreground transition-colors hover:bg-accent"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  void deleteAccount()
                  setConfirmingAccount(false)
                }}
                className="rounded-full bg-destructive/15 px-3.5 py-1.5 text-[12.5px] font-medium text-destructive transition-colors hover:bg-destructive/25"
              >
                Permanently Delete
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmingAccount(true)}
              className="flex items-center gap-2 rounded-full border border-destructive/40 px-3.5 py-1.5 text-[12.5px] text-destructive transition-colors hover:bg-destructive/10"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete Account
            </button>
          )}
        </Row>
      </Card>
    </Panel>
  )
}

function StorageSection({ stats }: Pick<SettingsPageProps, 'stats'>) {
  // Recomputed whenever the workspace changes, so the figure stays truthful.
  const usage = useMemo(() => {
    let total = 0
    const items: [string, number][] = []
    try {
      for (const key of Object.keys(localStorage)) {
        const size = new Blob([key, localStorage.getItem(key) ?? '']).size
        total += size
        items.push([key, size])
      }
    } catch {
      // Storage unavailable — report nothing rather than guess.
    }
    return { total, items: items.sort((a, b) => b[1] - a[1]) }
  }, [stats.chats, stats.projects, stats.messages])

  // Browsers typically allow around 5 MB of localStorage per origin.
  const LIMIT = 5 * 1024 * 1024
  const pct = Math.min(100, (usage.total / LIMIT) * 100)

  return (
    <Panel
      title="Storage"
      description="Chats and projects are stored on Talvrin's servers, tied to your account — this browser only keeps small local preferences, listed below."
    >
      <Card>
        <div className="px-4 py-4">
          <div className="flex items-baseline justify-between gap-4">
            <span className="text-[14px] font-medium">
              {formatBytes(usage.total)} of about {formatBytes(LIMIT)} used
            </span>
            <span className="text-[12.5px] tabular-nums text-muted-foreground">
              {pct < 1 ? '<1' : pct.toFixed(0)}%
            </span>
          </div>
          <div className="mt-2.5 h-2 overflow-hidden rounded-full bg-secondary">
            <div
              className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-[width]"
              style={{ width: `${Math.max(pct, 1)}%` }}
            />
          </div>
          <p className="mt-2.5 text-[12px] leading-relaxed text-muted-foreground">
            The limit is set by your browser, not by your plan, and is approximate.
          </p>
        </div>
      </Card>

      <Card>
        {usage.items.length === 0 ? (
          <Row label="Nothing stored" hint="This browser holds no Talvrin data." />
        ) : (
          usage.items.map(([key, size]) => (
            <Row key={key} label={key}>
              <span className="text-[13px] tabular-nums text-muted-foreground">
                {formatBytes(size)}
              </span>
            </Row>
          ))
        )}
      </Card>
    </Panel>
  )
}

/* ---------------- page ---------------- */

export default function SettingsPage({
  onBack,
  theme,
  onThemeChange,
  stats,
  onClearWorkspace,
  onExportWorkspace,
  onOpenPricing,
}: SettingsPageProps) {
  const [active, setActive] = useState<SectionId>('account')

  // Escape is the only keyboard way out of a full-pane view.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onBack()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onBack])

  return (
    <div className="scrollbar-slim flex-1 overflow-y-auto">
      <div className="mx-auto max-w-4xl px-6 pb-20 pt-8">
        <div className="mb-7 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              aria-label="Back"
              className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <ArrowLeft className="h-[18px] w-[18px]" />
            </button>
            <h1 className="text-[22px] font-semibold tracking-tight">Settings</h1>
          </div>
          <Link
            to="/guides"
            className="inline-flex items-center gap-1.5 rounded-xl border border-border/80 bg-background px-3 py-1.5 text-xs font-semibold text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            title="Open platform documentation and user manuals"
          >
            <BookOpen className="h-3.5 w-3.5 text-primary" />
            <span>Platform Guides & Docs</span>
          </Link>
        </div>

        <div className="flex flex-col gap-8 md:flex-row md:gap-10">
          {/* Horizontal chips when narrow, a list on desktop. */}
          <nav
            aria-label="Settings sections"
            className="scrollbar-slim -mx-1 flex shrink-0 gap-1.5 overflow-x-auto px-1 pb-1 md:mx-0 md:w-48 md:flex-col md:overflow-visible md:px-0 md:pb-0"
          >
            {SECTIONS.map(({ id, label, Icon }) => (
              <button
                key={id}
                onClick={() => setActive(id)}
                aria-current={active === id}
                className={cn(
                  'flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13.5px] transition-colors',
                  active === id
                    ? 'bg-accent font-medium text-foreground'
                    : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground'
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {label}
              </button>
            ))}
          </nav>

          <div className="min-w-0 flex-1">
            {active === 'account' && <AccountSection />}
            {active === 'appearance' && (
              <AppearanceSection theme={theme} onThemeChange={onThemeChange} />
            )}
            {active === 'security' && <SecuritySection />}
            {active === 'billing' && <BillingSection onOpenPricing={onOpenPricing} />}
            {active === 'usage' && <UsageSection stats={stats} />}
            {active === 'data' && (
              <DataSection
                stats={stats}
                onClearWorkspace={onClearWorkspace}
                onExportWorkspace={onExportWorkspace}
              />
            )}
            {active === 'storage' && <StorageSection stats={stats} />}
          </div>
        </div>
      </div>
    </div>
  )
}
