import { useEffect, useRef } from 'react'
import { useLiveMarket } from './useLiveMarket'
import { useAuth } from '@/auth/AuthContext'
import { dispatchTriggeredAlert } from '@/lib/api'
import { toast } from 'sonner'
import type { CustomAlertTrigger } from '@/components/SetAlertModal'

/**
 * Global Real-Time Alert Surveillance Hook.
 * 
 * Runs continuously at the root application level so alerts are evaluated
 * and dispatched immediately as market ticks arrive, regardless of which
 * tab or screen the user is currently viewing.
 */
export function useAlertSurveillance() {
  const { livePrices } = useLiveMarket()
  const { session } = useAuth()
  const firedAlertIdsRef = useRef<Set<string>>(new Set())

  // Load fired alert history on mount to prevent re-firing previously triggered alerts
  useEffect(() => {
    try {
      const historyRaw = localStorage.getItem('talvrin_custom_alerts_history')
      if (historyRaw) {
        const history: CustomAlertTrigger[] = JSON.parse(historyRaw)
        history.forEach((h) => firedAlertIdsRef.current.add(h.id))
      }
    } catch {
      // ignore parse errors
    }
  }, [])

  useEffect(() => {
    if (!livePrices || Object.keys(livePrices).length === 0) return

    let activeAlerts: CustomAlertTrigger[] = []
    try {
      const saved = localStorage.getItem('talvrin_custom_alerts')
      if (saved) activeAlerts = JSON.parse(saved)
    } catch {
      return
    }

    if (activeAlerts.length === 0) return

    let alertsModified = false
    const remainingActive: CustomAlertTrigger[] = []

    activeAlerts.forEach((alert) => {
      if (firedAlertIdsRef.current.has(alert.id)) {
        // Already triggered previously
        alertsModified = true
        return
      }

      // Check if this alert has a matching live quote feed
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

        // Archive into history storage immediately
        try {
          const historyRaw = localStorage.getItem('talvrin_custom_alerts_history')
          const history: CustomAlertTrigger[] = historyRaw ? JSON.parse(historyRaw) : []
          const nextHistory = [triggeredAlert, ...history.filter((h) => h.id !== alert.id)]
          localStorage.setItem('talvrin_custom_alerts_history', JSON.stringify(nextHistory))
        } catch {
          // ignore
        }

        // 1. Dispatch Email immediately via Resend API
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
              // fallback
            })
        }

        // 2. Native Browser Desktop Notification
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

        // 3. In-App Toast Alert with dismissible close button
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
        localStorage.setItem('talvrin_custom_alerts', JSON.stringify(remainingActive))
      } catch {
        // ignore
      }
    }
  }, [livePrices, session?.email])
}
