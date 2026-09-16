/**
 * The real backend calls this app makes — currently just the forgot/reset
 * password pair. Login and Signup still run on the localStorage mock in
 * session.ts; this file is the first piece of the bridge to the real
 * /api/v1/auth/* endpoints, not a full replacement of it yet.
 *
 * `credentials: 'include'` matters more than it looks: the backend sets the
 * session as an HttpOnly cookie on a successful reset, and fetch only sends
 * or stores cookies across origins (5173 vs 8000 in dev) when explicitly
 * told to.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number
  ) {
    super(message)
  }
}

interface ErrorEnvelope {
  error: { code: string; message: string }
}

async function parseErrorOr<T>(res: Response): Promise<T> {
  if (res.ok) {
    // 202/204 legitimately have no body; callers of those ignore the
    // resolved value, so `as T` here is never actually inspected for them.
    const text = await res.text()
    return (text ? JSON.parse(text) : undefined) as T
  }
  let body: ErrorEnvelope | null = null
  try {
    body = (await res.json()) as ErrorEnvelope
  } catch {
    // A non-JSON failure (proxy error page, network gateway, ...) — fall
    // through to the generic message below rather than throw on .error.
  }
  throw new ApiError(
    body?.error.message ?? 'Something went wrong. Please try again.',
    body?.error.code ?? 'UNKNOWN',
    res.status
  )
}

/** Always resolves — the backend itself never reveals whether the address
 * has an account (SEC-001 §7.1), and this must not undo that by branching
 * on the caller's behalf. A thrown ApiError here means the request itself
 * failed, not that the email was rejected. */
export async function requestPasswordReset(email: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/auth/forgot-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ email }),
  })
  await parseErrorOr<void>(res)
}

export interface ResetPasswordResult {
  principal_id: string
  account_id: string
  email: string
}

/** Throws ApiError('UNAUTHENTICATED') for an invalid/expired/already-used
 * link, or ApiError('VALIDATION_ERROR') for a password Supabase rejects. */
export async function resetPassword(
  accessToken: string,
  newPassword: string
): Promise<ResetPasswordResult> {
  const res = await fetch(`${API_BASE}/api/v1/auth/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ access_token: accessToken, new_password: newPassword }),
  })
  return parseErrorOr<ResetPasswordResult>(res)
}
