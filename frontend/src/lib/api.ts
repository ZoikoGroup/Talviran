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

// ------------------------------------------------------------------- chats

interface ChatWire {
  id: string
  title: string | null
  model: string
  project_id: string | null
  created_at: string
  last_message_at: string
}

export const createChat = (model: string, title?: string): Promise<ChatWire> =>
  apiFetch<ChatWire>('/api/v1/chats', {
    method: 'POST',
    body: JSON.stringify({ model, title }),
  })

// ---------------------------------------------------------------- research

export interface ResearchCitation {
  label: string
  meta?: string
  pill: Freshness
  kind: CiteKind
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
  citations: { label: string; meta: string | null; pill: string; kind: string }[]
  note: string | null
}

export const postResearch = (conversationId: string, query: string): Promise<ResearchAnswer> =>
  apiFetch<ResearchWire>('/api/v1/research', {
    method: 'POST',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify({ conversation_id: conversationId, query }),
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
    })),
    note: r.note,
  }))
