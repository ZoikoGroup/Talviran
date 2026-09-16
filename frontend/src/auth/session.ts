/**
 * Client-side session helpers.
 *
 * The backend now has a real /api/v1/auth/* surface (Supabase-backed sign-up,
 * sign-in, sign-out, forgot/reset password — see auth/api.ts), but Login and
 * Signup below still authenticate against nothing but the DEMO_ID constant.
 * Only the forgot/reset-password pages call the real backend so far.
 *
 * Identity itself comes from the backend — the session cookie is HttpOnly
 * and this file never touches it (SEC-001 §41). What lives here is purely
 * cosmetic and client-only: deriving a display name from an email, and a
 * local override for it, since there is no backend profile/display-name
 * endpoint yet.
 */

const DISPLAY_NAME_KEY = 'talvrin-display-name'

/** Deliberately generous — this is a format hint, not a validation authority. */
export const isEmail = (v: string) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim())

/** Client-side hint only — the backend's own password policy is authoritative
 * and rejects a weak password regardless of what this function says. */
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

export const getDisplayNameOverride = (): string | null => {
  try {
    return localStorage.getItem(DISPLAY_NAME_KEY)
  } catch {
    return null
  }
}

export const setDisplayNameOverride = (name: string) => {
  try {
    localStorage.setItem(DISPLAY_NAME_KEY, name.trim())
  } catch {
    // Private mode — the rename just won't survive a reload.
  }
}

export const clearDisplayNameOverride = () => {
  try {
    localStorage.removeItem(DISPLAY_NAME_KEY)
  } catch {
    // Nothing to clean up if storage is unavailable.
  }
}
