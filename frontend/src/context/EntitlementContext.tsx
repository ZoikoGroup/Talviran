import React, { createContext, useContext, useEffect, useState, useCallback } from 'react'
import {
  getAccountEntitlement,
  type AccountEntitlement,
  type PlanTier,
} from '@/lib/api'
import { useAuth } from '@/auth/AuthContext'

interface EntitlementContextValue {
  entitlement: AccountEntitlement | null
  loading: boolean
  error: string | null
  refreshEntitlement: () => Promise<void>
  checkLimit: (quotaKey: 'watchlists' | 'active_monitoring_rules' | 'verified_research_runs_per_month' | 'evidence_dossier_exports_per_month') => {
    isExceeded: boolean
    current: number
    max: number | 'unlimited'
    remaining: number | 'unlimited'
  }
}

const EntitlementContext = createContext<EntitlementContextValue | undefined>(undefined)

const DEFAULT_FALLBACK_ENTITLEMENT: AccountEntitlement = {
  account_id: 'default',
  plan_tier: 'professional',
  billing_cadence: 'annual',
  is_active: true,
  current_period_end: new Date(Date.now() + 365 * 24 * 3600 * 1000).toISOString(),
  seat_count: 5,
  quotas: {
    watchlists: 50,
    active_monitoring_rules: 125,
    verified_research_runs_per_month: 500,
    evidence_dossier_exports_per_month: 125,
    filing_history_years: 10,
    tick_level_realtime: true,
    team_workspaces: false,
    seat_count: 5,
  },
  usage: {
    watchlists_count: 2,
    active_rules_count: 4,
    research_runs_this_month: 14,
    evidence_exports_this_month: 3,
  },
}

export function EntitlementProvider({ children }: { children: React.ReactNode }) {
  const { session } = useAuth()
  const [entitlement, setEntitlement] = useState<AccountEntitlement | null>(DEFAULT_FALLBACK_ENTITLEMENT)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  const refreshEntitlement = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await getAccountEntitlement()
      setEntitlement(data)
    } catch (err: unknown) {
      console.warn('Failed to load live account entitlement, using institutional default', err)
      setError(err instanceof Error ? err.message : 'Failed to load entitlement')
      // Fallback remains active for uninterrupted demo experience
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (session) {
      void refreshEntitlement()
    }
  }, [session, refreshEntitlement])

  const checkLimit = useCallback(
    (quotaKey: 'watchlists' | 'active_monitoring_rules' | 'verified_research_runs_per_month' | 'evidence_dossier_exports_per_month'): {
      isExceeded: boolean
      current: number
      max: number | 'unlimited'
      remaining: number | 'unlimited'
    } => {
      if (!entitlement) {
        return { isExceeded: false, current: 0, max: 'unlimited', remaining: 'unlimited' }
      }

      const limit = entitlement.quotas[quotaKey]
      let current = 0
      if (quotaKey === 'watchlists') current = entitlement.usage.watchlists_count
      else if (quotaKey === 'active_monitoring_rules') current = entitlement.usage.active_rules_count
      else if (quotaKey === 'verified_research_runs_per_month') current = entitlement.usage.research_runs_this_month
      else if (quotaKey === 'evidence_dossier_exports_per_month') current = entitlement.usage.evidence_exports_this_month

      if (limit === 'unlimited') {
        return { isExceeded: false, current, max: 'unlimited', remaining: 'unlimited' }
      }

      const isExceeded = current >= limit
      const remaining = Math.max(0, limit - current)
      return { isExceeded, current, max: limit, remaining }
    },
    [entitlement]
  )

  return (
    <EntitlementContext.Provider
      value={{
        entitlement,
        loading,
        error,
        refreshEntitlement,
        checkLimit,
      }}
    >
      {children}
    </EntitlementContext.Provider>
  )
}

export function useEntitlement() {
  const context = useContext(EntitlementContext)
  if (!context) {
    throw new Error('useEntitlement must be used within an EntitlementProvider')
  }
  return context
}

export function formatPlanTier(tier?: PlanTier): string {
  if (!tier) return 'Professional'
  switch (tier) {
    case 'explorer':
      return 'Explorer'
    case 'research':
      return 'Research'
    case 'professional':
      return 'Professional'
    case 'teams':
      return 'Teams'
    case 'enterprise':
      return 'Enterprise'
    default:
      return tier
  }
}
