import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'
import AuthLayout from '@/components/layouts/AuthLayout'
import { Field, SubmitButton } from '@/components/ui/field'
import { passwordProblem } from '@/auth/session'
import { useAuth } from '@/auth/AuthContext'
import { ApiError, resetPassword } from '@/auth/api'

/**
 * Where a Supabase recovery link lands. Confirmed live against the real
 * project (2026-09-16): clicking the email link redirects here with
 * `#access_token=...&type=recovery&...` in the URL *fragment*, not the
 * query string — fragments never reach a server, so this page is the only
 * place that token can be read at all.
 */
/** Read once, lazily, at mount — not in an effect. StrictMode's dev-only
 * double-invocation is fine for a pure read but not for "read the hash, then
 * immediately clear it": a second invocation would read back the empty hash
 * the first one just wrote, silently turning a valid link into "invalid".
 * Clearing the hash is idempotent (a no-op the second time) and stays in its
 * own effect below, decoupled from the read. */
function parseRecoveryToken(): string | null {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ''))
  const accessToken = params.get('access_token')
  const type = params.get('type')
  return accessToken && type === 'recovery' ? accessToken : null
}

function useRecoveryToken(): { token: string | null; invalid: boolean } {
  const [token] = useState(parseRecoveryToken)

  // A token has no business lingering in the visible address bar or in
  // browser history any longer than it takes to read it once.
  useEffect(() => {
    if (window.location.hash) window.history.replaceState(null, '', window.location.pathname)
  }, [])

  return { token, invalid: token === null }
}

export default function ResetPassword() {
  const { token, invalid } = useRecoveryToken()
  const { signIn } = useAuth()
  const navigate = useNavigate()

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState<{ password?: string; confirm?: string }>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!token) return

    const next: typeof errors = {}
    const problem = passwordProblem(password)
    if (!password) next.password = 'Choose a new password.'
    else if (problem) next.password = problem
    if (confirm !== password) next.confirm = 'Passwords do not match.'
    setErrors(next)
    if (Object.keys(next).length > 0) return

    setFormError(null)
    setBusy(true)
    try {
      const result = await resetPassword(token, password)
      // The backend already set a real, HttpOnly session cookie — this just
      // brings the UI's own (still localStorage-backed, see auth/session.ts)
      // notion of "signed in" into agreement with it, the same bridge every
      // other page in this app already reads from.
      signIn(result.email)
      navigate('/', { replace: true })
    } catch (err) {
      setFormError(
        err instanceof ApiError
          ? err.message
          : 'Could not reach Talvrin. Check your connection and try again.'
      )
    } finally {
      setBusy(false)
    }
  }

  if (invalid) {
    return (
      <AuthLayout
        title="This link isn't valid"
        subtitle="Reset links expire after a while, and each one only works once."
        footer={
          <Link
            to="/forgot-password"
            className="font-medium text-primary underline-offset-4 hover:underline"
          >
            Request a new link
          </Link>
        }
      >
        <p
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-destructive/40 bg-destructive/10 px-3.5 py-3 text-[13px] leading-snug text-destructive"
        >
          <AlertCircle className="mt-px h-4 w-4 shrink-0" />
          Open the link from your most recent reset email, or request a new one below.
        </p>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Choose a new password"
      subtitle="You'll be signed in with it right away."
      footer={
        <Link to="/login" className="font-medium text-primary underline-offset-4 hover:underline">
          Back to sign in
        </Link>
      }
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-5">
        {formError && (
          <p
            role="alert"
            className="flex items-start gap-2 rounded-xl border border-destructive/40 bg-destructive/10 px-3.5 py-3 text-[13px] leading-snug text-destructive"
          >
            <AlertCircle className="mt-px h-4 w-4 shrink-0" />
            {formError}
          </p>
        )}

        <Field
          label="New password"
          type="password"
          autoComplete="new-password"
          placeholder="At least 8 characters"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
          disabled={busy || !token}
          hint="At least 8 characters, including a number."
        />

        <Field
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          placeholder="Re-enter your new password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={errors.confirm}
          disabled={busy || !token}
        />

        <SubmitButton busy={busy} disabled={!token}>
          Set new password
        </SubmitButton>
      </form>
    </AuthLayout>
  )
}
