/**
 * The signed-in user, as the UI displays them.
 *
 * Identity now comes from the local session rather than a hardcoded constant,
 * so whoever signs in is who the sidebar and the greeting show. The plan is
 * still fixed — there is no billing or entitlement endpoint yet (RIGHTS-001).
 */

import { useAuth } from '@/auth/AuthContext'

export interface DisplayUser {
  name: string
  /** Used for the greeting — a full name reads oddly after "Hello,". */
  firstName: string
  initials: string
  plan: string
}

const initialsFrom = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p.charAt(0).toUpperCase())
    .join('') || 'T'

export function useCurrentUser(): DisplayUser {
  const { session } = useAuth()
  const name = session?.name ?? 'Guest'
  return {
    name,
    firstName: name.split(/\s+/)[0] || name,
    initials: initialsFrom(name),
    plan: 'FREE',
  }
}
