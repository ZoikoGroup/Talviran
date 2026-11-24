/**
 * A single, non-account-scoped localStorage key leaks whatever it holds
 * into the next account that signs in on the same browser - the exact
 * shape of bug T10 (display name) and, separately, the custom-alert and
 * trigger-history lists keyed only by `talvrin_custom_alerts*` (T19/T20).
 * Namespacing every such key by the signed-in account's email closes that
 * leak without needing a server round-trip for purely client-side state.
 */
export function accountScopedKey(email: string | null | undefined, key: string): string {
  if (!email) return `${key}:anonymous`
  return `${key}:${email.trim().toLowerCase()}`
}
