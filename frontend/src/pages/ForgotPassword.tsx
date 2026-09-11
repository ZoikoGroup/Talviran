import { useState } from 'react'
import { Link } from 'react-router-dom'
import { MailCheck } from 'lucide-react'
import AuthLayout from '@/components/layouts/AuthLayout'
import { Field, SubmitButton } from '@/components/ui/field'
import { isEmail } from '@/auth/session'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim()) return setError('Enter your email address.')
    if (!isEmail(email)) return setError('That does not look like an email address.')
    setError(null)
    setBusy(true)
    setTimeout(() => {
      setBusy(false)
      setSent(true)
    }, 450)
  }

  if (sent) {
    return (
      <AuthLayout
        title="Check your email"
        subtitle="If an account exists for that address, a reset link is on its way."
        footer={
          <Link to="/login" className="font-medium text-primary hover:underline">
            Back to sign in
          </Link>
        }
      >
        <div className="flex items-start gap-3 rounded-xl border border-border bg-background/50 px-3.5 py-3.5">
          <MailCheck className="mt-0.5 h-4 w-4 shrink-0 text-fresh" />
          <div className="min-w-0">
            <p className="break-words text-[13.5px] font-medium">{email}</p>
            <p className="mt-1 text-[12.5px] leading-relaxed text-muted-foreground">
              The link expires in 30 minutes. Check your spam folder if it does
              not arrive.
            </p>
          </div>
        </div>

        <button
          onClick={() => setSent(false)}
          className="mt-4 w-full rounded-xl border border-border px-4 py-2.5 text-[13.5px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          Use a different address
        </button>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="Enter your email and we'll send you a reset link."
      footer={
        <Link to="/login" className="font-medium text-primary hover:underline">
          Back to sign in
        </Link>
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
          error={error}
        />
        <SubmitButton busy={busy}>Send reset link</SubmitButton>
      </form>
    </AuthLayout>
  )
}
