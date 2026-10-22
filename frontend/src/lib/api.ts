/**
 * Thin fetch wrapper for the real backend (P1 week 14).
 *
 * The session lives in an HttpOnly cookie the browser manages on its own —
 * this file never reads or stores a token itself (SEC-001 §41 forbids
 * exactly that). Every request sends credentials; every non-2xx response
 * becomes a typed ApiError instead of a raw Response the caller has to
 * unwrap by hand.
 */

import type { CiteKind, Freshness } from '@/data/mockReply'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  code: string
  status: number
  retryAfterSeconds?: number

  constructor(code: string, message: string, status: number, retryAfterSeconds?: number) {
    super(message)
    this.code = code
    this.status = status
    this.retryAfterSeconds = retryAfterSeconds
  }
}

interface ErrorEnvelope {
  error?: {
    code?: string
    message?: string
    retry_after_seconds?: number
  }
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...init.headers },
  })

  if (res.status === 204) return undefined as T

  const body = (await res.json().catch(() => null)) as (T & ErrorEnvelope) | null

  if (!res.ok) {
    const err = body?.error
    throw new ApiError(
      err?.code ?? 'INTERNAL_ERROR',
      err?.message ?? 'Something went wrong. Please try again.',
      res.status,
      err?.retry_after_seconds
    )
  }

  return body as T
}

// ------------------------------------------------------------------- auth

export interface Principal {
  principalId: string
  accountId: string
  email: string
}

interface PrincipalWire {
  principal_id: string
  account_id: string
  email: string
}

const toPrincipal = (p: PrincipalWire): Principal => ({
  principalId: p.principal_id,
  accountId: p.account_id,
  email: p.email,
})

export const signup = (email: string, password: string): Promise<Principal> =>
  apiFetch<PrincipalWire>('/api/v1/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  }).then(toPrincipal)

export const login = (email: string, password: string): Promise<Principal> =>
  apiFetch<PrincipalWire>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  }).then(toPrincipal)

export const logout = (): Promise<void> =>
  apiFetch<void>('/api/v1/auth/logout', { method: 'POST' })

export const me = (): Promise<Principal> =>
  apiFetch<PrincipalWire>('/api/v1/auth/me').then(toPrincipal)

export const deleteAccount = (): Promise<void> =>
  apiFetch<void>('/api/v1/auth/me', { method: 'DELETE' })

/** Always resolves — the backend itself never reveals whether the address
 * has an account (SEC-001 §7.1). A thrown ApiError means the request itself
 * failed, not that the email was rejected. */
export const requestPasswordReset = (email: string): Promise<void> =>
  apiFetch<void>('/api/v1/auth/forgot-password', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })

/** Throws ApiError('UNAUTHENTICATED') for an invalid/expired/already-used
 * link, or ApiError('VALIDATION_ERROR') for a password Supabase rejects.
 * On success the backend has already set the new HttpOnly session cookie —
 * callers still need AuthContext.refresh() to pick that up client-side. */
export const resetPassword = (accessToken: string, newPassword: string): Promise<Principal> =>
  apiFetch<PrincipalWire>('/api/v1/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify({ access_token: accessToken, new_password: newPassword }),
  }).then(toPrincipal)

// ------------------------------------------------------------------- chats

interface ChatWire {
  id: string
  title: string | null
  model: string
  project_id: string | null
  created_at: string
  last_message_at: string
}

export interface ChatSummary {
  id: string
  title: string | null
  model: string
  projectId: string | null
  createdAt: string
  lastMessageAt: string
}

const toChatSummary = (c: ChatWire): ChatSummary => ({
  id: c.id,
  title: c.title,
  model: c.model,
  projectId: c.project_id,
  createdAt: c.created_at,
  lastMessageAt: c.last_message_at,
})

export const createChat = (
  model: string,
  title?: string,
  projectId?: string | null
): Promise<ChatSummary> =>
  apiFetch<ChatWire>('/api/v1/chats', {
    method: 'POST',
    body: JSON.stringify({ model, title, project_id: projectId ?? undefined }),
  }).then(toChatSummary)

/** Every real conversation the signed-in account owns — scoped server-side
 * by the session cookie and RLS, so this never needs an account id. */
