import React, { useState } from 'react'
import {
  Bell,
  TrendingUp,
  TrendingDown,
  Smartphone,
  Mail,
  BellRing,
  X,
  Check,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/auth/AuthContext'
import { SubmitButton } from '@/components/ui/field'
import { createRule, type CreateRuleInput } from '@/lib/api'

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

interface SetAlertModalProps {
  symbol: string
  name: string
  currentPrice: string
  onClose: () => void
  onAlertCreated?: (alert: CustomAlertTrigger) => void
  existingAlert?: CustomAlertTrigger | null
  onAlertUpdated?: (alert: CustomAlertTrigger) => void
}

export default function SetAlertModal({
  symbol,
  name,
  currentPrice,
  onClose,
  onAlertCreated,
  existingAlert,
  onAlertUpdated,
}: SetAlertModalProps) {
  const { session } = useAuth()
  const isEditing = Boolean(existingAlert)
  const [predicate, setPredicate] = useState<'CROSSES_ABOVE' | 'CROSSES_BELOW'>(
    () => existingAlert?.direction ?? 'CROSSES_ABOVE'
  )
  const [threshold, setThreshold] = useState(() => existingAlert?.threshold ?? '')
  const [notifyInApp, setNotifyInApp] = useState(
    () => existingAlert?.channels.inApp ?? true
  )
  const [notifyBrowser, setNotifyBrowser] = useState(
    () => existingAlert?.channels.browserNotification ?? true
  )
  const [notifyEmail, setNotifyEmail] = useState(
    () => existingAlert?.channels.email ?? true
  )
  const [userEmail] = useState(
    () => existingAlert?.emailAddress ?? session?.email ?? ''
  )
  const [busy, setBusy] = useState(false)
  const [savedSuccess, setSavedSuccess] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!threshold.trim()) return

    setBusy(true)
    try {
      if (notifyBrowser && typeof window !== 'undefined' && 'Notification' in window) {
        if (Notification.permission === 'default') {
          await Notification.requestPermission()
        }
      }

      if (isEditing && existingAlert) {
        const updatedAlert: CustomAlertTrigger = {
          ...existingAlert,
          assetSymbol: symbol,
          assetName: name,
          direction: predicate,
          threshold: threshold.trim(),
          channels: {
            inApp: notifyInApp,
            browserNotification: notifyBrowser,
            email: notifyEmail,
          },
          emailAddress: notifyEmail ? userEmail.trim() : undefined,
        }

        try {
          const existingRaw = localStorage.getItem('talvrin_custom_alerts')
          const list: CustomAlertTrigger[] = existingRaw ? JSON.parse(existingRaw) : []
          const next = list.map((a) => (a.id === existingAlert.id ? updatedAlert : a))
          localStorage.setItem('talvrin_custom_alerts', JSON.stringify(next))
        } catch {
          // ignore
        }

        if (onAlertUpdated) {
          onAlertUpdated(updatedAlert)
        }
      } else {
        const newAlert: CustomAlertTrigger = {
          id: 'alert-' + Date.now(),
          assetSymbol: symbol,
          assetName: name,
          direction: predicate,
          threshold: threshold.trim(),
          channels: {
            inApp: notifyInApp,
            browserNotification: notifyBrowser,
            email: notifyEmail,
          },
          emailAddress: notifyEmail ? userEmail.trim() : undefined,
          createdAt: new Date().toISOString(),
          status: 'ACTIVE',
          currentPrice,
        }

        // Sync into local storage alerts list
        try {
          const existingRaw = localStorage.getItem('talvrin_custom_alerts')
          const list: CustomAlertTrigger[] = existingRaw ? JSON.parse(existingRaw) : []
          const updated = [newAlert, ...list]
          localStorage.setItem('talvrin_custom_alerts', JSON.stringify(updated))
        } catch {
          // ignore
        }

        // Also register to backend rule if sovereign instrument
        try {
          const input: CreateRuleInput = {
            metricId: 'UK_GILT_NOMINAL_SPOT_CURVE',
            predicate,
            thresholdValue: threshold.replace(/[^0-9.]/g, ''),
            tenorYears: '10',
          }
          await createRule(input)
        } catch {
          // ignore fallback
        }

        if (
          notifyBrowser &&
          typeof window !== 'undefined' &&
          'Notification' in window &&
          Notification.permission === 'granted'
        ) {
          new Notification(`Alert Set: ${symbol}`, {
            body: `Watching for ${symbol} to ${predicate === 'CROSSES_ABOVE' ? 'rise above' : 'fall below'} ${threshold}`,
            icon: '/favicon.ico',
          })
        }

        if (onAlertCreated) {
          onAlertCreated(newAlert)
        }
      }

      setSavedSuccess(true)
      setTimeout(() => {
        onClose()
      }, 1000)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/80 p-2 sm:p-4 backdrop-blur-sm animate-in fade-in duration-150 overflow-y-auto">
      <div className="relative my-auto flex max-h-[90vh] w-full max-w-lg flex-col rounded-2xl border border-border bg-[#0e1218] p-4 sm:p-5 shadow-2xl text-foreground animate-in zoom-in-95 duration-150">
        <div className="flex shrink-0 items-center justify-between border-b border-border/60 pb-2.5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/15 text-primary border border-primary/20">
              <Bell className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                {isEditing ? `Modify Alert: ${symbol}` : `Set Alert for ${symbol}`}
              </h3>
              <p className="text-[11px] text-muted-foreground truncate max-w-xs">{name}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-muted-foreground hover:bg-accent hover:text-foreground transition cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {savedSuccess ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400 mb-3 border border-emerald-500/30">
              <Check className="h-6 w-6" />
            </div>
            <h4 className="text-sm font-semibold text-foreground">
              {isEditing ? 'Alert Updated Successfully' : 'Alert Armed Successfully'}
            </h4>
            <p className="text-xs text-muted-foreground mt-1">
              You will be notified when {symbol} crosses {threshold}.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="mt-3 flex flex-1 flex-col min-h-0 overflow-hidden">
            <div className="flex-1 overflow-y-auto space-y-3 pr-1.5 scrollbar-slim">
              {/* Condition Direction */}
            <div>
              <label className="mb-1.5 block text-xs font-medium text-foreground">Condition Direction</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setPredicate('CROSSES_ABOVE')}
                  className={cn(
                    'flex h-9 items-center justify-center gap-1.5 rounded-lg border text-xs font-medium transition cursor-pointer',
                    predicate === 'CROSSES_ABOVE'
                      ? 'border-emerald-500/50 bg-emerald-500/15 text-emerald-400 font-semibold'
                      : 'border-border text-muted-foreground hover:bg-accent'
                  )}
                >
                  <TrendingUp className="h-3.5 w-3.5 text-emerald-400" />
                  <span>rises above</span>
                </button>
                <button
                  type="button"
                  onClick={() => setPredicate('CROSSES_BELOW')}
                  className={cn(
                    'flex h-9 items-center justify-center gap-1.5 rounded-lg border text-xs font-medium transition cursor-pointer',
                    predicate === 'CROSSES_BELOW'
                      ? 'border-rose-500/50 bg-rose-500/15 text-rose-400 font-semibold'
                      : 'border-border text-muted-foreground hover:bg-accent'
                  )}
                >
                  <TrendingDown className="h-3.5 w-3.5 text-rose-400" />
                  <span>falls below</span>
                </button>
              </div>
            </div>

            {/* Prominent Live Price Telemetry Display */}
            <div className="flex items-center justify-between rounded-xl border border-emerald-500/25 bg-emerald-950/20 px-3.5 py-2.5">
              <div className="flex items-center gap-2.5">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500"></span>
                </span>
                <div>
                  <div className="text-[10px] font-semibold tracking-wider text-emerald-400 uppercase">
                    Live Market Price / Yield
                  </div>
                  <div className="font-mono text-base font-bold text-white tracking-tight">
                    {currentPrice}
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setThreshold(currentPrice)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/25 transition cursor-pointer shadow-xs"
                title="Use exact current live price as alert threshold"
              >
                <span>Use Live Price</span>
              </button>
            </div>

            {/* Threshold Input & Live Target Picker */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-medium text-foreground">
                  Trigger Price / Yield Threshold
                </label>
                <div className="text-[11px] text-muted-foreground">
                  Target Price Level
                </div>
              </div>

              <div className="relative">
                <input
                  type="text"
                  required
                  placeholder={`e.g. ${currentPrice}`}
                  value={threshold}
                  onChange={(e) => setThreshold(e.target.value)}
                  className="h-9 w-full rounded-lg border border-border bg-background px-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary font-mono"
                />
              </div>

              {/* Quick Offset Targets Relative to Current Price */}
              {(() => {
                const numeric = parseFloat(currentPrice.replace(/[^0-9.-]/g, ''))
                const isPct = currentPrice.includes('%')
                const isDollar = currentPrice.startsWith('$')
                const isPound = currentPrice.startsWith('£')
                const prefix = isDollar ? '$' : isPound ? '£' : ''
                const suffix = isPct ? '%' : ''

                if (!numeric || isNaN(numeric)) return null

                const calcTarget = (pct: number) => {
                  const val = numeric * (1 + pct / 100)
                  return `${prefix}${val.toFixed(isPct ? 3 : 2)}${suffix}`
                }

                return (
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <span className="text-[10.5px] text-muted-foreground">Quick Target:</span>
                    {predicate === 'CROSSES_ABOVE' ? (
                      <>
                        <button
                          type="button"
                          onClick={() => setThreshold(calcTarget(1))}
                          className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 font-mono text-[10.5px] font-medium text-emerald-400 hover:bg-emerald-500/20 transition cursor-pointer"
                        >
                          +1% ({calcTarget(1)})
                        </button>
                        <button
                          type="button"
                          onClick={() => setThreshold(calcTarget(2.5))}
                          className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 font-mono text-[10.5px] font-medium text-emerald-400 hover:bg-emerald-500/20 transition cursor-pointer"
                        >
                          +2.5% ({calcTarget(2.5)})
                        </button>
                        <button
                          type="button"
                          onClick={() => setThreshold(calcTarget(5))}
                          className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 font-mono text-[10.5px] font-medium text-emerald-400 hover:bg-emerald-500/20 transition cursor-pointer"
                        >
                          +5% ({calcTarget(5)})
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => setThreshold(calcTarget(-1))}
                          className="rounded-md border border-rose-500/30 bg-rose-500/10 px-1.5 py-0.5 font-mono text-[10.5px] font-medium text-rose-400 hover:bg-rose-500/20 transition cursor-pointer"
                        >
                          -1% ({calcTarget(-1)})
                        </button>
                        <button
                          type="button"
                          onClick={() => setThreshold(calcTarget(-2.5))}
                          className="rounded-md border border-rose-500/30 bg-rose-500/10 px-1.5 py-0.5 font-mono text-[10.5px] font-medium text-rose-400 hover:bg-rose-500/20 transition cursor-pointer"
                        >
                          -2.5% ({calcTarget(-2.5)})
                        </button>
                        <button
                          type="button"
                          onClick={() => setThreshold(calcTarget(-5))}
                          className="rounded-md border border-rose-500/30 bg-rose-500/10 px-1.5 py-0.5 font-mono text-[10.5px] font-medium text-rose-400 hover:bg-rose-500/20 transition cursor-pointer"
                        >
                          -5% ({calcTarget(-5)})
                        </button>
                      </>
                    )}
                  </div>
                )
              })()}
            </div>

            {/* Notification Channels */}
            <div className="rounded-xl border border-border/80 bg-background/50 p-3 space-y-2.5">
              <div className="text-[11.5px] font-semibold text-foreground">Notification Channels</div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <label
                  htmlFor="set-alert-inapp"
                  className={cn(
                    'flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs font-medium cursor-pointer transition select-none',
                    notifyInApp
                      ? 'border-primary/60 bg-primary/10 text-foreground'
                      : 'border-border/70 bg-background/50 text-muted-foreground'
                  )}
                >
                  <input
                    id="set-alert-inapp"
                    type="checkbox"
                    checked={notifyInApp}
                    onChange={(e) => setNotifyInApp(e.target.checked)}
                    className="h-3.5 w-3.5 rounded border-border text-primary accent-primary"
                  />
                  <span className="flex items-center gap-1 text-[11px]">
                    <BellRing className="h-3 w-3 text-primary" />
                    In-App
                  </span>
                </label>

                <label
                  htmlFor="set-alert-browser"
                  className={cn(
                    'flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs font-medium cursor-pointer transition select-none',
                    notifyBrowser
                      ? 'border-primary/60 bg-primary/10 text-foreground'
                      : 'border-border/70 bg-background/50 text-muted-foreground'
                  )}
                >
                  <input
                    id="set-alert-browser"
                    type="checkbox"
                    checked={notifyBrowser}
                    onChange={(e) => setNotifyBrowser(e.target.checked)}
                    className="h-3.5 w-3.5 rounded border-border text-primary accent-primary"
                  />
                  <span className="flex items-center gap-1 text-[11px]">
                    <Smartphone className="h-3 w-3 text-primary" />
                    Browser Push
                  </span>
                </label>

                <label
                  htmlFor="set-alert-email"
                  className={cn(
                    'flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs font-medium cursor-pointer transition select-none',
                    notifyEmail
                      ? 'border-primary/60 bg-primary/10 text-foreground'
                      : 'border-border/70 bg-background/50 text-muted-foreground'
                  )}
                >
                  <input
                    id="set-alert-email"
                    type="checkbox"
                    checked={notifyEmail}
                    onChange={(e) => setNotifyEmail(e.target.checked)}
                    className="h-3.5 w-3.5 rounded border-border text-primary accent-primary"
                  />
                  <span className="flex items-center gap-1 text-[11px]">
                    <Mail className="h-3 w-3 text-primary" />
                    Email Alert
                  </span>
                </label>
              </div>

              {notifyEmail && (
                <div className="pt-2 border-t border-border/60">
                  <label className="mb-1 block text-[10.5px] font-medium text-muted-foreground">
                    Recipient Email Address
                  </label>
                  <input
                    type="email"
                    value={userEmail}
                    readOnly
                    className="h-8 w-full rounded-md border border-border/70 bg-background/50 px-2.5 text-xs text-muted-foreground font-mono cursor-not-allowed select-none opacity-85"
                  />
                </div>
              )}
            </div>
          </div>

          {/* Actions - Pinned to bottom of modal */}
          <div className="flex shrink-0 items-center justify-end gap-2 pt-2 border-t border-border/60 mt-1">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-border px-3.5 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition cursor-pointer"
              >
                Cancel
              </button>
              <SubmitButton busy={busy} className="h-8 rounded-lg px-4 text-xs font-semibold">
                {isEditing ? 'Update Alert' : 'Arm Alert'}
              </SubmitButton>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
