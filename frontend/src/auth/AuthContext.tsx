import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import * as api from '@/lib/api'
import {
  clearDisplayNameOverride,
  getDisplayNameOverride,
  nameFromEmail,
  setDisplayNameOverride,
} from '@/auth/session'

export interface Session {
  email: string
  name: string
}

interface AuthValue {
  session: Session | null
  /** True until the initial "is there already a valid session cookie" check
   * resolves — the router must not decide to redirect before this settles,
   * or a signed-in visitor briefly bounces through /login on every reload. */
  loading: boolean
  signIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  rename: (name: string) => void
  /** Re-checks /me and updates `session` to match. Needed after anything
   * that establishes a session cookie without going through signIn/signUp
   * — currently just password reset, which authenticates via a recovery
   * token rather than a login call. */
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

const toSession = (principal: { email: string }): Session => ({
  email: principal.email,
  name: getDisplayNameOverride() ?? nameFromEmail(principal.email),
})

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    api
      .me()
      .then((principal) => {
        if (!cancelled) setSession(toSession(principal))
      })
      .catch(() => {
        if (!cancelled) setSession(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const signIn = useCallback(async (email: string, password: string) => {
    const principal = await api.login(email, password)
    setSession(toSession(principal))
  }, [])

  const signUp = useCallback(async (email: string, password: string) => {
    const principal = await api.signup(email, password)
    setSession(toSession(principal))
  }, [])

  const refresh = useCallback(async () => {
    try {
      setSession(toSession(await api.me()))
    } catch {
      setSession(null)
    }
  }, [])

  const signOut = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      // Cleared even if the network call fails - a caller choosing to sign
      // out must end up signed out locally regardless.
      clearDisplayNameOverride()
      setSession(null)
    }
  }, [])

  /** Display only - there is no backend profile/display-name endpoint yet
   * (see session.ts's module docstring). */
  const rename = useCallback((name: string) => {
    const trimmed = name.trim()
    if (!trimmed) return
    setDisplayNameOverride(trimmed)
    setSession((prev) => (prev ? { ...prev, name: trimmed } : prev))
  }, [])

  const value = useMemo(
    () => ({ session, loading, signIn, signUp, signOut, rename, refresh }),
    [session, loading, signIn, signUp, signOut, rename, refresh]
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
