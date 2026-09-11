import { useEffect, useMemo, useState } from 'react'
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
  Shield,
  Sun,
  Trash2,
  User,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/auth/AuthContext'
import { Field, SubmitButton } from '@/components/ui/field'
import { PLANS, CURRENT_PLAN_ID } from '@/data/plans'
import { passwordProblem } from '@/auth/session'

interface SettingsPageProps {
  onBack: () => void
  theme: 'dark' | 'light'
  onThemeChange: (theme: 'dark' | 'light') => void
  stats: { chats: number; projects: number; messages: number }
  onClearWorkspace: () => void
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
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})

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
        form: 'No authentication backend is connected, so the password cannot be changed yet.',
      })
    }
  }

  return (
    <Panel
      title="Security"
      description="How your account is protected. Most of this arrives with the authentication backend."
    >
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

      <Card>
        <Row
          label="Two-factor authentication"
          hint="Passkeys are the preferred method, with an authenticator app as a fallback."
        >
          <NotYet>Not yet available</NotYet>
        </Row>
      </Card>
    </Panel>
  )
}

function BillingSection() {
  return (
    <Panel
      title="Billing"
      description="Plans are functional tiers. Pricing is not set, so none is shown here."
    >
      <div className="flex flex-col gap-2.5">
        {PLANS.map((p) => {
          const current = p.id === CURRENT_PLAN_ID
          return (
            <div
              key={p.id}
              className={cn(
                'rounded-xl border px-4 py-3.5',
                current ? 'border-primary/50 bg-primary/5' : 'border-border bg-card'
              )}
            >
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="text-[14px] font-medium">{p.name}</span>
                {current && (
                  <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[10.5px] font-semibold tracking-wide text-primary">
                    CURRENT
                  </span>
                )}
                {p.deferred && <NotYet>Deferred</NotYet>}
              </div>
              <p className="mt-1 text-[13px] text-muted-foreground">{p.role}</p>
              <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted-foreground/80">
                {p.gates}
              </p>
            </div>
          )
        })}
      </div>

      <Card>
        <Row
          label="Payment method"
          hint="No billing system is connected. Nothing can be charged."
        >
          <NotYet>Not yet available</NotYet>
        </Row>
        <Row label="Invoices" hint="Past invoices will appear here once billing is live.">
          <NotYet>Not yet available</NotYet>
        </Row>
      </Card>
    </Panel>
  )
}

function UsageSection({ stats }: Pick<SettingsPageProps, 'stats'>) {
  const tiles: [string, number][] = [
    ['Chats', stats.chats],
    ['Projects', stats.projects],
    ['Messages', stats.messages],
  ]
  return (
    <Panel
      title="Usage"
      description="What is in your workspace on this device. Server-side metering arrives with the backend."
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

      <Card>
        <Row
          label="Research requests this month"
          hint="Metered per plan once the API is connected."
        >
          <NotYet>Not yet available</NotYet>
        </Row>
        <Row label="Monitoring rules" hint="Alert capacity is a plan entitlement.">
          <NotYet>Not yet available</NotYet>
        </Row>
      </Card>
    </Panel>
  )
}

function DataSection({
  stats,
  onClearWorkspace,
}: Pick<SettingsPageProps, 'stats' | 'onClearWorkspace'>) {
  const [confirming, setConfirming] = useState(false)

  const exportWorkspace = () => {
    const payload = {
      exportedAt: new Date().toISOString(),
      workspace: JSON.parse(localStorage.getItem('talvrin-workspace') ?? 'null'),
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `talvrin-workspace-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

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
            onClick={exportWorkspace}
            className="rounded-full border border-border px-3.5 py-1.5 text-[12.5px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            Export
          </button>
        </Row>

        <Row
          label="Delete all chats and projects"
          hint="Removes everything from this device. This cannot be undone."
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
          <NotYet>Not yet available</NotYet>
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
      description="Talvrin currently keeps your workspace in this browser. Nothing is uploaded."
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
        <div className="mb-7 flex items-center gap-3">
          <button
            onClick={onBack}
            aria-label="Back"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <ArrowLeft className="h-[18px] w-[18px]" />
          </button>
          <h1 className="text-[22px] font-semibold tracking-tight">Settings</h1>
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
            {active === 'billing' && <BillingSection />}
            {active === 'usage' && <UsageSection stats={stats} />}
            {active === 'data' && (
              <DataSection stats={stats} onClearWorkspace={onClearWorkspace} />
            )}
            {active === 'storage' && <StorageSection stats={stats} />}
          </div>
        </div>
      </div>
    </div>
  )
}