export const listChats = (): Promise<ChatSummary[]> =>
  apiFetch<ChatWire[]>('/api/v1/chats').then((rows) => rows.map(toChatSummary))

export interface ChatMessageWire {
  id: string
  seq: number
  role: string
  content: string
  createdAt: string
}

export interface ChatDetail extends ChatSummary {
  messages: ChatMessageWire[]
}

interface ChatDetailWire extends ChatWire {
  messages: {
    id: string
    seq: number
    role: string
    content: string
    created_at: string
  }[]
}

/** Full message history for one chat. Fetched lazily — only when a chat is
 * actually opened, not for every row the sidebar lists. */
export const getChat = (chatId: string): Promise<ChatDetail> =>
  apiFetch<ChatDetailWire>(`/api/v1/chats/${chatId}`).then((c) => ({
    ...toChatSummary(c),
    messages: c.messages.map((m) => ({
      id: m.id,
      seq: m.seq,
      role: m.role,
      content: m.content,
      createdAt: m.created_at,
    })),
  }))

export const patchChat = (
  chatId: string,
  patch: { title?: string; projectId?: string | null; model?: string }
): Promise<void> =>
  apiFetch<void>(`/api/v1/chats/${chatId}`, {
    method: 'PATCH',
    body: JSON.stringify({
      ...(patch.title !== undefined ? { title: patch.title } : {}),
      ...(patch.model !== undefined ? { model: patch.model } : {}),
      // `undefined` (omitted) means "leave the project alone"; `null` means
      // "remove from its project" — the backend distinguishes the two by
      // whether the key is present at all, not by its value.
      ...(patch.projectId !== undefined ? { project_id: patch.projectId } : {}),
    }),
  })

export const deleteChat = (chatId: string): Promise<void> =>
  apiFetch<void>(`/api/v1/chats/${chatId}`, { method: 'DELETE' })

// ----------------------------------------------------------------- projects

interface ProjectWire {
  id: string
  name: string
  created_at: string
}

export interface ProjectSummary {
  id: string
  name: string
  createdAt: string
}

const toProjectSummary = (p: ProjectWire): ProjectSummary => ({
  id: p.id,
  name: p.name,
  createdAt: p.created_at,
})

export const listProjects = (): Promise<ProjectSummary[]> =>
  apiFetch<ProjectWire[]>('/api/v1/projects').then((rows) => rows.map(toProjectSummary))

export const createProject = (name: string): Promise<ProjectSummary> =>
  apiFetch<ProjectWire>('/api/v1/projects', {
    method: 'POST',
    body: JSON.stringify({ name }),
  }).then(toProjectSummary)

export const patchProject = (projectId: string, name: string): Promise<void> =>
  apiFetch<void>(`/api/v1/projects/${projectId}`, {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  })

export const deleteProject = (projectId: string): Promise<void> =>
  apiFetch<void>(`/api/v1/projects/${projectId}`, { method: 'DELETE' })

// ---------------------------------------------------------------- research

export interface ResearchCitation {
  label: string
  meta?: string
  pill: Freshness
  kind: CiteKind
  url?: string
}

export interface ResearchFacts {
  title: string
  rows: [string, string][]
}

export interface ResearchAnswer {
  requestId: string
  generatedAt: string
  evidenceBundleId: string | null
  allowedOutputType: string
  messageId: string
  text: string
  facts: ResearchFacts | null
  citations: ResearchCitation[]
  note: string | null
}

interface ResearchWire {
  request_id: string
  generated_at: string
  evidence_bundle_id: string | null
  allowed_output_type: string
  message_id: string
  text: string
  facts: { title: string; rows: [string, string][] } | null
  citations: { label: string; meta: string | null; pill: string; kind: string; url: string | null }[]
  note: string | null
}

export const postResearch = (
  conversationId: string,
  query: string,
  model?: string
): Promise<ResearchAnswer> =>
  apiFetch<ResearchWire>('/api/v1/research', {
    method: 'POST',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify({
      conversation_id: conversationId,
      query,
      ...(model ? { model } : {}),
    }),
  }).then((r) => ({
    requestId: r.request_id,
    generatedAt: r.generated_at,
    evidenceBundleId: r.evidence_bundle_id,
    allowedOutputType: r.allowed_output_type,
    messageId: r.message_id,
    text: r.text,
    facts: r.facts,
    // Cast at the wire boundary: the backend's pill/kind values are drawn
    // from these exact fixed sets by construction (evidence/service.py),
    // but the wire type itself is just `string` since JSON carries no
    // literal-union information.
    citations: r.citations.map((c) => ({
      label: c.label,
      meta: c.meta ?? undefined,
      pill: c.pill as Freshness,
      kind: c.kind as CiteKind,
      url: c.url ?? undefined,
    })),
    note: r.note,
  }))

