import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
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
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  ApiError,
  type Alert as ApiAlert,
  type Rule,
  listAlerts,
  listRules,
} from '@/lib/api'
import SetAlertModal from '@/components/SetAlertModal'
import { toast } from 'sonner'
import { useLiveMarket } from '@/hooks/useLiveMarket'

interface MonitoringPageProps {
  onBack: () => void
  initialRuleSymbol?: string | null
}

type Tab = 'active_alerts' | 'history'

export interface CustomAlertTrigger {
  id: string
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

export default function MonitoringPage({ onBack, initialRuleSymbol: _initialRuleSymbol }: MonitoringPageProps) {
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('active_alerts')
  const [backendRules, setBackendRules] = useState<Rule[] | null>(null)
  const [backendAlerts, setBackendAlerts] = useState<ApiAlert[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Browser Notification Permission State
  const [notificationPermission, setNotificationPermission] = useState<NotificationPermission>(() => {
    if (typeof window !== 'undefined' && 'Notification' in window) {
      return Notification.permission
    }
    return 'default'
  })

  // Full universe custom alerts (synced in localStorage)
  const [customAlerts, setCustomAlerts] = useState<CustomAlertTrigger[]>(() => {
    try {
      const saved = localStorage.getItem('talvrin_custom_alerts')
      if (saved) return JSON.parse(saved)
    } catch {
      // fallback
    }
    return [
      {
        id: 'init-1',
        assetSymbol: 'UK 10Y Gilt',
        assetName: 'United Kingdom 10-Year Benchmark Gilt',
        direction: 'CROSSES_ABOVE',
        threshold: '4.50%',
        channels: { inApp: true, browserNotification: true, email: true },
        createdAt: new Date().toISOString(),
        status: 'ACTIVE',
        currentPrice: '4.216%',
      },
      {
        id: 'init-2',
        assetSymbol: 'NVIDIA (NVDA)',
        assetName: 'NVIDIA Corporation',
        direction: 'CROSSES_ABOVE',
        threshold: '$140.00',
        channels: { inApp: true, browserNotification: true, email: true },
        createdAt: new Date().toISOString(),
        status: 'ACTIVE',
        currentPrice: '$135.58',
      },
    ]
  })

  const [modifyingAlert, setModifyingAlert] = useState<CustomAlertTrigger | null>(null)

  const saveAlertsToStorage = (updated: CustomAlertTrigger[]) => {
    setCustomAlerts(updated)
    try {
      localStorage.setItem('talvrin_custom_alerts', JSON.stringify(updated))
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

  const { livePrices, isConnected: wsConnected } = useLiveMarket()
  const [firedAlertIds, setFiredAlertIds] = useState<Set<string>>(new Set())

  // Dynamic real-time threshold crossing comparison
  useEffect(() => {
    customAlerts.forEach((alert) => {
      if (alert.status !== 'ACTIVE') return
      const live = livePrices[alert.assetSymbol]
      if (!live || !live.rawPrice) return

      // Parse threshold value
      const targetNum = parseFloat(alert.threshold.replace(/[^0-9.]/g, ''))
      if (isNaN(targetNum)) return

      const isAbove = alert.direction === 'CROSSES_ABOVE'
      const crossed = isAbove ? live.rawPrice >= targetNum : live.rawPrice <= targetNum

      if (crossed && !firedAlertIds.has(alert.id)) {
        // Trigger alert!
        setFiredAlertIds((prev) => new Set([...prev, alert.id]))
        
        // Update alert status to TRIGGERED
        const updated = customAlerts.map((a) =>
          a.id === alert.id ? { ...a, status: 'TRIGGERED' as const, lastTriggered: new Date().toLocaleTimeString() } : a
        )
        saveAlertsToStorage(updated)

        // Native Browser Desktop Notification
        if (
          alert.channels.browserNotification &&
          typeof window !== 'undefined' &&
          'Notification' in window &&
          Notification.permission === 'granted'
        ) {
          new Notification(`🚨 Market Alert Triggered: ${alert.assetSymbol}`, {
            body: `${alert.assetSymbol} has crossed your threshold ${alert.threshold} (Current: ${live.price})`,
            icon: '/favicon.ico',
          })
        }

        // In-App Toast
        if (alert.channels.inApp) {
          toast.error(`Alert Triggered: ${alert.assetSymbol} crossed ${alert.threshold}!`, {
            description: `Live quote: ${live.price} (${live.change})`,
            duration: 8000,
          })
        }
      }
    })
  }, [livePrices, customAlerts, firedAlertIds])

  const handleError = (err: unknown) => {
    if (err instanceof ApiError && err.code === 'UNAUTHENTICATED') {
      navigate('/login', { replace: true })
      return
    }
    setError(errorMessageFor(err))
  }

  useEffect(() => {
    listRules()
      .then((p) => setBackendRules(p.items))
      .catch(handleError)

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

  const handleDeleteAlert = (id: string) => {
    const updated = customAlerts.filter((a) => a.id !== id)
    saveAlertsToStorage(updated)
    if (modifyingAlert?.id === id) {
      setModifyingAlert(null)
    }
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
              {backendAlerts ? backendAlerts.length : 0}
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
                    const targetNum = parseFloat(alert.threshold.replace(/[^0-9.]/g, ''))
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
                            {wsConnected && (
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
          <Panel title="Historical Trigger Events & Backend Rules">
            {backendRules && backendRules.length > 0 && (
              <div className="mb-3 rounded-lg border border-border/80 bg-background/50 p-3 text-xs text-muted-foreground flex items-center justify-between">
                <span>Deterministic PDP-guarded backend rules active: <strong className="text-foreground">{backendRules.length}</strong></span>
                <span className="text-[11px] font-mono text-primary">Engine Armed</span>
              </div>
            )}
            {backendAlerts === null || backendAlerts.length === 0 ? (
              <EmptyState
                icon={CheckCircle2}
                text="No historical triggers recorded yet. Once market values cross your target thresholds, full audit entries and delivery logs will appear here."
              />
            ) : (
              <Card>
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
