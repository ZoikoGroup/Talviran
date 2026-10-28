import React from 'react'
import ReactDOM from 'react-dom/client'
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from 'react-router-dom'
import App from '@/App'
import Login from '@/pages/Login'
import Signup from '@/pages/Signup'
import ForgotPassword from '@/pages/ForgotPassword'
import ResetPassword from '@/pages/ResetPassword'
import Privacy from '@/pages/Privacy'
import Terms from '@/pages/Terms'
import Contact from '@/pages/Contact'
import Help from '@/pages/Help'
import Guides from '@/pages/Guides'
import { AuthProvider, useAuth } from '@/auth/AuthContext'
import { ThemeProvider } from '@/theme/ThemeContext'
import { LiveMarketProvider } from '@/hooks/useLiveMarket'
import { EntitlementProvider } from '@/context/EntitlementContext'
import '@/index.css'

/** Sends signed-out visitors to sign in, remembering where they were going
 * ONLY if they deliberately navigated to a specific URL (e.g. /settings).
 * Generic visitors are routed to home after login. */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { session, loading } = useAuth()
  const location = useLocation()
  if (loading) return null
  if (!session) {
    const isSpecificPath =
      location.pathname !== '/' || Boolean(location.search) || Boolean(location.hash)
    return (
      <Navigate
        to="/login"
        replace
        state={
          isSpecificPath
            ? { from: location.pathname + location.search + location.hash }
            : undefined
        }
      />
    )
  }
  return <>{children}</>
}

/** Signed-in users have no business on the auth screens. */
function RedirectIfSignedIn({ children }: { children: React.ReactNode }) {
  const { session, loading } = useAuth()
  if (loading) return null
  return session ? <Navigate to="/" replace /> : <>{children}</>
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <AuthProvider>
        <LiveMarketProvider>
          <EntitlementProvider>
            <BrowserRouter>
              <Routes>
                <Route
                  path="/login"
                  element={
                    <RedirectIfSignedIn>
                      <Login />
                    </RedirectIfSignedIn>
                  }
                />
                <Route
                  path="/signup"
                  element={
                    <RedirectIfSignedIn>
                      <Signup />
                    </RedirectIfSignedIn>
                  }
                />
                <Route
                  path="/forgot-password"
                  element={
                    <RedirectIfSignedIn>
                      <ForgotPassword />
                    </RedirectIfSignedIn>
                  }
                />
                <Route path="/reset-password" element={<ResetPassword />} />
                <Route path="/privacy" element={<Privacy />} />
                <Route path="/terms" element={<Terms />} />
                <Route path="/contact" element={<Contact />} />
                <Route path="/help" element={<Help />} />
                <Route path="/guides" element={<Guides />} />

                {/* Explicit deep-link routes wrapped with RequireAuth */}
                {['/', '/settings', '/markets', '/watchlists', '/monitoring', '/compare', '/research'].map((p) => (
                  <Route
                    key={p}
                    path={p}
                    element={
                      <RequireAuth>
                        <App />
                      </RequireAuth>
                    }
                  />
                ))}

                {/* Unknown paths fall back to the app, which itself requires auth. */}
                <Route
                  path="*"
                  element={
                    <RequireAuth>
                      <App />
                    </RequireAuth>
                  }
                />
              </Routes>
            </BrowserRouter>
          </EntitlementProvider>
        </LiveMarketProvider>
      </AuthProvider>
    </ThemeProvider>
  </React.StrictMode>
)
