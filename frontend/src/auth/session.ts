/**
 * Client-side session helpers.
 *
 * Every auth flow — sign-up, sign-in, sign-out, forgot/reset password — now
 * calls the real /api/v1/auth/* surface (Supabase-backed) via @/lib/api,
 * wired through AuthContext. Identity itself comes from the backend — the
 * session cookie is HttpOnly and this file never touches it (SEC-001 §41).
 *
 * Display name used to be purely client-side: derived from the email and
 * optionally overridden in a single, NOT account-scoped localStorage key
 * (bug T10). On a shared browser that let one account's chosen name leak
 * into whichever account signed in next, and it was wiped on sign-out, so a
 * fresh login always looked like the rename had reverted. Display name is
 * now a real column (identity.principal.display_name) returned by every
 * signup/login/me/display-name response — see PATCH /api/v1/auth/
 * display-name and AuthContext.rename.
 */

/** Deliberately generous — this is a format hint, not a validation authority. */
export const isEmail = (v: string) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim())

/** Client-side hint only — the backend's own password policy is authoritative
 * and rejects a weak password regardless of what this function says. */
export const passwordProblem = (v: string): string | null => {
  if (v.length < 8) return 'Use at least 8 characters.'
  if (!/[0-9]/.test(v)) return 'Include at least one number.'
  return null
}
