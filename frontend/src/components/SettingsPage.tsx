import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowLeft,
  Check,
  CreditCard,
  LogOut,
  Pencil,
  QrCode,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  BookOpen,
  ExternalLink,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Search,
  Layers,
  Radio,
  Activity,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/auth/AuthContext'
import * as api from '@/lib/api'
import { Field } from '@/components/ui/field'
import { passwordProblem } from '@/auth/session'
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
  { id: 'account', label: 'Account' },
  { id: 'appearance', label: 'Appearance' },
  { id: 'security', label: 'Security' },
  { id: 'billing', label: 'Billing' },
  { id: 'usage', label: 'Usage' },
  { id: 'data', label: 'Data controls' },
] as const

type SectionId = (typeof SECTIONS)[number]['id']

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
    <section className="animate-in fade-in duration-150">
      <div className="pb-5 pt-1">
        <h2 className="text-[18px] font-semibold tracking-tight text-foreground">{title}</h2>
        {description && (
          <p className="mt-1 text-[13.5px] leading-relaxed text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      <div className="divide-y divide-border/60 border-t border-border/70">{children}</div>
    </section>
  )
}

function Card({ children }: { children: React.ReactNode }) {
  return <div className="divide-y divide-border/60">{children}</div>
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
    <div className="grid grid-cols-1 gap-4 py-6 md:grid-cols-12 md:gap-8 items-start">
      <div className="md:col-span-4 lg:col-span-4 pr-2">
        <div className="text-[14px] font-medium text-foreground">{label}</div>
        {hint && (
          <p className="mt-1 text-[12.5px] leading-relaxed text-muted-foreground">
            {hint}
          </p>
        )}
      </div>
      <div className="md:col-span-8 lg:col-span-8 flex flex-wrap items-center gap-4">
        {children}
      </div>
    </div>
  )
}


/* ---------------- sections ---------------- */

