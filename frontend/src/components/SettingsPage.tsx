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
  X,
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
  initialSection?: SectionId
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

const SETTING_SEARCH_INDEX: Record<SectionId, { keywords: string[] }> = {
  account: {
    keywords: [
      'name', 'display name', 'email', 'profile', 'user', 'sign out', 'logout',
      'plan', 'account', 'identity', 'username', 'edit name', 'device session',
      'who you are', 'credentials', 'switch account', 'exit session',
    ],
  },
  appearance: {
    keywords: [
      'theme', 'dark', 'light', 'system', 'display', 'preference', 'mode',
      'transparent', 'sidebar', 'appearance', 'look', 'style', 'color',
      'contrast', 'ui', 'interface', 'dark mode', 'light mode', 'system preference',
      'visuals', 'backdrop', 'blur', 'glassmorphism', 'layout',
    ],
  },
  security: {
    keywords: [
      'password', 'pass', 'security', '2fa', 'totp', 'two-factor', 'authentication',
      'auth', 'shield', 'protect', 'qr', 'qr code', 'authenticator', 'google authenticator',
      'authy', '1password', 'one-time code', 'otp', 'multi-factor', 'mfa',
      'verify', 'reset password', 'new password', 'current password', 'change password',
      'breach check', 'secret key',
    ],
  },
  billing: {
    keywords: [
      'billing', 'subscription', 'invoice', 'plan', 'upgrade', 'pricing', 'stripe',
      'payment', 'quotas', 'explorer', 'research', 'professional', 'teams',
      'enterprise', 'credit card', 'renewal', 'receipt', 'manage billing',
      'billing portal', 'tier', 'annual', 'monthly', 'compare plans', 'seats',
      'allowance', 'billing frequency', 'downgrade',
    ],
  },
  usage: {
    keywords: [
      'usage', 'quota', 'limits', 'metrics', 'watchlists', 'rules', 'alert rules',
      'runs', 'research runs', 'exports', 'chats', 'messages', 'consumption',
      'activity', 'allowance', 'dossier exports', 'historical queries', 'storage',
      'monitoring rules', 'remaining runs', 'usage overview', 'capacity',
    ],
  },
  data: {
    keywords: [
      'data', 'export', 'delete', 'download', 'backup', 'privacy', 'erase',
      'clear', 'account deletion', 'data controls', 'export workspace', 'json',
      'clear workspace', 'delete all chats', 'delete account', 'erase history',
      'gdpr', 'compliance', 'purge data', 'permanent delete',
    ],
  },
}

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

