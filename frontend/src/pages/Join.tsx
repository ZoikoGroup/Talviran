import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { AlertCircle, CheckCircle2, Users, ArrowRight, RefreshCw } from 'lucide-react'
import AuthLayout from '@/components/layouts/AuthLayout'
import { Field, SubmitButton } from '@/components/ui/field'
import { useAuth } from '@/auth/AuthContext'
import { passwordProblem } from '@/auth/session'
import * as api from '@/lib/api'

export default function Join() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const emailParam = params.get('email') || ''
  const navigate = useNavigate()
  const { signIn } = useAuth()

  const [loading, setLoading] = useState(true)
  const [invitation, setInvitation] = useState<api.InvitationDetails | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    if (!token) {
      setError('Missing invitation token in the link.')
      setLoading(false)
      return
    }

    api
      .getInvitationDetails(token)
      .then((data) => {
        setInvitation(data)
        if (!data.is_valid) {
          setError(
            data.status === 'EXPIRED'
              ? 'This invitation link has expired. Please ask your administrator to issue a new invite.'
              : 'This invitation has already been accepted or revoked.'
          )
        }
      })
      .catch((err) => {
        setError(err?.message || 'Unable to load invitation details. The link may be invalid.')
      })
      .finally(() => {
        setLoading(false)
      })
  }, [token])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setValidationError(null)

    const pwError = passwordProblem(password)
    if (pwError) {
      setValidationError(pwError)
      return
    }

    if (password !== confirmPassword) {
      setValidationError('Passwords do not match.')
      return
    }

    try {
      setSubmitting(true)
      await api.acceptInvitation({
        token,
        password,
      })
      setSuccess(true)

      // Automatically sign in the user
      const targetEmail = invitation?.email || emailParam
      try {
        await signIn(targetEmail, password)
        navigate('/', { replace: true })
      } catch {
        // Fallback to login screen
        setTimeout(() => {
          navigate('/login', { replace: true })
        }, 1500)
      }
    } catch (err: any) {
      setValidationError(err?.message || 'Failed to accept invitation. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout
      title="Join Organization"
      subtitle="Accept your team invite and configure workspace access."
    >
      <div className="rounded-2xl border border-border/80 bg-card p-6 shadow-xl backdrop-blur-md">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-12 text-center text-sm text-muted-foreground space-y-3">
            <RefreshCw className="h-6 w-6 animate-spin text-primary" />
            <p>Validating invitation token...</p>
          </div>
        ) : error ? (
          <div className="py-6 text-center space-y-4">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-400">
              <AlertCircle className="h-6 w-6" />
            </div>
            <div className="space-y-1">
              <h3 className="text-base font-semibold text-foreground">Invitation Invalid</h3>
              <p className="text-xs text-muted-foreground leading-relaxed max-w-sm mx-auto">{error}</p>
            </div>
            <div className="pt-2">
              <Link
                to="/login"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
              >
                <span>Return to Sign In</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </div>
        ) : success ? (
          <div className="py-6 text-center space-y-4">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <CheckCircle2 className="h-6 w-6" />
            </div>
            <div className="space-y-1">
              <h3 className="text-base font-semibold text-foreground">Welcome to {invitation?.account_name}!</h3>
              <p className="text-xs text-muted-foreground">Your seat has been activated. Redirecting to workspace...</p>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 flex items-start gap-3">
              <Users className="h-5 w-5 text-primary shrink-0 mt-0.5" />
              <div>
                <div className="text-xs font-semibold text-foreground">
                  You have been invited to join <strong className="text-primary">{invitation?.account_name}</strong>
                </div>
                <div className="text-[11px] text-muted-foreground mt-0.5">
                  Role: <span className="font-semibold capitalize text-foreground">{invitation?.role}</span> &bull; Account: {invitation?.email}
                </div>
              </div>
            </div>

            {validationError && (
              <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 p-3 text-xs text-rose-300 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{validationError}</span>
              </div>
            )}

            <Field label="Email address" hint="Locked to the invited address">
              <input
                type="email"
                disabled
                value={invitation?.email}
                className="w-full rounded-xl border border-border/80 bg-muted/50 px-3.5 py-2 text-xs font-mono text-muted-foreground cursor-not-allowed"
              />
            </Field>

            <Field label="Set your password" hint="Minimum 8 characters">
              <input
                type="password"
                required
                autoFocus
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Choose a strong password"
                className="w-full rounded-xl border border-border/80 bg-background px-3.5 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </Field>

            <Field label="Confirm password">
              <input
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Confirm your password"
                className="w-full rounded-xl border border-border/80 bg-background px-3.5 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </Field>

            <SubmitButton busy={submitting}>
              {submitting ? 'Activating Seat...' : 'Accept & Join Workspace'}
            </SubmitButton>
          </form>
        )}
      </div>
    </AuthLayout>
  )
}