function AccountSection({ onNavigateToBilling }: { onNavigateToBilling?: () => void }) {
  const { session, rename, signOut } = useAuth()
  const { entitlement } = useEntitlement()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(session?.name ?? '')

  const save = () => {
    if (draft.trim()) rename(draft)
    setEditing(false)
  }

  const currentPlan = (entitlement?.plan_tier || 'free').toUpperCase()

  return (
    <Panel title="Account" description="Who you are signed in as on this device.">
      <Card>
        <Row label="Display name" hint="Used for greeting and in-app display.">
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
          label="Email address"
          hint="Primary login email for this account."
        >
          <span className="text-[13.5px] font-mono text-muted-foreground">{session?.email}</span>
        </Row>

        <Row label="Plan" hint="See Billing for subscription details, invoices, and quotas.">
          <button
            type="button"
            onClick={onNavigateToBilling}
            className="group inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-[12px] font-semibold tracking-wide text-primary transition-all hover:bg-primary/20 hover:border-primary/40 focus:outline-none focus:ring-2 focus:ring-primary/40"
            title="Go to Billing & Subscription"
          >
            <span>{currentPlan}</span>
            <span className="text-[11px] font-normal text-primary/70 group-hover:text-primary group-hover:translate-x-0.5 transition-transform flex items-center gap-0.5">
              Manage &rarr;
            </span>
          </button>
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
  const [transparentSidebar, setTransparentSidebar] = useState(() => {
    return localStorage.getItem('talvrin-transparent-sidebar') === 'true'
  })

  const toggleTransparentSidebar = () => {
    const next = !transparentSidebar
    setTransparentSidebar(next)
    try {
      localStorage.setItem('talvrin-transparent-sidebar', String(next))
    } catch {
      // private mode
    }
    document.body.classList.toggle('sidebar-transparent', next)
  }

  useEffect(() => {
    document.body.classList.toggle('sidebar-transparent', transparentSidebar)
  }, [transparentSidebar])

  return (
    <Panel
      title="Appearance"
      description="Change how your dashboard looks and feels."
    >
      {/* 1. Display preference */}
      <Row
        label="Display preference"
        hint="Switch between light and dark modes."
      >
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 w-full max-w-2xl">
          {/* Card 1: System preference (Split Light / Dark) */}
          <button
            type="button"
            onClick={() => onThemeChange('dark')}
            className={cn(
              'group relative flex flex-col items-center rounded-xl border p-2.5 text-left transition-all hover:border-primary/60 focus:outline-none',
              theme === 'dark'
                ? 'border-primary ring-2 ring-primary/20 bg-primary/[0.02]'
                : 'border-border/70 bg-card hover:bg-accent/30'
            )}
          >
            <div className="relative h-28 w-full overflow-hidden rounded-lg border border-border/80 bg-white shadow-sm flex">
              {/* Left half: Light UI mockup */}
              <div className="w-1/2 p-2 border-r border-slate-200 bg-slate-50 flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-1 mb-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
                    <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  </div>
                  <div className="space-y-1">
                    <div className="h-1.5 w-10 rounded bg-slate-300" />
                    <div className="h-1.5 w-14 rounded bg-primary/40" />
                  </div>
                </div>
                {/* Mini chart line */}
                <div className="h-6 w-full flex items-end">
                  <div className="h-3 w-full border-b-2 border-primary/60" />
                </div>
              </div>

              {/* Right half: Dark UI mockup */}
              <div className="w-1/2 p-2 bg-[#121417] flex flex-col justify-between">
                <div>
                  <div className="flex justify-end gap-1 mb-2">
                    <span className="h-1.5 w-4 rounded bg-primary/70" />
                  </div>
                  <div className="space-y-1">
                    <div className="h-1.5 w-10 rounded bg-slate-700" />
                    <div className="h-1.5 w-12 rounded bg-slate-800" />
                  </div>
                </div>
                {/* Mini dark chart line */}
                <div className="h-6 w-full flex items-end">
                  <div className="h-4 w-full border-b-2 border-indigo-400" />
                </div>
              </div>

              {/* Radio selection indicator pill inside mockup preview */}
              <div className="absolute bottom-2 left-2 flex h-5 w-5 items-center justify-center rounded-full border-2 border-primary bg-background">
                <span className="h-2 w-2 rounded-full bg-primary" />
              </div>
            </div>
            <div className="mt-2.5 w-full text-center">
              <span className="text-[13px] font-medium text-foreground">System preference</span>
            </div>
          </button>

          {/* Card 2: Light mode */}
          <button
            type="button"
            onClick={() => onThemeChange('light')}
            className={cn(
              'group relative flex flex-col items-center rounded-xl border p-2.5 text-left transition-all hover:border-primary/60 focus:outline-none',
              theme === 'light'
                ? 'border-primary ring-2 ring-primary/20 bg-primary/[0.02]'
                : 'border-border/70 bg-card hover:bg-accent/30'
            )}
          >
            <div className="relative h-28 w-full overflow-hidden rounded-lg border border-slate-200 bg-white p-2.5 shadow-sm flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
                    <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  </div>
                  <div className="h-2 w-5 rounded bg-primary/40" />
                </div>
                <div className="space-y-1">
                  <div className="h-1.5 w-12 rounded bg-slate-300" />
                  <div className="h-1.5 w-8 rounded bg-primary/60" />
                </div>
              </div>
              {/* Mini wave chart in light mode */}
              <div className="h-8 w-full flex items-end">
                <svg className="w-full h-8 text-primary/40" viewBox="0 0 100 30" fill="none" preserveAspectRatio="none">
                  <path d="M0,25 Q25,20 50,15 T100,5" stroke="currentColor" strokeWidth="2" fill="none" />
                </svg>
              </div>

              {theme === 'light' && (
                <div className="absolute bottom-2 left-2 flex h-5 w-5 items-center justify-center rounded-full border-2 border-primary bg-background">
                  <span className="h-2 w-2 rounded-full bg-primary" />
                </div>
              )}
            </div>
            <div className="mt-2.5 w-full text-center">
              <span className="text-[13px] font-medium text-foreground">Light mode</span>
            </div>
          </button>

          {/* Card 3: Dark mode */}
          <button
            type="button"
            onClick={() => onThemeChange('dark')}
            className={cn(
              'group relative flex flex-col items-center rounded-xl border p-2.5 text-left transition-all hover:border-primary/60 focus:outline-none',
              theme === 'dark'
                ? 'border-primary ring-2 ring-primary/20 bg-primary/[0.02]'
                : 'border-border/70 bg-card hover:bg-accent/30'
            )}
          >
            <div className="relative h-28 w-full overflow-hidden rounded-lg border border-slate-800 bg-[#0F1117] p-2.5 shadow-sm flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-slate-600" />
                    <span className="h-1.5 w-1.5 rounded-full bg-slate-600" />
                    <span className="h-1.5 w-1.5 rounded-full bg-slate-600" />
                  </div>
                  <div className="h-2 w-5 rounded bg-indigo-500/50" />
                </div>
                <div className="space-y-1">
                  <div className="h-1.5 w-12 rounded bg-slate-700" />
                  <div className="h-1.5 w-8 rounded bg-indigo-400" />
                </div>
              </div>
              {/* Mini wave chart in dark mode */}
              <div className="h-8 w-full flex items-end">
                <svg className="w-full h-8 text-indigo-400" viewBox="0 0 100 30" fill="none" preserveAspectRatio="none">
                  <path d="M0,25 Q25,20 50,15 T100,5" stroke="currentColor" strokeWidth="2" fill="none" />
                </svg>
              </div>

              {theme === 'dark' && (
                <div className="absolute bottom-2 left-2 flex h-5 w-5 items-center justify-center rounded-full border-2 border-primary bg-background">
                  <span className="h-2 w-2 rounded-full bg-primary" />
                </div>
              )}
            </div>
            <div className="mt-2.5 w-full text-center">
              <span className="text-[13px] font-medium text-foreground">Dark mode</span>
            </div>
          </button>
        </div>
      </Row>

      {/* 2. Transparent sidebar */}
      <Row
        label="Transparent sidebar"
        hint="Make the sidebar transparent."
      >
        <button
          type="button"
          role="switch"
          aria-checked={transparentSidebar}
          onClick={toggleTransparentSidebar}
          className={cn(
            'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2',
            transparentSidebar ? 'bg-primary' : 'bg-secondary'
          )}
        >
          <span
            className={cn(
              'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out',
              transparentSidebar ? 'translate-x-5' : 'translate-x-0'
            )}
          />
        </button>
      </Row>
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

          <div className="pt-2 flex justify-start">
            <button
              type="submit"
              className="inline-flex h-10 items-center justify-center rounded-xl bg-primary px-5 text-[13.5px] font-semibold text-primary-foreground shadow-sm transition-all hover:bg-primary/90 hover:shadow active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            >
              Update password
            </button>
          </div>
        </form>
      </Card>
    </Panel>
  )
}

function BillingSection({ onOpenPricing }: { onOpenPricing?: () => void }) {
  const { entitlement, refreshEntitlement, loading: entitlementLoading } = useEntitlement()
  const [portalLoading, setPortalLoading] = useState(false)
  const [updatingTier, setUpdatingTier] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const activePlanTier = entitlement?.plan_tier || 'professional'
  const activePlanName = formatPlanTier(activePlanTier)
  const isAnnual = entitlement?.billing_cadence === 'annual'
  const renewalDate = entitlement?.current_period_end
    ? new Date(entitlement.current_period_end).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    : 'Active'

  // Live Quotas & Usage straight from backend database counts
  const watchlistsQuota = entitlement?.quotas.watchlists ?? 50
  const watchlistsUsed = entitlement?.usage.watchlists_count ?? 0
  const rulesQuota = entitlement?.quotas.active_monitoring_rules ?? 125
  const rulesUsed = entitlement?.usage.active_rules_count ?? 0
  const researchQuota = entitlement?.quotas.verified_research_runs_per_month ?? 500
  const researchUsed = entitlement?.usage.research_runs_this_month ?? 0
  const exportsQuota = entitlement?.quotas.evidence_dossier_exports_per_month ?? 125
  const exportsUsed = entitlement?.usage.evidence_exports_this_month ?? 0

  const handleOpenStripePortal = async () => {
    if (!entitlement?.stripe_configured) {
      setErrorMessage(
        'Stripe API keys are not yet configured in backend/.env. To open a live Stripe Billing Portal, set STRIPE_SECRET_KEY=sk_test_... in backend/.env.'
      )
      return
    }
    try {
      setPortalLoading(true)
      setErrorMessage(null)
      const res = await api.getBillingPortalSession()
      if (res?.portal_url && res.portal_url.startsWith('http')) {
        await refreshEntitlement()
        window.open(res.portal_url, '_blank')
        return
      }
      setErrorMessage('Unable to initialize customer portal session')
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Unable to connect to Stripe Billing Portal')
    } finally {
      setPortalLoading(false)
    }
  }

  const handleDirectPlanSwitch = async (targetTier: api.PlanTier) => {
    if (targetTier === activePlanTier) return
    try {
      setUpdatingTier(targetTier)
      setErrorMessage(null)
      await api.updateAccountPlan({
        plan_tier: targetTier,
        billing_cadence: entitlement?.billing_cadence || 'annual',
      })
      await refreshEntitlement()
      setSuccessMessage(`Account plan successfully updated to ${formatPlanTier(targetTier)} Tier.`)
      setTimeout(() => setSuccessMessage(null), 4000)
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to update account tier')
    } finally {
      setUpdatingTier(null)
    }
  }

  return (
    <Panel
      title="Billing & Subscription"
      description="Manage your subscription plan, usage quotas, and payment details."
    >
      {/* Alert Notifications */}
      {errorMessage && (
        <div className="flex items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-xs text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span className="flex-1 font-medium">{errorMessage}</span>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            className="text-destructive font-semibold hover:underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {successMessage && (
        <div className="flex items-center gap-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-xs text-emerald-400">
          <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
          <span className="flex-1 font-medium">{successMessage}</span>
        </div>
      )}

      {/* 1. Subscription Overview */}
      <Card>
        <div className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <span className="text-lg font-semibold tracking-tight text-foreground">
                {activePlanName} Plan
              </span>
              <span className="rounded-full bg-secondary border border-border px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                {isAnnual ? 'Annual' : 'Monthly'}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              Renews on <strong className="font-medium text-foreground">{renewalDate}</strong>
            </p>
          </div>

          <div className="flex items-center gap-2">
            {onOpenPricing && (
              <button
                type="button"
                onClick={onOpenPricing}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-border bg-secondary/50 px-3.5 py-2 text-xs font-medium text-foreground transition-colors hover:bg-secondary"
              >
                Compare Plans
              </button>
            )}

            <button
              type="button"
              onClick={handleOpenStripePortal}
              disabled={portalLoading}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-primary px-3.5 py-2 text-xs font-medium text-primary-foreground transition-all hover:bg-primary/90 shadow-sm disabled:opacity-50"
            >
              {portalLoading ? (
                <>
                  <RefreshCw className="h-3.5 w-3.5 animate-spin text-primary-foreground" />
                  <span>Opening...</span>
                </>
              ) : (
                <>
                  <CreditCard className="h-3.5 w-3.5" />
                  <span>Manage Billing & Invoices</span>
                  <ExternalLink className="h-3 w-3 opacity-70 ml-0.5" />
                </>
              )}
            </button>
          </div>
        </div>
      </Card>

      {/* 2. Real Quotas & Usage */}
      <Card>
        <div className="p-5 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-medium text-foreground">
                Plan Quotas & Usage
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Current usage tracked against your active subscription limits.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void refreshEntitlement()}
              disabled={entitlementLoading}
              title="Refresh usage"
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors p-1 rounded"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', entitlementLoading && 'animate-spin')} />
              <span>Refresh</span>
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* Watchlists */}
            <div className="rounded-lg border border-border bg-secondary/30 p-3.5 flex flex-col justify-between gap-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <div className="h-6 w-6 rounded bg-primary/10 grid place-items-center text-primary">
                    <Layers className="h-3.5 w-3.5" />
                  </div>
                  <span className="text-xs font-medium text-foreground">Watchlists</span>
                </div>
                <div className="text-right whitespace-nowrap shrink-0">
                  <span className="text-sm font-semibold text-foreground font-mono">{watchlistsUsed}</span>
                  <span className="text-xs text-muted-foreground font-mono ml-1">
                    / {typeof watchlistsQuota === 'number' ? watchlistsQuota : '∞'}
                  </span>
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
                  <div
                    className="h-full rounded-full bg-primary transition-all duration-300"
                    style={{
                      width: `${Math.min(100, (watchlistsUsed / (typeof watchlistsQuota === 'number' ? Math.max(1, watchlistsQuota) : 100)) * 100)}%`,
                    }}
                  />
                </div>
                <span className="text-[11px] text-muted-foreground block">
                  {typeof watchlistsQuota === 'number'
                    ? `${Math.max(0, watchlistsQuota - watchlistsUsed)} remaining`
                    : 'Unlimited'}
                </span>
              </div>
            </div>

            {/* Alert Rules */}
            <div className="rounded-lg border border-border bg-secondary/30 p-3.5 flex flex-col justify-between gap-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <div className="h-6 w-6 rounded bg-rose-500/10 grid place-items-center text-rose-400">
                    <Radio className="h-3.5 w-3.5" />
                  </div>
                  <span className="text-xs font-medium text-foreground">Alert Rules</span>
                </div>
                <div className="text-right whitespace-nowrap shrink-0">
                  <span className="text-sm font-semibold text-foreground font-mono">{rulesUsed}</span>
                  <span className="text-xs text-muted-foreground font-mono ml-1">
                    / {typeof rulesQuota === 'number' ? rulesQuota : '∞'}
                  </span>
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
                  <div
                    className="h-full rounded-full bg-rose-500 transition-all duration-300"
                    style={{
                      width: `${Math.min(100, (rulesUsed / (typeof rulesQuota === 'number' ? Math.max(1, rulesQuota) : 125)) * 100)}%`,
                    }}
                  />
                </div>
                <span className="text-[11px] text-muted-foreground block">
                  {typeof rulesQuota === 'number'
                    ? `${Math.max(0, rulesQuota - rulesUsed)} remaining`
                    : 'Unlimited'}
                </span>
              </div>
            </div>

            {/* Research Runs */}
            <div className="rounded-lg border border-border bg-secondary/30 p-3.5 flex flex-col justify-between gap-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <div className="h-6 w-6 rounded bg-purple-500/10 grid place-items-center text-purple-400">
                    <Activity className="h-3.5 w-3.5" />
                  </div>
                  <span className="text-xs font-medium text-foreground">Research Runs</span>
                </div>
                <div className="text-right whitespace-nowrap shrink-0">
                  <span className="text-sm font-semibold text-foreground font-mono">{researchUsed}</span>
                  <span className="text-xs text-muted-foreground font-mono ml-1">
                    / {typeof researchQuota === 'number' ? researchQuota : '∞'}
                  </span>
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
                  <div
                    className="h-full rounded-full bg-purple-500 transition-all duration-300"
                    style={{
                      width: `${Math.min(100, (researchUsed / (typeof researchQuota === 'number' ? Math.max(1, researchQuota) : 500)) * 100)}%`,
                    }}
                  />
                </div>
                <span className="text-[11px] text-muted-foreground block">
                  {typeof researchQuota === 'number'
                    ? `${Math.max(0, researchQuota - researchUsed)} remaining this month`
                    : 'Unlimited'}
                </span>
              </div>
            </div>

            {/* Dossier Exports */}
            <div className="rounded-lg border border-border bg-secondary/30 p-3.5 flex flex-col justify-between gap-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <div className="h-6 w-6 rounded bg-emerald-500/10 grid place-items-center text-emerald-400">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                  </div>
                  <span className="text-xs font-medium text-foreground">Exports</span>
                </div>
                <div className="text-right whitespace-nowrap shrink-0">
                  <span className="text-sm font-semibold text-foreground font-mono">{exportsUsed}</span>
                  <span className="text-xs text-muted-foreground font-mono ml-1">
                    / {typeof exportsQuota === 'number' ? exportsQuota : '∞'}
                  </span>
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
                  <div
                    className="h-full rounded-full bg-emerald-500 transition-all duration-300"
                    style={{
                      width: `${Math.min(100, (exportsUsed / (typeof exportsQuota === 'number' ? Math.max(1, exportsQuota) : 125)) * 100)}%`,
                    }}
                  />
                </div>
                <span className="text-[11px] text-muted-foreground block">
                  {typeof exportsQuota === 'number'
                    ? `${Math.max(0, exportsQuota - exportsUsed)} remaining this month`
                    : 'Unlimited'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* 3. Change Plan Tier */}
      <Card>
        <div className="p-5 flex flex-col gap-4">
          <div>
            <h3 className="text-sm font-medium text-foreground">
              Change Plan
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Switch your plan tier to update quotas and features.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              {
                id: 'explorer' as api.PlanTier,
                name: 'Explorer',
                price: '$0',
                cadence: '/mo',
                desc: 'Basic search and up to 2 watchlists.',
              },
              {
                id: 'research' as api.PlanTier,
                name: 'Research',
                price: '$29',
                cadence: '/mo',
                desc: '10 watchlists, 25 alert rules, 100 runs.',
              },
              {
                id: 'professional' as api.PlanTier,
                name: 'Professional',
                price: '$79',
                cadence: '/mo',
                desc: 'Unlimited watchlists, 125 alert rules.',
              },
              {
                id: 'teams' as api.PlanTier,
                name: 'Teams',
                price: '$249',
                cadence: '/mo',
                desc: 'Multi-seat access and 400 alert rules.',
              },
            ].map((tier) => {
              const isCurrent = activePlanTier === tier.id
              const isUpdating = updatingTier === tier.id
              return (
                <div
                  key={tier.id}
                  className={cn(
                    'rounded-lg border p-4 flex flex-col justify-between gap-3 transition-colors',
                    isCurrent
                      ? 'border-primary/50 bg-primary/[0.04]'
                      : 'border-border bg-secondary/20 hover:bg-secondary/40'
                  )}
                >
                  <div className="space-y-1.5">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-xs font-semibold text-foreground">{tier.name}</span>
                      <div className="flex items-baseline gap-0.5">
                        <span className="text-sm font-bold text-foreground font-mono">{tier.price}</span>
                        <span className="text-[11px] text-muted-foreground">{tier.cadence}</span>
                      </div>
                    </div>
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      {tier.desc}
                    </p>
                  </div>

                  <button
                    type="button"
                    disabled={isCurrent || isUpdating}
                    onClick={() => void handleDirectPlanSwitch(tier.id)}
                    className={cn(
                      'w-full rounded-md py-1.5 px-3 text-xs font-medium transition-colors flex items-center justify-center gap-1.5',
                      isCurrent
                        ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 cursor-default font-semibold'
                        : 'border border-border bg-secondary hover:bg-accent text-foreground'
                    )}
                  >
                    {isUpdating ? (
                      <>
                        <RefreshCw className="h-3 w-3 animate-spin text-muted-foreground" />
                        <span>Updating...</span>
                      </>
                    ) : isCurrent ? (
                      <>
                        <Check className="h-3.5 w-3.5 text-emerald-400" />
                        <span>Current Plan</span>
                      </>
                    ) : (
                      <span>Select {tier.name}</span>
                    )}
                  </button>
                </div>
              )
            })}
          </div>
        </div>
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
    ['Messages', stats.messages],
  ]

  return (
    <Panel
      title="Plan Quotas & Server Usage"
      description="Real-time capacity tracking against your institutional tier entitlements."
    >
      <div className="grid gap-2.5 sm:grid-cols-2">
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
          hint={`Downloads ${stats.chats} chats as JSON.`}
        >
          <button
            onClick={() => void onExportWorkspace()}
            className="rounded-full border border-border px-3.5 py-1.5 text-[12.5px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            Export
          </button>
        </Row>

        <Row
          label="Delete all chats"
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
  const [active, setActive] = useState<SectionId>('appearance')
  const [searchQuery, setSearchQuery] = useState('')

  // Escape is the only keyboard way out of a full-pane view.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onBack()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onBack])

  return (
    <div className="scrollbar-slim flex-1 overflow-y-auto">
      <div className="mx-auto max-w-6xl px-6 pb-24 pt-8">
        {/* Top Header: Title and Search on the right */}
        <div className="mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              aria-label="Back"
              className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <ArrowLeft className="h-[18px] w-[18px]" />
            </button>
            <h1 className="text-[26px] font-semibold tracking-tight text-foreground">Settings</h1>
          </div>

          <div className="flex items-center gap-3">
            <div className="relative w-full sm:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-xl border border-border/80 bg-background pl-9 pr-3.5 py-1.5 text-[13.5px] text-foreground placeholder:text-muted-foreground outline-none transition-all focus:border-primary/60 focus:ring-1 focus:ring-primary/40 shadow-sm"
              />
            </div>
            <Link
              to="/guides"
              className="hidden lg:inline-flex items-center gap-1.5 rounded-xl border border-border/80 bg-background px-3 py-1.5 text-xs font-semibold text-muted-foreground hover:bg-accent hover:text-foreground transition-colors shadow-sm"
              title="Open platform documentation and user manuals"
            >
              <BookOpen className="h-3.5 w-3.5 text-primary" />
              <span>Guides</span>
            </Link>
          </div>
        </div>

        {/* Top Horizontal Pill Navigation Bar (Centered) */}
        <div className="mb-8 flex justify-center">
          <nav
            aria-label="Settings sections"
            className="scrollbar-slim flex items-center justify-center gap-1.5 overflow-x-auto rounded-2xl border border-border/80 bg-background/95 p-1.5 shadow-sm px-2 backdrop-blur-sm max-w-full"
          >
            {SECTIONS.map((sec) => {
              const isSelected = active === sec.id
              return (
                <button
                  key={sec.id}
                  onClick={() => setActive(sec.id)}
                  aria-current={isSelected}
                  className={cn(
                    'flex shrink-0 items-center justify-center gap-2 rounded-xl px-4 py-2 text-[13.5px] font-medium transition-all',
                    isSelected
                      ? 'bg-card text-foreground shadow-sm ring-1 ring-border/80 font-semibold'
                      : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground'
                  )}
                >
                  <span>{sec.label}</span>
                </button>
              )
            })}
          </nav>
        </div>

        {/* Settings Body */}
        <div className="w-full">
          {active === 'account' && (
            <AccountSection onNavigateToBilling={() => setActive('billing')} />
          )}
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
        </div>
      </div>
    </div>
  )
}