function BillingSection() {
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
  const watchlistsQuota = entitlement?.quotas.watchlists ?? 'unlimited'
  const watchlistsUsed = entitlement?.usage.watchlists_count ?? 0
  const rulesQuota = entitlement?.quotas.active_monitoring_rules ?? 125
  const rulesUsed = entitlement?.usage.active_rules_count ?? 0
  const researchQuota = entitlement?.quotas.verified_research_runs_per_month ?? 400
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
            <button
              type="button"
              onClick={() => {
                const el = document.getElementById('plans-comparison-matrix')
                if (el) el.scrollIntoView({ behavior: 'smooth' })
              }}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-border bg-secondary/50 px-3.5 py-2 text-xs font-medium text-foreground transition-colors hover:bg-secondary"
            >
              Compare Plans
            </button>

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
                      width: `${Math.min(100, (researchUsed / (typeof researchQuota === 'number' ? Math.max(1, researchQuota) : 400)) * 100)}%`,
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

      {/* 3. Change Plan Tier with Expanded Details & Comparative View */}
      <div id="plans-comparison-matrix">
      <Card>
        <div className="p-5 flex flex-col gap-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/60 pb-4">
            <div>
              <h3 className="text-base font-semibold text-foreground tracking-tight">
                Subscription Plans & Capacity Comparison
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Side-by-side comparative matrix of quotas, sovereign verification engine capabilities, and support SLAs.
              </p>
            </div>

          </div>

          {/* Cards Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3.5">
            {[
              {
                id: 'explorer' as api.PlanTier,
                name: 'Explorer',
                badge: 'Evaluate UX',
                price: '$0',
                cadence: '/mo',
                desc: 'Evaluate evidence UX and sovereign verification at zero financial commitment.',
                limits: [
                  '2 saved watchlists',
                  '3 monitoring rules',
                  '10 verified runs / mo',
                  '2 brief exports / mo',
                ],
                features: [
                  '1 individual user seat',
                  'Personal workspace only',
                  'Evidence replay manifest view',
                  'Self-help support',
                ],
              },
              {
                id: 'research' as api.PlanTier,
                name: 'Research',
                badge: 'Individual Research',
                price: '$29',
                cadence: '/mo',
                desc: 'Regular individual research with expanded monitoring and evidence packs.',
                limits: [
                  '10 saved watchlists',
                  '25 monitoring rules',
                  '100 verified runs / mo',
                  '25 dossier exports / mo',
                ],
                features: [
                  '1 named user seat',
                  'Personal workspace only',
                  'View + standard replay',
                  'Standard support',
                ],
              },
              {
                id: 'professional' as api.PlanTier,
                name: 'Professional',
                badge: 'High Intensity',
                price: '$79',
                cadence: '/mo',
                desc: 'High-intensity institutional research, priority queue, and enhanced exports.',
                popular: true,
                limits: [
                  'Unlimited watchlists',
                  '125 monitoring rules',
                  '400 verified runs / mo',
                  '125 dossier exports / mo',
                ],
                features: [
                  '1 named user seat',
                  'Enhanced replay export',
                  'Priority execution queue',
                  'Priority support queue',
                ],
              },
              {
                id: 'teams' as api.PlanTier,
                name: 'Teams',
                badge: 'Small Teams',
                price: '$249',
                cadence: '/mo',
                desc: 'Collaborative team pods with pooled quotas, shared roles, and business SLA.',
                limits: [
                  'Unlimited pooled watchlists',
                  '400 active rules pooled',
                  '1,200 verified runs / mo',
                  '350 dossier exports / mo',
                ],
                features: [
                  '3 named users included',
                  'Shared team + roles',
                  'Org-scoped replay archive',
                  'Business-hours priority',
                ],
              },
              {
                id: 'enterprise' as api.PlanTier,
                name: 'Enterprise',
                badge: 'Institutional Orgs',
                price: 'Custom',
                cadence: 'quote',
                desc: 'Institutional organizations with contracted governance, SSO, and custom SLA.',
                limits: [
                  'Contracted watchlists',
                  'Contracted active rules',
                  'Committed / pooled runs',
                  'Contracted pack exports',
                ],
                features: [
                  'Multi-team + policy',
                  'Contracted retention',
                  'SSO / SCIM optional SKU',
                  'Contracted SLA',
                ],
              },
            ].map((tier) => {
              const isCurrent = activePlanTier === tier.id
              const isUpdating = updatingTier === tier.id
              return (
                <div
                  key={tier.id}
                  className={cn(
                    'relative rounded-2xl border p-5 flex flex-col justify-between gap-4 transition-all duration-200',
                    isCurrent
                      ? 'border-emerald-500/50 bg-emerald-500/[0.03] ring-1 ring-emerald-500/30 shadow-sm'
                      : tier.popular
                      ? 'border-primary/50 bg-primary/[0.02] ring-1 ring-primary/20 shadow-sm'
                      : 'border-border/80 bg-card hover:border-border hover:bg-accent/20'
                  )}
                >
                  {/* Top Popular or Current Pill */}
                  {tier.popular && !isCurrent && (
                    <div className="absolute -top-2.5 left-1/2 -translate-x-1/2 rounded-full bg-primary px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-primary-foreground shadow-sm">
                      Most Popular
                    </div>
                  )}

                  <div className="space-y-3">
                    {/* Header: Name + Badge */}
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h4 className="text-base font-bold text-foreground">{tier.name}</h4>
                        <span className="text-[11px] font-medium text-muted-foreground">{tier.badge}</span>
                      </div>
                      {isCurrent && (
                        <span className="rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-bold text-emerald-400">
                          CURRENT
                        </span>
                      )}
                    </div>

                    {/* Price */}
                    <div className="flex items-baseline gap-1 border-b border-border/50 pb-3">
                      <span className="text-2xl font-extrabold text-foreground tracking-tight font-mono">
                        {tier.price}
                      </span>
                      <span className="text-xs text-muted-foreground">{tier.cadence}</span>
                    </div>

                    <p className="text-xs text-muted-foreground leading-relaxed min-h-[36px]">
                      {tier.desc}
                    </p>

                    {/* Capacity Limits Pill Box */}
                    <div className="rounded-xl border border-border/60 bg-muted/20 p-2.5 space-y-1.5 text-[11px]">
                      <div className="font-semibold text-muted-foreground text-[10px] uppercase tracking-wider mb-1">
                        Capacity Limits
                      </div>
                      {tier.limits.map((l, i) => (
                        <div key={i} className="flex items-center gap-1.5 text-foreground">
                          <Check className="h-3 w-3 text-primary shrink-0" />
                          <span>{l}</span>
                        </div>
                      ))}
                    </div>

                    {/* Included Features */}
                    <div className="space-y-1.5 pt-1">
                      <div className="font-semibold text-muted-foreground text-[10px] uppercase tracking-wider mb-1">
                        Key Features
                      </div>
                      {tier.features.map((f, i) => (
                        <div key={i} className="flex items-start gap-1.5 text-xs text-muted-foreground">
                          <Check className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" />
                          <span className="leading-tight">{f}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* CTA Switch Button */}
                  <div className="pt-3 border-t border-border/50">
                    <button
                      type="button"
                      disabled={isCurrent || isUpdating}
                      onClick={() => void handleDirectPlanSwitch(tier.id)}
                      className={cn(
                        'w-full rounded-xl py-2 px-3 text-xs font-semibold transition-all flex items-center justify-center gap-1.5',
                        isCurrent
                          ? 'bg-emerald-500/10 border border-emerald-500/25 text-emerald-400 cursor-default font-medium'
                          : tier.popular
                          ? 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm'
                          : 'border border-border/80 bg-background text-foreground hover:bg-accent'
                      )}
                    >
                      {isUpdating ? (
                        <>
                          <RefreshCw className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
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
                </div>
              )
            })}
          </div>

          {/* Comparative Matrix Table matching Table 11 of Talvrin Commercial Architecture */}
          <div className="mt-4 pt-4 border-t border-border/60">
            <h4 className="text-sm font-semibold text-foreground mb-3">
              Official Entitlements & Capacity Matrix
            </h4>
            <div className="overflow-x-auto rounded-xl border border-border/70 scrollbar-slim">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-border/70 bg-muted/40">
                    <th className="p-3.5 font-semibold text-muted-foreground min-w-[200px]">
                      Entitlement / month
                    </th>
                    <th className="p-3.5 font-semibold text-foreground text-center min-w-[120px]">
                      Explorer ($0)
                    </th>
                    <th className="p-3.5 font-semibold text-foreground text-center min-w-[120px]">
                      Research ($29)
                    </th>
                    <th className="p-3.5 font-semibold text-primary text-center min-w-[130px] bg-primary/5">
                      Professional ($79)
                    </th>
                    <th className="p-3.5 font-semibold text-indigo-400 text-center min-w-[130px]">
                      Teams ($249)
                    </th>
                    <th className="p-3.5 font-semibold text-slate-300 text-center min-w-[120px]">
                      Enterprise
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50 bg-background/50">
                  <tr>
                    <td className="p-3.5 font-medium text-foreground">Saved watchlists</td>
                    <td className="p-3.5 text-center text-muted-foreground">2</td>
                    <td className="p-3.5 text-center text-muted-foreground">10</td>
                    <td className="p-3.5 text-center font-semibold text-primary bg-primary/5">Unlimited</td>
                    <td className="p-3.5 text-center text-indigo-400 font-semibold">Unlimited (pooled)</td>
                    <td className="p-3.5 text-center text-slate-300">Contracted</td>
                  </tr>
                  <tr>
                    <td className="p-3.5 font-medium text-foreground">Active monitoring rules</td>
                    <td className="p-3.5 text-center text-muted-foreground">3</td>
                    <td className="p-3.5 text-center text-muted-foreground">25</td>
                    <td className="p-3.5 text-center font-semibold text-primary bg-primary/5">125</td>
                    <td className="p-3.5 text-center text-indigo-400 font-semibold">400 pooled</td>
                    <td className="p-3.5 text-center text-slate-300">Contracted</td>
                  </tr>
                  <tr>
                    <td className="p-3.5 font-medium text-foreground">Verified research runs</td>
                    <td className="p-3.5 text-center text-muted-foreground">10</td>
                    <td className="p-3.5 text-center text-muted-foreground">100</td>
                    <td className="p-3.5 text-center font-semibold text-primary bg-primary/5">400</td>
                    <td className="p-3.5 text-center text-indigo-400 font-semibold">1,200 pooled</td>
                    <td className="p-3.5 text-center text-slate-300">Committed / pooled</td>
                  </tr>
                  <tr>
                    <td className="p-3.5 font-medium text-foreground">Evidence-pack exports</td>
                    <td className="p-3.5 text-center text-muted-foreground">2</td>
                    <td className="p-3.5 text-center text-muted-foreground">25</td>
                    <td className="p-3.5 text-center font-semibold text-primary bg-primary/5">125</td>
                    <td className="p-3.5 text-center text-indigo-400 font-semibold">350 pooled</td>
                    <td className="p-3.5 text-center text-slate-300">Contracted</td>
                  </tr>
                  <tr>
                    <td className="p-3.5 font-medium text-foreground">Workspaces / collaboration</td>
                    <td className="p-3.5 text-center text-muted-foreground">Personal only</td>
                    <td className="p-3.5 text-center text-muted-foreground">Personal only</td>
                    <td className="p-3.5 text-center text-primary bg-primary/5">Personal only</td>
                    <td className="p-3.5 text-center text-indigo-400 font-semibold">Shared team + roles</td>
                    <td className="p-3.5 text-center text-slate-300">Multi-team + policy</td>
                  </tr>
                  <tr>
                    <td className="p-3.5 font-medium text-foreground">Evidence replay manifest</td>
                    <td className="p-3.5 text-center text-muted-foreground">View permitted</td>
                    <td className="p-3.5 text-center text-muted-foreground">View + standard</td>
                    <td className="p-3.5 text-center font-semibold text-primary bg-primary/5">Enhanced export</td>
                    <td className="p-3.5 text-center text-indigo-400 font-semibold">Org-scoped archive</td>
                    <td className="p-3.5 text-center text-slate-300">Contracted retention</td>
                  </tr>
                  <tr>
                    <td className="p-3.5 font-medium text-foreground">SSO / SCIM</td>
                    <td className="p-3.5 text-center text-muted-foreground">—</td>
                    <td className="p-3.5 text-center text-muted-foreground">—</td>
                    <td className="p-3.5 text-center text-muted-foreground bg-primary/5">—</td>
                    <td className="p-3.5 text-center text-indigo-400">Optional contract</td>
                    <td className="p-3.5 text-center text-slate-300">Optional standard SKU</td>
                  </tr>
                  <tr>
                    <td className="p-3.5 font-medium text-foreground">Product API</td>
                    <td className="p-3.5 text-center text-muted-foreground">—</td>
                    <td className="p-3.5 text-center text-muted-foreground">—</td>
                    <td className="p-3.5 text-center text-muted-foreground bg-primary/5">—</td>
                    <td className="p-3.5 text-center text-indigo-400">Quote and rights gate</td>
                    <td className="p-3.5 text-center text-slate-300">Contracted + rights gate</td>
                  </tr>
                  <tr>
                    <td className="p-3.5 font-medium text-foreground">Support</td>
                    <td className="p-3.5 text-center text-muted-foreground">Self-help</td>
                    <td className="p-3.5 text-center text-muted-foreground">Standard</td>
                    <td className="p-3.5 text-center font-semibold text-primary bg-primary/5">Priority queue</td>
                    <td className="p-3.5 text-center font-semibold text-indigo-400">Business-hours priority</td>
                    <td className="p-3.5 text-center text-slate-300">Contracted SLA</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </Card>
      </div>
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
  initialSection,
}: SettingsPageProps) {
  const [active, setActive] = useState<SectionId>(initialSection || 'appearance')
  const [searchQuery, setSearchQuery] = useState('')

  // Automatically navigate/highlight section when search query matches
  useEffect(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return

    for (const [secId, def] of Object.entries(SETTING_SEARCH_INDEX) as [SectionId, { keywords: string[] }][]) {
      const match = def.keywords.some((k) => k.toLowerCase().includes(q) || q.includes(k.toLowerCase()))
      if (match) {
        setActive(secId)
        break
      }
    }
  }, [searchQuery])

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
                placeholder="Search settings..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-xl border border-border/80 bg-background pl-9 pr-8 py-1.5 text-[13.5px] text-foreground placeholder:text-muted-foreground outline-none transition-all focus:border-primary/60 focus:ring-1 focus:ring-primary/40 shadow-sm"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  aria-label="Clear search"
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
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
          {active === 'billing' && <BillingSection />}
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
