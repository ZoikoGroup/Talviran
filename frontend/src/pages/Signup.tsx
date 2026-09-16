import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'
import AuthLayout from '@/components/layouts/AuthLayout'
import { Field, SubmitButton } from '@/components/ui/field'
import { useAuth } from '@/auth/AuthContext'
import { isEmail, passwordProblem } from '@/auth/session'
import { ApiError } from '@/lib/api'

export default function Signup() {
  const { signUp } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [accepted, setAccepted] = useState(false)
  const [errors, setErrors] = useState<{
    email?: string
    password?: string
    confirm?: string
    accepted?: string
  }>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)

    const next: typeof errors = {}
    if (!email.trim()) next.email = 'Enter your email address.'
    else if (!isEmail(email)) next.email = 'That does not look like an email address.'

    const pwProblem = passwordProblem(password)
    if (!password) next.password = 'Choose a password.'
    else if (pwProblem) next.password = pwProblem

    if (!confirm) next.confirm = 'Re-enter your password.'
    else if (confirm !== password) next.confirm = 'Passwords do not match.'

    if (!accepted) next.accepted = 'Please accept the terms to continue.'

    setErrors(next)
    if (Object.keys(next).length > 0) return

    setBusy(true)
    signUp(email, password)
      .then(() => navigate('/', { replace: true }))
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.code === 'CONFLICT') {
          setFormError('An account already exists for that email address.')
        } else if (err instanceof ApiError && err.code === 'VALIDATION_ERROR') {
          setErrors((prev) => ({ ...prev, password: err.message }))
        } else {
          setFormError('Something went wrong. Please try again.')
        }
      })
      .finally(() => setBusy(false))
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Source-linked research for public markets."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-primary underline-offset-4 hover:underline">
            Sign in
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
          autoComplete="email"
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
          disabled={busy}
        />

        <Field
          label="Password"
          type="password"
          autoComplete="new-password"
          placeholder="At least 8 characters"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
          disabled={busy}
          hint="At least 8 characters, including a number."
        />

        <Field
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          placeholder="Re-enter your password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={errors.confirm}
          disabled={busy}
        />

        <div>
          <label className="flex cursor-pointer items-start gap-2.5 text-[13px] leading-relaxed text-muted-foreground">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 accent-primary"
            />
            <span>
              I agree to the{' '}
              <Link to="/terms" className="text-primary underline-offset-4 hover:underline">
                Terms and Conditions
              </Link>{' '}
              and{' '}
              <Link to="/privacy" className="text-primary underline-offset-4 hover:underline">
                Privacy Policy
              </Link>
              .
            </span>
          </label>
          {errors.accepted && (
            <p className="mt-1.5 text-[12px] text-destructive">{errors.accepted}</p>
          )}
        </div>

        <SubmitButton busy={busy}>Create account</SubmitButton>
      </form>
    </AuthLayout>
  )
}
