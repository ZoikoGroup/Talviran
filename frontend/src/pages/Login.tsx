import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { KeyRound } from 'lucide-react'
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
          <Link to="/signup" className="font-medium text-primary hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <div className="mb-5 flex items-start gap-3 rounded-xl border border-border bg-card/70 px-3.5 py-3">
        <KeyRound className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <div className="min-w-0 flex-1 text-[13px] leading-relaxed">
          <p className="font-medium text-foreground">Demo access</p>
          <p className="mt-0.5 text-muted-foreground">
            Sign in with{' '}
            <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[12px] text-foreground">
              {DEMO_ID}
            </code>{' '}
            /{' '}
            <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[12px] text-foreground">
              {DEMO_PASSWORD}
            </code>
            .
          </p>
        </div>
        <button
          type="button"
          onClick={fillDemo}
          className="shrink-0 rounded-lg border border-border px-2.5 py-1 text-[12px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          Use
        </button>
      </div>

      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        {failed && (
          <p
            role="alert"
            className="rounded-xl border border-destructive/40 bg-destructive/10 px-3.5 py-2.5 text-[13px] text-destructive"
          >
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
        />

        <div>
          <Field
            label="Password"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={errors.password}
          />
          <div className="mt-2 text-right">
            <Link
              to="/forgot-password"
              className="text-[12.5px] text-muted-foreground transition-colors hover:text-foreground"
            >
              Forgot your password?
            </Link>
          </div>
        </div>

        <SubmitButton busy={busy}>Sign in</SubmitButton>
      </form>
    </AuthLayout>
  )
}
