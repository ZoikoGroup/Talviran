import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft,
  Bell,
  BellRing,
  TrendingDown,
  TrendingUp,
  Smartphone,
  CheckCircle2,
  AlertTriangle,
  Trash2,
  Edit2,
  BookOpen,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  ApiError,
  type Alert as ApiAlert,
  listAlerts,
  deleteRule,
} from '@/lib/api'

import SetAlertModal from '@/components/SetAlertModal'
import { toast } from 'sonner'
import { useLiveMarket } from '@/hooks/useLiveMarket'
import { useEntitlement } from '@/context/EntitlementContext'
import { Clock } from 'lucide-react'
import { useAuth } from '@/auth/AuthContext'
import { accountScopedKey } from '@/lib/accountStorage'


interface MonitoringPageProps {
  onBack: () => void
  initialRuleSymbol?: string | null
  onOpenPricing?: () => void
}

type Tab = 'active_alerts' | 'history'

export interface CustomAlertTrigger {
  id: string
  ruleId?: string
  assetSymbol: string
  assetName: string
  direction: 'CROSSES_ABOVE' | 'CROSSES_BELOW'
  threshold: string
  channels: {
    inApp: boolean
    browserNotification: boolean
    email: boolean
  }
  emailAddress?: string
  createdAt: string
  status: 'ACTIVE' | 'TRIGGERED' | 'PAUSED'
  lastTriggered?: string
  currentPrice?: string
}

function errorMessageFor(err: unknown): string {
  if (err instanceof ApiError) return err.message
  return "Talvrin couldn't reach the backend. Please check your connection and try again."
}

function Panel({
  title,
  action,
  children,
}: {
  title: string
  action?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section>
      <div className="flex items-center justify-between gap-4 pb-2">
        <h2 className="text-[17px] font-semibold tracking-tight text-foreground">{title}</h2>
        {action}
      </div>
      <div className="mt-3 flex flex-col gap-4">{children}</div>
    </section>
  )
}

function Card({ children }: { children: React.ReactNode }) {
  return <div className="rounded-xl border border-border/80 bg-card/70 shadow-xs">{children}</div>
}

function EmptyState({ icon: Icon, text }: { icon: typeof Bell; text: string }) {
  return (
    <div className="flex flex-col items-center gap-3 py-14 text-center text-muted-foreground">
      <Icon className="h-8 w-8 opacity-40 text-primary" />
      <p className="max-w-sm text-[13.5px] leading-relaxed">{text}</p>
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
        'inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold',
        above
          ? 'bg-emerald-500/15 text-emerald-500'
          : 'bg-rose-500/15 text-rose-500'
      )}
    >
      <Icon className="h-3 w-3" />
      {DIRECTION_LABEL[predicate] ?? predicate}
    </span>
  )
}