// --------------------------------------------------------- research evidence

export interface EvidenceItem {
  kind: string
  subjectType: string | null
  metricId: string | null
  value: Record<string, unknown> | null
  basis: string | null
  /** When Talvrin came to hold this exact value (knowledge/ingestion time) -
   * never the real-world date/period it describes (see effectiveTime). */
  asOf: string | null
  /** The real-world market date/period this value describes - can differ
   * from asOf (an ingestion lag, or a historical reconstruction). */
  effectiveTime: string | null
  /** Plain publisher/computation attribution, e.g. "Bank of England" or
   * "Talvrin calculation (gilt_price_yield_v1 v1)" - never a raw
   * rights-profile code or policy-engine identifier. */
  source: string | null
  /** Plain-language summary of what may be done with this fact beyond
   * viewing it (export/redistribution/AI-composed use) - null when no
   * governing rights profile could be resolved at all. */
  permittedUse: string | null
}

export interface EvidenceDetail {
  evidenceBundleId: string | null
  purposeType: string | null
  status: string | null
  items: EvidenceItem[]
}

interface EvidenceWire {
  evidence_bundle_id: string | null
  purpose_type: string | null
  status: string | null
  items: {
    kind: string
    subject_type: string | null
    metric_id: string | null
    value: Record<string, unknown> | null
    basis: string | null
    as_of: string | null
    effective_time: string | null
    source: string | null
    permitted_use: string | null
  }[]
}

export const getResearchEvidence = (messageId: string): Promise<EvidenceDetail> =>
  apiFetch<EvidenceWire>(`/api/v1/research/${messageId}/evidence`).then((r) => ({
    evidenceBundleId: r.evidence_bundle_id,
    purposeType: r.purpose_type,
    status: r.status,
    items: r.items.map((i) => ({
      kind: i.kind,
      subjectType: i.subject_type,
      metricId: i.metric_id,
      value: i.value,
      basis: i.basis,
      asOf: i.as_of,
      effectiveTime: i.effective_time,
      source: i.source,
      permittedUse: i.permitted_use,
    })),
  }))

// -------------------------------------------------------------- monitoring

// The only two watchable metrics today (monitoring/rule_engine.py's own
// SCALAR_VALUE_KEYS/CALCULATION_SCALAR_VALUE_KEYS) - a rule for anything
// else is rejected server-side, so the picker only ever offers these two.
export const WATCHABLE_METRICS = [
  {
    id: 'UK_GILT_NOMINAL_SPOT_CURVE',
    label: 'UK gilt nominal spot curve (yield at a tenor)',
    needs: 'tenor' as const,
  },
  {
    id: 'MODEL_IMPLIED_CLEAN_PRICE',
    label: 'Model-implied clean price (an instrument, by ISIN)',
    needs: 'isin' as const,
  },
] as const

export type WatchableMetricId = (typeof WATCHABLE_METRICS)[number]['id']

interface PageWire<T> {
  items: T[]
  next_cursor: string | null
  has_more: boolean
}

export interface Page<T> {
  items: T[]
  nextCursor: string | null
  hasMore: boolean
}

interface RuleWire {
  id: string
  status: string
  subject_type: string
  subject_id: string
  metric_id: string
  predicate: string
  threshold_value: string
  rearm_threshold: string | null
  debounce_seconds: number
  effective_from: string
  created_at: string
}

export interface Rule {
  id: string
  status: string
  subjectType: string
  subjectId: string
  metricId: string
  predicate: string
  thresholdValue: string
  rearmThreshold: string | null
  debounceSeconds: number
  effectiveFrom: string
  createdAt: string
}

