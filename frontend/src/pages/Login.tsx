import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'
import AuthLayout from '@/components/layouts/AuthLayout'
import { Field, SubmitButton } from '@/components/ui/field'
import { useAuth } from '@/auth/AuthContext'
import {
  DEMO_ID,
  DEMO_PASSWORD,
  credentialsMatch,
  isValidIdentifier,
} from '@/auth/session'

export default function Login() {
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  // Where the user was headed before being bounced to sign in.
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<{ identifier?: string; password?: string }>({})
  const [failed, setFailed] = useState(false)
  const [busy, setBusy] = useState(false)

  const fillDemo = () => {
    setIdentifier(DEMO_ID)
    setPassword(DEMO_PASSWORD)
    setErrors({})
    setFailed(false)
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setFailed(false)

    const next: typeof errors = {}
    if (!identifier.trim()) next.identifier = 'Enter your username or email.'
    else if (!isValidIdentifier(identifier))
      next.identifier = 'That does not look like a username or email address.'
    if (!password) next.password = 'Enter your password.'
    setErrors(next)
    if (Object.keys(next).length > 0) return

    setBusy(true)
    // Stands in for the round trip the real endpoint will make.
    setTimeout(() => {
      if (!credentialsMatch(identifier, password)) {
        setBusy(false)
        setFailed(true)
        return
      }
      signIn(identifier)
      navigate(from, { replace: true })
    }, 450)
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
        {failed && (
          <p
            role="alert"
            className="flex items-start gap-2 rounded-xl border border-destructive/40 bg-destructive/10 px-3.5 py-3 text-[13px] leading-snug text-destructive"
          >
            <AlertCircle className="mt-px h-4 w-4 shrink-0" />
            Incorrect username or password.
          </p>
        )}

        <Field
          label="Username or email"
          type="text"
          autoComplete="username"
          placeholder={DEMO_ID}
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          error={errors.identifier}
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

        {/* A helper, not the headline — so it sits below the action and stays
            visually quiet rather than announcing "prototype" first. */}
        <div className="flex items-center justify-center gap-2 text-[12px] text-muted-foreground">
          <span>Demo access</span>
          <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[11.5px] text-foreground">
            {DEMO_ID}
          </code>
          <span className="text-muted-foreground/50">/</span>
          <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[11.5px] text-foreground">
            {DEMO_PASSWORD}
          </code>
          <button
            type="button"
            onClick={fillDemo}
            className="rounded font-medium text-primary underline-offset-4 transition-colors hover:underline"
          >
            Use
          </button>
        </div>
      </form>
    </AuthLayout>
  )
}
