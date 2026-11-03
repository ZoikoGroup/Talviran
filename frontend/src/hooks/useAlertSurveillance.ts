import { useEffect, useRef, useState, useCallback } from 'react'
import { useLiveMarket } from './useLiveMarket'
import { useAuth } from '@/auth/AuthContext'
import { dispatchTriggeredAlert } from '@/lib/api'
import { toast } from 'sonner'
import type { CustomAlertTrigger } from '@/components/SetAlertModal'

const STORAGE_ALERTS_KEY = 'talvrin_custom_alerts'
const STORAGE_HISTORY_KEY = 'talvrin_custom_alerts_history'

/**
 * Global Real-Time Alert Surveillance Hook.
 * 
 * Runs continuously at the root application level across all views.
 * Listens for window 'storage' events so alerts added, updated, or removed
 * in any browser tab are instantly synchronized across all open tabs
 * without requiring page reloads.
 */
export function useAlertSurveillance() {
  const { livePrices } = useLiveMarket()
  const { session } = useAuth()
  const firedAlertIdsRef = useRef<Set<string>>(new Set())

  // Active alerts state synchronized across tabs
  const [activeAlerts, setActiveAlerts] = useState<CustomAlertTrigger[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_ALERTS_KEY)
      if (saved) return JSON.parse(saved)
    } catch {
      // ignore
    }
    return []
  })

  // Synchronize alerts from localStorage
  const syncAlertsFromStorage = useCallback(() => {
    try {
      const saved = localStorage.getItem(STORAGE_ALERTS_KEY)
      if (saved) {
        setActiveAlerts(JSON.parse(saved))
      } else {
        setActiveAlerts([])
      }

      const historyRaw = localStorage.getItem(STORAGE_HISTORY_KEY)
      if (historyRaw) {
        const history: CustomAlertTrigger[] = JSON.parse(historyRaw)
        history.forEach((h) => firedAlertIdsRef.current.add(h.id))
      }
    } catch {
      // ignore parse errors
    }
  }, [])

  // 1. Initial load & multi-tab StorageEvent listener
  useEffect(() => {
    syncAlertsFromStorage()

    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === STORAGE_ALERTS_KEY || e.key === STORAGE_HISTORY_KEY) {
        syncAlertsFromStorage()
      }
    }

    window.addEventListener('storage', handleStorageChange)
    return () => {
      window.removeEventListener('storage', handleStorageChange)
    }
  }, [syncAlertsFromStorage])

  // 2. Continuous real-time tick evaluation loop
  useEffect(() => {
    if (!livePrices || Object.keys(livePrices).length === 0 || activeAlerts.length === 0) {
      return
    }

    let alertsModified = false
    const remainingActive: CustomAlertTrigger[] = []

    activeAlerts.forEach((alert) => {
      if (firedAlertIdsRef.current.has(alert.id)) {
        // Already triggered previously
        alertsModified = true
        return
      }

      // Match alert against live ticks
      const quoteKey = Object.keys(livePrices).find((k) =>
        k.toUpperCase() === alert.assetSymbol.toUpperCase() ||
        alert.assetSymbol.toUpperCase().includes(k.toUpperCase()) ||
        k.toUpperCase().includes(alert.assetSymbol.toUpperCase())
      )

      if (!quoteKey || !livePrices[quoteKey]) {
        remainingActive.push(alert)
        return
      }

      const live = livePrices[quoteKey]
      const targetNum = parseFloat(alert.threshold.replace(/[^0-9.]/g, ''))
      if (isNaN(targetNum)) {
        remainingActive.push(alert)
        return
      }

      const isAbove = alert.direction === 'CROSSES_ABOVE'
      const crossed = isAbove ? live.rawPrice >= targetNum : live.rawPrice <= targetNum

      if (crossed) {
        alertsModified = true
        firedAlertIdsRef.current.add(alert.id)

        const timestamp = new Date().toLocaleTimeString()
        const triggeredAlert: CustomAlertTrigger = {
          ...alert,
          status: 'TRIGGERED',
          lastTriggered: timestamp,
          currentPrice: live.price,
        }

        // 1. Archive into history storage immediately
        try {
          const historyRaw = localStorage.getItem(STORAGE_HISTORY_KEY)
          const history: CustomAlertTrigger[] = historyRaw ? JSON.parse(historyRaw) : []
          const nextHistory = [triggeredAlert, ...history.filter((h) => h.id !== alert.id)]
          localStorage.setItem(STORAGE_HISTORY_KEY, JSON.stringify(nextHistory))
        } catch {
          // ignore
        }

        // 2. Dispatch Email immediately via Resend API
        const targetEmail = alert.emailAddress || session?.email
        if (alert.channels.email && targetEmail) {
          dispatchTriggeredAlert({
            assetSymbol: alert.assetSymbol,
            assetName: alert.assetName,
            thresholdValue: alert.threshold,
            observedValue: live.price,
            predicate: alert.direction,
            recipientEmail: targetEmail,
          })
            .then((res) => {
              if (res.email_dispatched) {
                toast.success(`Alert email sent to ${res.recipient}`, {
                  description: `${alert.assetSymbol} touched ${alert.threshold} (Live: ${live.price})`,
                })
              }
            })
            .catch(() => {
              // fallback gracefully
            })
        }

        // 3. Native Browser Desktop Notification
        if (
          alert.channels.browserNotification &&
          typeof window !== 'undefined' &&
          'Notification' in window &&
          Notification.permission === 'granted'
        ) {
          new Notification(`🚨 Market Alert Triggered: ${alert.assetSymbol}`, {
            body: `${alert.assetSymbol} has reached your threshold ${alert.threshold} (Current: ${live.price}).`,
            icon: '/favicon.ico',
          })
        }

        // 4. In-App Toast Alert with dismissible close button
        if (alert.channels.inApp) {
          toast.error(`Target Reached: ${alert.assetSymbol} touched ${alert.threshold}!`, {
            description: `Live quote: ${live.price} (${live.change}). Moved to alert history.`,
            duration: 9000,
          })
        }
      } else {
        remainingActive.push(alert)
      }
    })

    if (alertsModified) {
      try {
        localStorage.setItem(STORAGE_ALERTS_KEY, JSON.stringify(remainingActive))
        setActiveAlerts(remainingActive)
      } catch {
        // ignore
      }
    }
  }, [livePrices, activeAlerts, session?.email])
}
