import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Bell, ListChecks, Plus, TrendingDown, TrendingUp } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Field, SubmitButton } from '@/components/ui/field'
import {
  ApiError,
  type Alert,
  type CreateRuleInput,
  type Rule,
  type WatchableMetricId,
  WATCHABLE_METRICS,
  createRule,
  listAlerts,
  listRules,
} from '@/lib/api'

interface MonitoringPageProps {
  onBack: () => void
}

type Tab = 'rules' | 'alerts'

function errorMessageFor(err: unknown): string {
  if (err instanceof ApiError) return err.message
  return "Talvrin couldn't reach the backend. Please check your connection and try again."
}

function Panel({
  title,
  description,
  action,
  children,
}: {
  title: string
  description?: string
  action?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-[17px] font-semibold tracking-tight">{title}</h2>
          {description && (
            <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted-foreground">
              {description}
            </p>
          )}
        </div>
        {action}
      </div>
      <div className="mt-5 flex flex-col gap-4">{children}</div>
    </section>
  )
}

function Card({ children }: { children: React.ReactNode }) {
  return <div className="rounded-xl border border-border bg-card">{children}</div>
}

function EmptyState({ icon: Icon, text }: { icon: typeof Bell; text: string }) {
  return (
    <div className="flex flex-col items-center gap-3 py-14 text-center text-muted-foreground">
      <Icon className="h-8 w-8 opacity-50" />
      <p className="max-w-xs text-[13.5px] leading-relaxed">{text}</p>
    </div>
  )
}

const DIRECTION_LABEL: Record<string, string> = {
  CROSSES_ABOVE: 'rises above',
  CROSSES_BELOW: 'falls below',
}

function DirectionBadge({ predicate }: { predicate: string }) {
  const above = predicate === 'CROSSES_ABOVE'
  const Icon = above ? TrendingUp : TrendingDown
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11.5px] font-medium',
        above
          ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
          : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
      )}
    >
      <Icon className="h-3 w-3" />
      {DIRECTION_LABEL[predicate] ?? predicate}
    </span>
  )
}

const STATUS_STYLE: Record<string, string> = {
  ARMED: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  SUSPENDED: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  DEGRADED: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  NEW: 'bg-sky-500/10 text-sky-600 dark:text-sky-400',
  ACKNOWLEDGED: 'bg-secondary text-muted-foreground',
}

function StatusPill({ status }: { status: string }) {
  return (
    <span
      className={cn(
        'rounded-full px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide',
        STATUS_STYLE[status] ?? 'bg-secondary text-muted-foreground'
      )}
    >
      {status.toLowerCase()}
    </span>
  )
}

function metricLabel(metricId: string): string {
  return WATCHABLE_METRICS.find((m) => m.id === metricId)?.label ?? metricId
}

function RuleRow({ rule }: { rule: Rule }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-4 last:border-b-0">
      <div className="min-w-0">
        <div className="flex items-center gap-2 text-[14px] font-medium">
          {metricLabel(rule.metricId)}
        </div>
        <p className="mt-1 flex items-center gap-1.5 text-[12.5px] text-muted-foreground">
          Alerts when it <DirectionBadge predicate={rule.predicate} /> {rule.thresholdValue}
        </p>
      </div>
      <StatusPill status={rule.status} />
    </div>
  )
}

function AlertRow({ alert }: { alert: Alert }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-4 last:border-b-0">
      <div className="min-w-0">
        <div className="text-[14px] font-medium">{metricLabel(alert.metricId)}</div>
        <p className="mt-1 text-[12.5px] text-muted-foreground">
          Observed {alert.observedValue} against a threshold of {alert.thresholdValue} — as of{' '}
          {new Date(alert.knowledgeTime).toLocaleString()}
        </p>
      </div>
      <StatusPill status={alert.status} />
    </div>
  )
}

