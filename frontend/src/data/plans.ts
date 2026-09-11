/**
 * Plan catalogue, from PRD-001 §12.
 *
 * No prices. The spec is explicit that price bands are commercial hypotheses,
 * not software constants, and requires a versioned plan/entitlement catalogue
 * so limits can change without a code change. Putting figures here would bake
 * in exactly what it says not to.
 */

export interface Plan {
  id: string
  name: string
  role: string
  gates: string
  /** Deferred until rights and commercial approval — not sellable yet. */
  deferred?: boolean
}

export const PLANS: Plan[] = [
  {
    id: 'free',
    name: 'Free',
    role: 'Prove evidence and calculation quality.',
    gates: 'Small watchlist, delayed or end-of-day data where appropriate, capped monitoring, limited history.',
  },
  {
    id: 'core',
    name: 'Core',
    role: 'Self-directed investor continuity.',
    gates: 'Sovereign calculators, normal watchlists, standard source-linked research, daily objective monitoring.',
  },
  {
    id: 'research',
    name: 'Research',
    role: 'Serious private investor.',
    gates: 'Expanded history, evidence panels, comparison depth and more monitoring capacity.',
  },
  {
    id: 'pro',
    name: 'Pro',
    role: 'Professional factual workflow.',
    gates: 'Larger monitoring graph, higher-frequency eligible alerts, export and advanced datasets where licensed.',
  },
  {
    id: 'team',
    name: 'Team / API',
    role: 'Enterprise mode.',
    gates: 'Seats, structured feeds, entitlements and support.',
    deferred: true,
  },
]

export const CURRENT_PLAN_ID = 'free'
