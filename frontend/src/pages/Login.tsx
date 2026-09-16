import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'
import AuthLayout from '@/components/layouts/AuthLayout'
import { Field, SubmitButton } from '@/components/ui/field'
import { useAuth } from '@/auth/AuthContext'
import { isEmail } from '@/auth/session'
import { ApiError } from '@/lib/api'

export default function Login() {
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  // Where the user was headed before being bounced to sign in.
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)

    const next: typeof errors = {}
    if (!email.trim()) next.email = 'Enter your email address.'
    else if (!isEmail(email)) next.email = 'That does not look like an email address.'
    if (!password) next.password = 'Enter your password.'
    setErrors(next)
    if (Object.keys(next).length > 0) return

    setBusy(true)
    signIn(email, password)
      .then(() => navigate(from, { replace: true }))
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.code === 'RATE_LIMITED') {
          setFormError('Too many attempts. Please wait a moment and try again.')
        } else if (err instanceof ApiError && err.code === 'UNAUTHENTICATED') {
          setFormError('Incorrect email or password.')
        } else {
          setFormError('Something went wrong. Please try again.')
        }
      })
      .finally(() => setBusy(false))
  }

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Continue your research where you left off."
      footer={
        <>
          New to Talvrin?{' '}
          <Link
            to="/signup"
            className="font-medium text-primary underline-offset-4 hover:underline"
          >
            Create an account
          </Link>
        </>
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
          label="Email"
          type="email"
          autoComplete="username"
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
          disabled={busy}
        />

        <Field
          label="Password"
          type="password"
          autoComplete="current-password"
          placeholder="••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
          disabled={busy}
          action={
            <Link
              to="/forgot-password"
              className="rounded text-[12.5px] text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline"
            >
              Forgot password?
            </Link>
          }
        />

        <SubmitButton busy={busy}>Sign in</SubmitButton>
      </form>
    </AuthLayout>
  )
}