const toRule = (r: RuleWire): Rule => ({
  id: r.id,
  status: r.status,
  subjectType: r.subject_type,
  subjectId: r.subject_id,
  metricId: r.metric_id,
  predicate: r.predicate,
  thresholdValue: r.threshold_value,
  rearmThreshold: r.rearm_threshold,
  debounceSeconds: r.debounce_seconds,
  effectiveFrom: r.effective_from,
  createdAt: r.created_at,
})

export interface CreateRuleInput {
  metricId: WatchableMetricId
  predicate: 'CROSSES_ABOVE' | 'CROSSES_BELOW'
  thresholdValue: string
  instrumentIsin?: string
  tenorYears?: string
  rearmThreshold?: string
  debounceSeconds?: number
}

export const createRule = (input: CreateRuleInput): Promise<Rule> =>
  apiFetch<RuleWire>('/api/v1/monitoring-rules', {
    method: 'POST',
    body: JSON.stringify({
      metric_id: input.metricId,
      predicate: input.predicate,
      threshold_value: input.thresholdValue,
      instrument_isin: input.instrumentIsin ?? null,
      tenor_years: input.tenorYears ?? null,
      rearm_threshold: input.rearmThreshold ?? null,
      debounce_seconds: input.debounceSeconds ?? 0,
    }),
  }).then(toRule)

export const listRules = (cursor?: string): Promise<Page<Rule>> =>
  apiFetch<PageWire<RuleWire>>(
    `/api/v1/monitoring-rules${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`
  ).then((p) => ({
    items: p.items.map(toRule),
    nextCursor: p.next_cursor,
    hasMore: p.has_more,
  }))

interface AlertWire {
  id: string
  rule_id: string
  rule_version_id: string
  evaluation_id: string
  alert_type: string
  subject_id: string
  metric_id: string
  observed_value: string
  threshold_value: string
  knowledge_time: string
  evidence_bundle_id: string | null
  status: string
  created_at: string
}

export interface Alert {
  id: string
  ruleId: string
  alertType: string
  subjectId: string
  metricId: string
  observedValue: string
  thresholdValue: string
  knowledgeTime: string
  status: string
  createdAt: string
}

const toAlert = (a: AlertWire): Alert => ({
  id: a.id,
  ruleId: a.rule_id,
  alertType: a.alert_type,
  subjectId: a.subject_id,
  metricId: a.metric_id,
  observedValue: a.observed_value,
  thresholdValue: a.threshold_value,
  knowledgeTime: a.knowledge_time,
  status: a.status,
  createdAt: a.created_at,
})

export const listAlerts = (cursor?: string): Promise<Page<Alert>> =>
  apiFetch<PageWire<AlertWire>>(
    `/api/v1/alerts${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`
  ).then((p) => ({
    items: p.items.map(toAlert),
    nextCursor: p.next_cursor,
    hasMore: p.has_more,
  }))

// ------------------------------------------------------------------- watchlists

export interface WatchlistItem {
  id: string
  watchlistId: string
  symbol: string
  name: string
  assetClass: string
  instrumentId?: string | null
  sortOrder: number
  createdAt: string
}

export interface Watchlist {
  id: string
  name: string
  description?: string | null
  isDefault: boolean
  createdAt: string
  updatedAt: string
  items: WatchlistItem[]
}

interface WatchlistItemWire {
  id: string
  watchlist_id: string
  symbol: string
  name: string
  asset_class: string
  instrument_id: string | null
  sort_order: number
  created_at: string
}

interface WatchlistWire {
  id: string
  name: string
  description: string | null
  is_default: boolean
  created_at: string
  updated_at: string
  items: WatchlistItemWire[]
}

const toWatchlistItem = (w: WatchlistItemWire): WatchlistItem => ({
  id: w.id,
  watchlistId: w.watchlist_id,
  symbol: w.symbol,
  name: w.name,
  assetClass: w.asset_class,
  instrumentId: w.instrument_id,
  sortOrder: w.sort_order,
  createdAt: w.created_at,
})

const toWatchlist = (w: WatchlistWire): Watchlist => ({
  id: w.id,
  name: w.name,
  description: w.description,
  isDefault: w.is_default,
  createdAt: w.created_at,
  updatedAt: w.updated_at,
  items: (w.items || []).map(toWatchlistItem),
})

export const listWatchlists = (): Promise<Watchlist[]> =>
  apiFetch<WatchlistWire[]>('/api/v1/watchlists').then((arr) => arr.map(toWatchlist))

