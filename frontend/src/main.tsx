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
import Privacy from '@/pages/Privacy'
import Terms from '@/pages/Terms'
import Contact from '@/pages/Contact'
import Help from '@/pages/Help'
import { AuthProvider, useAuth } from '@/auth/AuthContext'
import { ThemeProvider } from '@/theme/ThemeContext'
import '@/index.css'

/** Sends signed-out visitors to sign in, remembering where they were going. */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { session } = useAuth()
  const location = useLocation()
  if (!session) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <>{children}</>
}

/** Signed-in users have no business on the auth screens. */
function RedirectIfSignedIn({ children }: { children: React.ReactNode }) {
  const { session } = useAuth()
  return session ? <Navigate to="/" replace /> : <>{children}</>
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <AuthProvider>
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
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/contact" element={<Contact />} />
            <Route path="/help" element={<Help />} />
            <Route
              path="/"
              element={
                <RequireAuth>
                  <App />
                </RequireAuth>
              }
            />
            {/* Unknown paths fall back to the app, which itself requires auth. */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  </React.StrictMode>
)