export default function MonitoringPage({ onBack, initialRuleSymbol: _initialRuleSymbol, onOpenPricing }: MonitoringPageProps) {
  const { isRealtimePermitted } = useEntitlement()
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('active_alerts')
  const [backendAlerts, setBackendAlerts] = useState<ApiAlert[] | null>(null)
  const [error, setError] = useState<string | null>(null)


  // Browser Notification Permission State
  const [notificationPermission, setNotificationPermission] = useState<NotificationPermission>(() => {
    if (typeof window !== 'undefined' && 'Notification' in window) {
      return Notification.permission
    }
    return 'default'
  })

  const { session } = useAuth()

  // Full universe custom alerts (active only). No seeded defaults - a new
  // account starts with none, since any hardcoded entry here would be a
  // fabricated alert nobody actually armed (2026-11-10 UAT gap analysis
  // G11 remediation). Keyed by the signed-in account's email, not a bare
  // `talvrin_custom_alerts*` key, so a shared browser can't show one
  // account's armed alerts or trigger history to the next account that
  // signs in - the same leak class as bug T10, here for alerts (T19/T20).
  const [customAlerts, setCustomAlerts] = useState<CustomAlertTrigger[]>([])
  const [historyAlerts, setHistoryAlerts] = useState<CustomAlertTrigger[]>([])

  useEffect(() => {
    try {
      const savedAlerts = localStorage.getItem(accountScopedKey(session?.email, 'talvrin_custom_alerts'))
      setCustomAlerts(savedAlerts ? JSON.parse(savedAlerts) : [])
    } catch {
      setCustomAlerts([])
    }
    try {
      const savedHistory = localStorage.getItem(
        accountScopedKey(session?.email, 'talvrin_custom_alerts_history')
      )
      setHistoryAlerts(savedHistory ? JSON.parse(savedHistory) : [])
    } catch {
      setHistoryAlerts([])
    }
  }, [session?.email])

  const [modifyingAlert, setModifyingAlert] = useState<CustomAlertTrigger | null>(null)

  // Multi-tab synchronization for active and history alerts
  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'talvrin_custom_alerts') {
        try {
          if (e.newValue) {
            setCustomAlerts(JSON.parse(e.newValue))
          }
        } catch {
          // ignore
        }
      } else if (e.key === 'talvrin_custom_alerts_history') {
        try {
          if (e.newValue) {
            setHistoryAlerts(JSON.parse(e.newValue))
          }
        } catch {
          // ignore
        }
      }
    }
    window.addEventListener('storage', handleStorageChange)
    return () => window.removeEventListener('storage', handleStorageChange)
  }, [])

  const saveAlertsToStorage = (updated: CustomAlertTrigger[]) => {
    setCustomAlerts(updated)
    try {
      localStorage.setItem(accountScopedKey(session?.email, 'talvrin_custom_alerts'), JSON.stringify(updated))
    } catch {
      // ignore
    }
  }

  const saveHistoryToStorage = (updatedHistory: CustomAlertTrigger[]) => {
    setHistoryAlerts(updatedHistory)
    try {
      localStorage.setItem(
        accountScopedKey(session?.email, 'talvrin_custom_alerts_history'),
        JSON.stringify(updatedHistory)
      )
    } catch {
      // ignore
    }
  }

  const requestBrowserPermission = async () => {
    if (typeof window !== 'undefined' && 'Notification' in window) {
      const perm = await Notification.requestPermission()
      setNotificationPermission(perm)
      if (perm === 'granted') {
        new Notification('Talvrin Alerts Activated', {
          body: 'You will receive instant desktop notifications when your market triggers fire.',
          icon: '/favicon.ico',
        })
      }
    }
  }

  const { livePrices, isConnected: wsConnected, isSimulated: liveIsSimulated } = useLiveMarket()

  // There used to be a client-side threshold-crossing useEffect here that
  // compared this page's local `customAlerts` against `livePrices` and, on
  // a "crossing," fired a real Resend email + browser Notification + toast
  // and archived the alert into local trigger history - all driven by the
  // sync.py websocket's random-walk feed, with no real MonitoringRule/Alert
  // row behind any of it (2026-11-10 UAT gap analysis G11 remediation).
  // That feed is now explicitly flagged `simulated: true` (surfaced above
  // as `liveIsSimulated`) and the backend refuses to serve it at all in
  // production, but simulated-or-not, a client-observed "crossing" was
  // never a real monitoring event and must never again trigger a real
  // notification. The only genuine alert-firing path is the real backend
  // monitoring engine (monitoring.rule_engine -> monitoring.delivery.
  // deliver_alert), surfaced below as `backendAlerts` / "Backend Audit
  // Triggers" - untouched by this change.
  //
  // A merge from main (2026-11-24) tried to reintroduce exactly this
  // mechanism - a client-side comparison against the simulated feed
  // dispatching a real email via a dispatchTriggeredAlert() helper that no
  // longer exists in lib/api.ts (its own removal is documented at that
  // former call site). Dropped again for the same reason it was removed
  // the first time; the multi-tab localStorage-sync effect above it is
  // independent and was kept.


  const handleError = (err: unknown) => {
    if (err instanceof ApiError && err.code === 'UNAUTHENTICATED') {
      navigate('/login', { replace: true })
      return
    }
    setError(errorMessageFor(err))
  }

  useEffect(() => {
    listAlerts()
      .then((p) => setBackendAlerts(p.items))
      .catch(handleError)
  }, [])


  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onBack()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onBack])

  const handleEditAlert = (alert: CustomAlertTrigger) => {
    setModifyingAlert(alert)
  }

  const handleDeleteAlert = async (id: string) => {
    const targetAlert = customAlerts.find((a) => a.id === id)
    if (targetAlert?.ruleId) {
      try {
        await deleteRule(targetAlert.ruleId)
      } catch {
        // rule deletion error handled silently
      }
    }
    const updated = customAlerts.filter((a) => a.id !== id)
    saveAlertsToStorage(updated)
    if (modifyingAlert?.id === id) {
      setModifyingAlert(null)
    }
    toast.success('Alert trigger removed')
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-background p-4 md:p-6 scrollbar-slim">
      <div className="mx-auto w-full max-w-5xl space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between gap-4 pb-4 border-b border-border/80">
          <div className="flex items-center gap-3">
            {onBack && (
              <button
                onClick={onBack}
                aria-label="Back"
                className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground mr-1"
              >
                <ArrowLeft className="h-[18px] w-[18px]" />
              </button>
            )}
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary border border-primary/20">
              <Bell className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-foreground sm:text-2xl">
                Real-Time Alerts & Triggers
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {!isRealtimePermitted ? (
              <button
                type="button"
                onClick={onOpenPricing}
                title="Explorer Plan: Surveillance sweeps run at 15-minute polling latency. Upgrade to enable tick-level evaluation."
                className="inline-flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-300 hover:bg-amber-500/20 transition-all shadow-xs cursor-pointer"
              >
                <Clock className="h-3.5 w-3.5 text-amber-400" />
                <span>15m Latency</span>
                <span className="ml-1 rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] text-amber-200 font-bold uppercase tracking-wider">
                  Upgrade
                </span>
              </button>
            ) : (
              <div
                title="Real-Time Tick Surveillance Active"
                className="hidden sm:inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-400 shadow-xs"
              >
                <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                <span>Tick-Level Realtime</span>
              </div>
            )}
            <Link
              to="/guides?topic=how-to-use#setting-alerts-step-by-step"
              className="inline-flex items-center gap-1.5 rounded-lg border border-border/80 bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition"
              title="Learn how monitoring rules & dead-man watchers work"
            >
              <BookOpen className="h-3.5 w-3.5 text-primary" />
              <span>Monitoring Guide</span>
            </Link>

            {/* Browser Push Permission Enable */}
            {notificationPermission !== 'granted' && (
              <button
                type="button"
                onClick={requestBrowserPermission}
                className="hidden sm:inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent transition"
                title="Enable browser desktop notifications"
              >
                <Smartphone className="h-3.5 w-3.5 text-primary" />
                <span>Enable Browser Push</span>
              </button>
            )}
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex gap-2 border-b border-border/70 pb-px">
          <button
            onClick={() => setTab('active_alerts')}
            className={cn(
              'inline-flex items-center gap-2 border-b-2 px-3 py-2 text-xs font-medium transition cursor-pointer',
              tab === 'active_alerts'
                ? 'border-primary text-foreground font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            )}
          >
            <BellRing className="h-3.5 w-3.5" />
            <span>Active Alerts</span>
            <span className="rounded-full bg-primary/15 px-1.5 py-0.2 text-[10px] font-semibold text-primary">
              {customAlerts.length}
            </span>
          </button>

          <button
            onClick={() => setTab('history')}
            className={cn(
              'inline-flex items-center gap-2 border-b-2 px-3 py-2 text-xs font-medium transition cursor-pointer',
              tab === 'history'
                ? 'border-primary text-foreground font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            )}
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span>Trigger History</span>
            <span className="rounded-full bg-muted px-1.5 py-0.2 text-[10px] font-semibold text-muted-foreground">
              {historyAlerts.length + (backendAlerts ? backendAlerts.length : 0)}
            </span>
          </button>
        </nav>


        {error && (
          <div className="flex items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Tab 1: Active Alerts */}
        {tab === 'active_alerts' && (
          <Panel title="Configured Market Alerts">
            {customAlerts.length === 0 ? (
              <EmptyState
                icon={Bell}
                text="No active alerts set. Open any asset chart in Markets to arm custom price and yield alerts."
              />
            ) : (
              <Card>
                <div className="divide-y divide-border/60">
                  {customAlerts.map((alert) => {
                    const live = livePrices[alert.assetSymbol]
                    const displayedPrice = live ? live.price : (alert.currentPrice ?? 'Live')
                    const targetNum = parseFloat(alert.threshold.replace(/[^0-9.-]/g, ''))
                    const currentNum = live?.rawPrice ?? parseFloat((alert.currentPrice || '').replace(/[^0-9.]/g, ''))
                    const isYield = alert.threshold.includes('%')
                    
                    let distanceLabel = ''
                    let isNear = false
                    if (!isNaN(targetNum) && !isNaN(currentNum) && currentNum > 0) {
                      const diff = targetNum - currentNum
                      if (isYield) {
                        const bpsDiff = Math.abs(diff * 100).toFixed(1)
                        distanceLabel = `${diff >= 0 ? '+' : '-'}${bpsDiff} bps to target`
                        isNear = Math.abs(diff) <= 0.05
                      } else {
                        const pctDiff = ((diff / currentNum) * 100).toFixed(2)
                        distanceLabel = `${diff >= 0 ? '+' : ''}${pctDiff}% to target`
                        isNear = Math.abs((diff / currentNum) * 100) <= 1.0
                      }
                    }

                    return (
                      <div
                        key={alert.id}
                        className={cn(
                          'flex flex-wrap items-center justify-between gap-3 p-4 transition-colors',
                          alert.status === 'TRIGGERED'
                            ? 'bg-rose-500/10 border-l-4 border-rose-500'
                            : 'hover:bg-accent/30'
                        )}
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-foreground text-sm">{alert.assetSymbol}</span>
                            <span className="text-xs text-muted-foreground truncate max-w-xs">{alert.assetName}</span>
                            {alert.status === 'TRIGGERED' ? (
                              <span className="rounded-full bg-rose-500/20 px-2 py-0.5 text-[10.5px] font-bold text-rose-400 animate-pulse">
                                TRIGGERED {alert.lastTriggered ? `(${alert.lastTriggered})` : ''}
                              </span>
                            ) : (
                              <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10.5px] font-semibold text-emerald-400">
                                ARMED
                              </span>
                            )}
                            {wsConnected && liveIsSimulated && (
                              <span
                                className="inline-flex items-center gap-1 text-[10px] text-amber-400 font-mono"
                                title="This price feed is simulated for local development and is never served in production."
                              >
                                <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                                SIMULATED
                              </span>
                            )}
                            {wsConnected && !liveIsSimulated && (
                              <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400 font-mono">
                                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-ping" />
                                LIVE
                              </span>
                            )}
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                            <span>Triggers when it</span>
                            <DirectionBadge predicate={alert.direction} />
                            <span className="font-mono font-semibold text-foreground">{alert.threshold}</span>
                            <span>• Current:</span>
                            <span
                              className={cn(
                                'font-mono font-bold transition-colors px-1.5 py-0.5 rounded text-xs',
                                live?.direction === 'up' && 'text-emerald-400 bg-emerald-500/10',
                                live?.direction === 'down' && 'text-rose-400 bg-rose-500/10',
                                !live?.direction && 'text-foreground'
                              )}
                            >
                              {displayedPrice}
                            </span>
                            {live?.change && (
                              <span className={cn('text-[11px] font-mono', live.direction === 'up' ? 'text-emerald-400' : 'text-rose-400')}>
                                ({live.change})
                              </span>
                            )}
                            {distanceLabel && (
                              <span
                                className={cn(
                                  'rounded px-1.5 py-0.5 text-[11px] font-mono',
                                  isNear ? 'bg-amber-500/20 text-amber-300 font-bold animate-pulse' : 'bg-accent text-muted-foreground'
                                )}
                              >
                                {distanceLabel}
                              </span>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => handleEditAlert(alert)}
                            className="inline-flex items-center gap-1 rounded-lg border border-border/80 bg-background/80 px-2.5 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                            title="Modify alert parameters"
                          >
                            <Edit2 className="h-3.5 w-3.5 text-primary" />
                            <span>Modify</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeleteAlert(alert.id)}
                            className="rounded-lg p-2 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                            title="Delete alert"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </Card>
            )}
          </Panel>
        )}

        {/* Tab 2: Trigger History */}
        {tab === 'history' && (
          <Panel title="Historical Trigger Events & Fulfilled Alerts">
            {historyAlerts.length === 0 && (!backendAlerts || backendAlerts.length === 0) ? (
              <EmptyState

                icon={CheckCircle2}
                text="No historical triggers recorded yet. Once market values touch your target thresholds, alerts are automatically fulfilled, emailed to your account, and archived here."
              />
            ) : (
              <div className="space-y-4">
                {/* Touched & Dispatched Target Alerts */}
                {historyAlerts.length > 0 && (
                  <Card>
                    <div className="p-3 bg-accent/20 border-b border-border/60 flex items-center justify-between text-xs">
                      <span className="font-semibold text-foreground">Touched & Dispatched Alerts</span>
                      <button
                        type="button"
                        onClick={() => saveHistoryToStorage([])}
                        className="text-[11px] text-muted-foreground hover:text-destructive transition cursor-pointer"
                      >
                        Clear History
                      </button>
                    </div>
                    <div className="divide-y divide-border/60">
                      {historyAlerts.map((alert) => (
                        <div key={alert.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-foreground text-sm">{alert.assetSymbol}</span>
                              {alert.assetName && (
                                <span className="text-xs text-muted-foreground truncate max-w-xs">{alert.assetName}</span>
                              )}
                            </div>

                            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                              <span>Target:</span>
                              <DirectionBadge predicate={alert.direction} />
                              <span className="font-mono font-semibold text-foreground">{alert.threshold}</span>
                              <span>• Touched Quote:</span>
                              <span className="font-mono font-bold text-sky-400">
                                {alert.currentPrice ?? 'Market Price'}
                              </span>
                              {alert.lastTriggered && (
                                <span className="text-[11px] text-muted-foreground">
                                  at {alert.lastTriggered}
                                </span>
                              )}
                              {alert.emailAddress && (
                                <span className="text-[11px] text-muted-foreground">
                                  → {alert.emailAddress}
                                </span>
                              )}
                            </div>
                          </div>
                          <span className="text-xs font-mono text-muted-foreground">
                            Archived
                          </span>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}

                {/* Backend Engine Rules History */}
                {backendAlerts && backendAlerts.length > 0 && (
                  <Card>
                    <div className="p-3 bg-accent/20 border-b border-border/60 text-xs font-semibold text-foreground">
                      Backend Audit Triggers
                    </div>
                    <div className="divide-y divide-border/60">
                      {backendAlerts.map((alert) => (
                        <div key={alert.id} className="flex items-center justify-between p-4">
                          <div>
                            <div className="text-xs font-semibold text-foreground">{alert.metricId}</div>
                            <p className="mt-0.5 text-xs text-muted-foreground">
                              Observed {alert.observedValue} against target threshold {alert.thresholdValue}
                            </p>
                          </div>
                          <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10.5px] font-semibold text-emerald-400">
                            {alert.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}
              </div>
            )}
          </Panel>
        )}

      </div>

      {/* Modify Alert Modal */}
      {modifyingAlert && (
        <SetAlertModal
          symbol={modifyingAlert.assetSymbol}
          name={modifyingAlert.assetName}
          currentPrice={modifyingAlert.currentPrice ?? 'Live'}
          existingAlert={modifyingAlert}
          onClose={() => setModifyingAlert(null)}
          onAlertUpdated={(updated) => {
            const next = customAlerts.map((a) => (a.id === updated.id ? updated : a))
            saveAlertsToStorage(next)
            toast.success(`Alert for ${updated.assetSymbol} updated`)
          }}
        />
      )}
    </div>
  )
}