export const createWatchlist = (data: {
  name: string
  description?: string
  isDefault?: boolean
  items?: Array<{ symbol: string; name: string; assetClass: string; instrumentId?: string }>
}): Promise<Watchlist> =>
  apiFetch<WatchlistWire>('/api/v1/watchlists', {
    method: 'POST',
    body: JSON.stringify({
      name: data.name,
      description: data.description ?? null,
      is_default: data.isDefault ?? false,
      items: (data.items || []).map((it) => ({
        symbol: it.symbol,
        name: it.name,
        asset_class: it.assetClass,
        instrument_id: it.instrumentId ?? null,
      })),
    }),
  }).then(toWatchlist)

export const deleteWatchlist = (id: string): Promise<void> =>
  apiFetch<void>(`/api/v1/watchlists/${id}`, { method: 'DELETE' })

export const addWatchlistItem = (
  watchlistId: string,
  item: { symbol: string; name: string; assetClass: string; instrumentId?: string }
): Promise<WatchlistItem> =>
  apiFetch<WatchlistItemWire>(`/api/v1/watchlists/${watchlistId}/items`, {
    method: 'POST',
    body: JSON.stringify({
      symbol: item.symbol,
      name: item.name,
      asset_class: item.assetClass,
      instrument_id: item.instrumentId ?? null,
    }),
  }).then(toWatchlistItem)

export const removeWatchlistItem = (watchlistId: string, itemId: string): Promise<void> =>
  apiFetch<void>(`/api/v1/watchlists/${watchlistId}/items/${itemId}`, {
    method: 'DELETE',
  })

// ------------------------------------------------------------------- reference instruments

export interface ReferenceInstrument {
  id: string
  issuerId: string
  instrumentType: string
  name: string
  currencyCode: string
  status: string
}

interface InstrumentWire {
  id: string
  issuer_id: string
  instrument_type: string
  name: string
  currency_code: string
  status: string
}

export const listInstruments = (cursor?: string): Promise<Page<ReferenceInstrument>> =>
  apiFetch<PageWire<InstrumentWire>>(
    `/api/v1/instruments${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`
  ).then((p) => ({
    items: p.items.map((i) => ({
      id: i.id,
      issuerId: i.issuer_id,
      instrumentType: i.instrument_type,
      name: i.name,
      currencyCode: i.currency_code,
      status: i.status,
    })),
    nextCursor: p.next_cursor,
    hasMore: p.has_more,
  }))

// ------------------------------------------------------------------- live provider auto-sync

export interface SyncedAssetRecord {
  symbol: string
  name: string
  asset_class: string
  price: string
  source: string
  freshness: string
  bitemporal_status: string
}

export interface SyncResponse {
  status: string
  provider: string
  synced_at: string
  total_synced: number
  assets: SyncedAssetRecord[]
}

export const triggerExternalSync = (provider = 'all', limit = 50): Promise<SyncResponse> =>
  apiFetch<SyncResponse>('/api/v1/sync/trigger', {
    method: 'POST',
    body: JSON.stringify({ provider, limit }),
  })

export const getLiveSyncedAssets = (): Promise<SyncedAssetRecord[]> =>
  apiFetch<SyncedAssetRecord[]>('/api/v1/sync/live-feed')

// ------------------------------------------------------------------- dashboard overview

export interface DashboardTicker {
  title: string
  value: string
  change: string
  is_up: boolean
  is_bps: boolean
  sparkline: number[]
}

export interface DashboardAlert {
  id: string
  title: string
  time_ago: string
  status: string
  metric_id: string
}

export interface DashboardEconomicEvent {
  date: string
  time: string
  flag: string
  code: string
  event: string
}

export interface DashboardWatchlistSummary {
  id: string
  title: string
  detail: string
  change: string
  is_up: boolean
}

export interface DashboardOverviewResponse {
  tickers: DashboardTicker[]
  alerts: DashboardAlert[]
  economic_calendar: DashboardEconomicEvent[]
  watchlists: DashboardWatchlistSummary[]
  as_of: string
}

export const getDashboardOverview = (): Promise<DashboardOverviewResponse> =>
  apiFetch<DashboardOverviewResponse>('/api/v1/dashboard/overview')