function NewRuleForm({
  onCreated,
  onCancel,
}: {
  onCreated: (rule: Rule) => void
  onCancel: () => void
}) {
  const [metricId, setMetricId] = useState<WatchableMetricId>(WATCHABLE_METRICS[0].id)
  const [predicate, setPredicate] = useState<'CROSSES_ABOVE' | 'CROSSES_BELOW'>('CROSSES_ABOVE')
  const [threshold, setThreshold] = useState('')
  const [tenor, setTenor] = useState('')
  const [isin, setIsin] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const metric = WATCHABLE_METRICS.find((m) => m.id === metricId)!

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!threshold.trim()) return
    setBusy(true)
    setError(null)
    try {
      const input: CreateRuleInput = {
        metricId,
        predicate,
        thresholdValue: threshold.trim(),
      }
      if (metric.needs === 'tenor') input.tenorYears = tenor.trim()
      if (metric.needs === 'isin') input.instrumentIsin = isin.trim().toUpperCase()
      const rule = await createRule(input)
      onCreated(rule)
    } catch (err) {
      setError(errorMessageFor(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <form onSubmit={submit} className="flex flex-col gap-4 p-4">
        <div>
          <label className="mb-2 block text-[13px] font-medium leading-none">Watch</label>
          <select
            value={metricId}
            onChange={(e) => setMetricId(e.target.value as WatchableMetricId)}
            className="h-11 w-full rounded-xl border border-border bg-background/50 px-3.5 text-[14px] outline-none focus:border-ring/80 focus:ring-[3px] focus:ring-ring/15"
          >
            {WATCHABLE_METRICS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </div>

        {metric.needs === 'tenor' && (
          <Field
            label="Tenor (years)"
            placeholder="10"
            inputMode="decimal"
            value={tenor}
            onChange={(e) => setTenor(e.target.value)}
            required
            hint="Which point on the curve, e.g. 10 for the 10-year point."
          />
        )}
        {metric.needs === 'isin' && (
          <Field
            label="Instrument ISIN"
            placeholder="GB0032452392"
            value={isin}
            onChange={(e) => setIsin(e.target.value)}
            required
            hint="Only instruments with a computed model-implied price can be watched this way."
          />
        )}

        <div>
          <label className="mb-2 block text-[13px] font-medium leading-none">Direction</label>
          <div className="flex gap-2">
            {(['CROSSES_ABOVE', 'CROSSES_BELOW'] as const).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPredicate(p)}
                className={cn(
                  'flex h-11 flex-1 items-center justify-center gap-1.5 rounded-xl border text-[13.5px] transition-colors',
                  predicate === p
                    ? 'border-ring/70 bg-accent text-foreground'
                    : 'border-border text-muted-foreground hover:bg-accent/60'
                )}
              >
                {p === 'CROSSES_ABOVE' ? (
                  <TrendingUp className="h-3.5 w-3.5" />
                ) : (
                  <TrendingDown className="h-3.5 w-3.5" />
                )}
                {DIRECTION_LABEL[p]}
              </button>
            ))}
          </div>
        </div>

        <Field
          label="Threshold"
          placeholder="4.50"
          inputMode="decimal"
          value={threshold}
          onChange={(e) => setThreshold(e.target.value)}
          required
        />

        {error && <p className="text-[12.5px] text-destructive">{error}</p>}

        <div className="flex gap-2 pt-1">
          <button
            type="button"
            onClick={onCancel}
            className="h-11 flex-1 rounded-xl border border-border text-[13.5px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            Cancel
          </button>
          <SubmitButton busy={busy} className="flex-[2]">
            Create rule
          </SubmitButton>
        </div>
      </form>
    </Card>
  )
}

export default function MonitoringPage({ onBack }: MonitoringPageProps) {
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('rules')
  const [rules, setRules] = useState<Rule[] | null>(null)
  const [alerts, setAlerts] = useState<Alert[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)

  const handleError = (err: unknown) => {
    if (err instanceof ApiError && err.code === 'UNAUTHENTICATED') {
      navigate('/login', { replace: true })
      return
    }
    setError(errorMessageFor(err))
  }

  useEffect(() => {
    if (tab === 'rules' && rules === null) {
      listRules()
        .then((p) => setRules(p.items))
        .catch(handleError)
    }
    if (tab === 'alerts' && alerts === null) {
      listAlerts()
        .then((p) => setAlerts(p.items))
        .catch(handleError)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onBack()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onBack])

  return (
    <div className="scrollbar-slim flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl px-6 pb-20 pt-8">
        <div className="mb-7 flex items-center gap-3">
          <button
            onClick={onBack}
            aria-label="Back"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <ArrowLeft className="h-[18px] w-[18px]" />
          </button>
          <h1 className="text-[22px] font-semibold tracking-tight">Monitoring</h1>
        </div>

        <nav className="mb-6 flex gap-1.5 border-b border-border">
          {(
            [
              { id: 'rules' as const, label: 'Rules', Icon: ListChecks },
              { id: 'alerts' as const, label: 'Alerts', Icon: Bell },
            ] as const
          ).map(({ id, label, Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn(
                'flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-[13.5px] font-medium transition-colors',
                tab === id
                  ? 'border-foreground text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </nav>

        {error && (
          <p className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-3.5 py-2.5 text-[13px] text-destructive">
            {error}
          </p>
        )}

        {tab === 'rules' ? (
          <Panel
            title="Your rules"
            description="Objective thresholds on real data - Talvrin never picks the threshold for you."
            action={
              !showForm && (
                <button
                  onClick={() => setShowForm(true)}
                  className="flex h-9 items-center gap-1.5 rounded-lg border border-border px-3 text-[12.5px] font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                >
                  <Plus className="h-3.5 w-3.5" />
                  New rule
                </button>
              )
            }
          >
            {showForm && (
              <NewRuleForm
                onCreated={(rule) => {
                  setRules((prev) => (prev ? [rule, ...prev] : [rule]))
                  setShowForm(false)
                }}
                onCancel={() => setShowForm(false)}
              />
            )}
            {rules === null ? null : rules.length === 0 && !showForm ? (
              <EmptyState
                icon={ListChecks}
                text="No rules yet. Create one to get an objective alert when a real value crosses a threshold you set."
              />
            ) : rules.length > 0 ? (
              <Card>
                {rules.map((r) => (
                  <RuleRow key={r.id} rule={r} />
                ))}
              </Card>
            ) : null}
          </Panel>
        ) : (
          <Panel
            title="Alert history"
            description="Every objective event Talvrin detected against your rules - nothing here is a recommendation."
          >
            {alerts === null ? null : alerts.length === 0 ? (
              <EmptyState
                icon={Bell}
                text="No alerts yet. Once a rule's condition is met against real, reconciled data, it'll show up here."
              />
            ) : (
              <Card>
                {alerts.map((a) => (
                  <AlertRow key={a.id} alert={a} />
                ))}
              </Card>
            )}
          </Panel>
        )}
      </div>
    </div>
  )
}
