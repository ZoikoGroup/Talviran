/**
 * Session handling for the UI prototype.
 *
 * The backend has identity *models* (Account, Principal, Session) but exposes
 * no auth endpoints yet — `openapi.json` serves only /instruments, /issuers
 * and /healthz. So nothing here authenticates anybody: it stores a local
 * session so the signed-in and signed-out routes can be built and demonstrated.
 *
 * When SEC-001 auth lands, this module is replaced by real token handling and
 * nothing else in the UI should need to change.
 */

const KEY = 'talvrin-session'

export interface Session {
  email: string
  name: string
  /** Epoch ms, so a stale session can be expired rather than lingering. */
  createdAt: number
}

/**
 * The prototype's fixed sign-in credential.
 *
 * Nothing is verified against a server — these exist so the login screen can
 * actually demonstrate a success and a failure. No password is ever stored:
 * the comparison is against this constant and nothing else.
 */
export const DEMO_ID = 'demo'
export const DEMO_PASSWORD = 'demo'

/** Deliberately generous — this is a format hint, not a validation authority. */
export const isEmail = (v: string) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim())

/** Accepts the demo id, or any address-shaped value, as a *format* check. */
export const isValidIdentifier = (v: string) =>
  v.trim().toLowerCase() === DEMO_ID || isEmail(v)

export const credentialsMatch = (identifier: string, password: string) =>
  identifier.trim().toLowerCase() === DEMO_ID && password === DEMO_PASSWORD

/** Mirrors nothing real; a placeholder until SEC-001 password policy applies. */
export const passwordProblem = (v: string): string | null => {
  if (v.length < 8) return 'Use at least 8 characters.'
  if (!/[0-9]/.test(v)) return 'Include at least one number.'
  return null
}

/** Derives a display name from an email local part: "vignesh.k" -> "Vignesh K". */
export const nameFromEmail = (email: string) =>
  email
    .split('@')[0]
    .split(/[._-]+/)
    .filter(Boolean)
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(' ') || 'There'

export const getSession = (): Session | null => {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const s = JSON.parse(raw) as Partial<Session>
    if (typeof s.email !== 'string' || typeof s.name !== 'string') return null
    return { email: s.email, name: s.name, createdAt: s.createdAt ?? Date.now() }
  } catch {
    return null
  }
}

export const signIn = (email: string): Session => {
  const session: Session = {
    email: email.trim(),
    name: nameFromEmail(email),
    createdAt: Date.now(),
  }
  try {
    localStorage.setItem(KEY, JSON.stringify(session))
  } catch {
    // Private mode — the session just won't survive a reload.
  }
  return session
}

/** Renames the signed-in principal. Display only — no server to inform. */
export const renameSession = (name: string): Session | null => {
  const current = getSession()
  if (!current) return null
  const next: Session = { ...current, name: name.trim() || current.name }
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    // Private mode — the change just won't survive a reload.
  }
  return next
}

export const signOut = () => {
  try {
    localStorage.removeItem(KEY)
  } catch {
    // Nothing to clean up if storage is unavailable.
  }
}
