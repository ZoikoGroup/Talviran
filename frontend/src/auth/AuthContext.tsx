import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import * as api from '@/lib/api'

export interface Session {
  email: string
  name: string
  totpEnabled: boolean
}

interface AuthValue {
  session: Session | null
  /** True until the initial "is there already a valid session cookie" check
   * resolves — the router must not decide to redirect before this settles,
   * or a signed-in visitor briefly bounces through /login on every reload. */
  loading: boolean
  signIn: (email: string, password: string, totpCode?: string) => Promise<void>
  signUp: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  deleteAccount: () => Promise<void>
  /** Persists server-side (bug T10 fix) - throws ApiError on failure, so a
   * caller can show the real reason instead of assuming it always works. */
  rename: (name: string) => Promise<void>
  /** Re-checks /me and updates `session` to match. Needed after anything
   * that establishes a session cookie without going through signIn/signUp
   * — currently just password reset, which authenticates via a recovery
   * token rather than a login call. */
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

const toSession = (principal: api.Principal): Session => ({
  email: principal.email,
  name: principal.name,
  totpEnabled: principal.totpEnabled,
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

  const signIn = useCallback(async (email: string, password: string, totpCode?: string) => {
    const principal = await api.login(email, password, totpCode)
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
      try { sessionStorage.removeItem('talvrin_active_view') } catch {}
      setSession(null)
    }
  }, [])

  const deleteAccount = useCallback(async () => {
    try {
      await api.deleteAccount()
    } finally {
      try { sessionStorage.removeItem('talvrin_active_view') } catch {}
      setSession(null)
    }
  }, [])

  const rename = useCallback(async (name: string) => {
    const trimmed = name.trim()
    if (!trimmed) return
    const principal = await api.updateDisplayName(trimmed)
    setSession(toSession(principal))
  }, [])

  const value = useMemo(
    () => ({ session, loading, signIn, signUp, signOut, deleteAccount, rename, refresh }),
    [session, loading, signIn, signUp, signOut, deleteAccount, rename, refresh]
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
