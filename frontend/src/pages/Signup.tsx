import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import AuthLayout from '@/components/layouts/AuthLayout'
import { Field, SubmitButton } from '@/components/ui/field'
import { useAuth } from '@/auth/AuthContext'
import { isEmail, passwordProblem } from '@/auth/session'

export default function Signup() {
  const { signIn } = useAuth()
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
  const [busy, setBusy] = useState(false)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
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
    setTimeout(() => {
      signIn(email)
      navigate('/', { replace: true })
    }, 450)
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Source-linked research for public markets."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-primary hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <Field
          label="Email"
          type="email"
          autoComplete="email"
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
        />

        <Field
          label="Password"
          type="password"
          autoComplete="new-password"
          placeholder="At least 8 characters"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
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
              <Link to="/terms" className="text-primary hover:underline">
                Terms and Conditions
              </Link>{' '}
              and{' '}
              <Link to="/privacy" className="text-primary hover:underline">
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

        <p className="text-[12px] leading-relaxed text-muted-foreground">
          The prototype does not persist accounts — this signs you straight in.
          To sign in again later, use the demo credentials on the sign-in page.
        </p>
      </form>
    </AuthLayout>
  )
}
