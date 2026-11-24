import { useEffect, useRef, useState, useCallback } from 'react'
import type { CustomAlertTrigger } from '@/components/SetAlertModal'

const STORAGE_ALERTS_KEY = 'talvrin_custom_alerts'
const STORAGE_HISTORY_KEY = 'talvrin_custom_alerts_history'

/**
 * Global multi-tab sync for the local custom-alerts list: a storage event
 * in one tab (an alert armed, edited or removed) is reflected here too,
 * without requiring a reload.
 *
 * This used to also run a "continuous real-time tick evaluation loop" that
 * compared this list against useLiveMarket()'s feed and, on a "crossing,"
 * fired a real email (via a dispatchTriggeredAlert() that no longer exists
 * in lib/api.ts - that removal, and why, is documented at its former call
 * site) plus a real browser Notification and toast. That feed is the same
 * simulated random-walk one MonitoringPage.tsx's own docstring explains is
 * never a real monitoring event (2026-11-10 UAT gap analysis G11
 * remediation) - globalizing it here would have made that violation worse,
 * not fixed it, so it was removed again rather than reconnected to a
 * replacement email call. The only genuine alert-firing path is the real
 * backend monitoring engine (monitoring.rule_engine -> monitoring.delivery.
 * deliver_alert).
 */
export function useAlertSurveillance() {
  const firedAlertIdsRef = useRef<Set<string>>(new Set())

  const [, setActiveAlerts] = useState<CustomAlertTrigger[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_ALERTS_KEY)
      if (saved) return JSON.parse(saved)
    } catch {
      // ignore
    }
    return []
  })

  const syncAlertsFromStorage = useCallback(() => {
    try {
      const saved = localStorage.getItem(STORAGE_ALERTS_KEY)
      setActiveAlerts(saved ? JSON.parse(saved) : [])

      const historyRaw = localStorage.getItem(STORAGE_HISTORY_KEY)
      if (historyRaw) {
        const history: CustomAlertTrigger[] = JSON.parse(historyRaw)
        history.forEach((h) => firedAlertIdsRef.current.add(h.id))
      }
    } catch {
      // ignore parse errors
    }
  }, [])

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
}
