import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import {
  getSession,
  renameSession,
  signIn as storeSignIn,
  signOut as storeSignOut,
  type Session,
} from '@/auth/session'

interface AuthValue {
  session: Session | null
  signIn: (email: string) => void
  signOut: () => void
  rename: (name: string) => void
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(getSession)

  const signIn = useCallback((email: string) => setSession(storeSignIn(email)), [])
  const signOut = useCallback(() => {
    storeSignOut()
    setSession(null)
  }, [])
  const rename = useCallback((name: string) => {
    const next = renameSession(name)
    if (next) setSession(next)
  }, [])

  const value = useMemo(
    () => ({ session, signIn, signOut, rename }),
    [session, signIn, signOut, rename]
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
