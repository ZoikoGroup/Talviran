import React, { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  Eye,
  EyeOff,
  Mail,
  Lock,
  ArrowRight,
  TrendingUp,
  FileText,
  ShieldCheck,
  Globe2,
  ChevronRight,
  Building2,
  Check,
} from 'lucide-react'
import { useAuth } from '@/auth/AuthContext'
import { isEmail, passwordProblem } from '@/auth/session'
import { ApiError, requestPasswordReset } from '@/lib/api'
import generatedBg from '@/assets/talvrin-login-bg-master-1080p.jpg'

type TabType = 'login' | 'register' | 'reset'

// Social provider icons
function MicrosoftIcon() {
  return (
    <svg className="h-[18px] w-[18px] shrink-0" viewBox="0 0 23 23">
      <path fill="#f35325" d="M1 1h10v10H1z" />
      <path fill="#81bc06" d="M12 1h10v10H12z" />
      <path fill="#05a6f0" d="M1 12h10v10H1z" />
      <path fill="#ffba08" d="M12 12h10v10H12z" />
    </svg>
  )
}

function GoogleIcon() {
  return (
    <svg className="h-[18px] w-[18px] shrink-0" viewBox="0 0 24 24">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
      />
    </svg>
  )
}

function AppleIcon() {
  return (
    <svg className="h-[18px] w-[18px] shrink-0 fill-current text-slate-900" viewBox="0 0 24 24">
      <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M15.97 6.38c.62-.75 1.04-1.8 0.93-2.85-.9.04-2 .6-2.64 1.35-.56.65-1.05 1.72-.92 2.74 1.01.08 2.01-.5 2.63-1.24z" />
    </svg>
  )
}

function TalvrinMonogram() {
  return (
    <div className="flex h-10 w-10 sm:h-11 sm:w-11 items-center justify-center rounded-xl bg-gradient-to-br from-[#6855f8] to-[#5542e8] shadow-md shadow-[#5542e8]/25">
      <svg className="h-6 w-6 text-white" viewBox="0 0 1000 1000" fill="currentColor">
        <path d="M492.97,771.24l-107.47-62.6v-322.34c0-13.53-10.16-23.74-23.64-23.74s-23.76,10.21-23.76,23.74v129.64l-90.57-52.76v-206.22h228.53v375.03c0,7.04,2.8,13.33,7.9,17.72,4.32,3.72,9.97,5.78,15.91,5.78,13.58,0,23.82-10.1,23.82-23.5v-375.03h228.76v207.29l-90.8,51.9v-130.08c0-13.4-10.17-23.5-23.65-23.5s-23.22,9.88-23.73,22.97v320.03s-108.83,65.81-108.83,65.81l-12.47-.14Z" />
      </svg>
    </div>
  )
}

export default function Login() {
  const { signIn, signUp } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  const [activeTab, setActiveTab] = useState<TabType>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [rememberMe, setRememberMe] = useState(true)
  const [acceptTerms, setAcceptTerms] = useState(false)
  const [totpCode, setTotpCode] = useState('')
  const [requires2FA, setRequires2FA] = useState(false)

  const [errors, setErrors] = useState<{
    email?: string
    password?: string
    confirmPassword?: string
    terms?: string
    totp?: string
  }>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const switchTab = (tab: TabType) => {
    setActiveTab(tab)
    setErrors({})
    setFormError(null)
    setSuccessMessage(null)
    setRequires2FA(false)
  }

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setSuccessMessage(null)

    const next: typeof errors = {}
    if (!requires2FA) {
      if (!email.trim()) next.email = 'Enter your work email address.'
      else if (!isEmail(email)) next.email = 'That does not look like a valid email address.'
      if (!password) next.password = 'Enter your password.'
    } else {
      if (!totpCode.trim() || totpCode.trim().length < 6) {
        next.totp = 'Enter the 6-digit verification code.'
      }
    }
    setErrors(next)
    if (Object.keys(next).length > 0) return

    setBusy(true)
    try {
      await signIn(email, password, requires2FA ? totpCode.trim() : undefined)
      if (from && from !== '/') {
        navigate(from, { replace: true })
      } else {
        try { sessionStorage.removeItem('talvrin_active_view') } catch {}
        navigate('/', { replace: true })
      }
    } catch (err: unknown) {
      if (err instanceof ApiError && err.code === 'PRECONDITION_FAILED' && err.message === '2FA_REQUIRED') {
        setRequires2FA(true)
        setFormError(null)
      } else if (err instanceof ApiError && err.code === 'RATE_LIMITED') {
        setFormError('Too many attempts. Please wait a moment and try again.')
      } else if (err instanceof ApiError && err.code === 'UNAUTHENTICATED') {
        if (requires2FA) {
          setFormError('Invalid 2FA code. Please check your authenticator app.')
        } else {
          setFormError('Incorrect email or password.')
        }
      } else if (err instanceof ApiError && err.message) {
        setFormError(err.message)
      } else {
        setFormError('Unable to sign in. Please check your credentials.')
      }
    } finally {
      setBusy(false)
    }
  }

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setSuccessMessage(null)

    const next: typeof errors = {}
    if (!email.trim()) next.email = 'Enter your work email address.'
    else if (!isEmail(email)) next.email = 'That does not look like a valid email address.'

    const pwProblem = passwordProblem(password)
    if (!password) next.password = 'Choose a secure password.'
    else if (pwProblem) next.password = pwProblem

    if (!confirmPassword) next.confirmPassword = 'Confirm your password.'
    else if (confirmPassword !== password) next.confirmPassword = 'Passwords do not match.'

    if (!acceptTerms) next.terms = 'Please accept the terms and privacy policy.'

    setErrors(next)
    if (Object.keys(next).length > 0) return

    setBusy(true)
    try {
      await signUp(email, password)
      if (from && from !== '/') {
        navigate(from, { replace: true })
      } else {
        try { sessionStorage.removeItem('talvrin_active_view') } catch {}
        navigate('/', { replace: true })
      }
    } catch (err: unknown) {
      if (err instanceof ApiError && err.code === 'CONFLICT') {
        setFormError('An account already exists for that email address.')
      } else if (err instanceof ApiError && err.code === 'VALIDATION_ERROR') {
        setErrors((prev) => ({ ...prev, password: err.message }))
      } else if (err instanceof ApiError && err.message) {
        setFormError(err.message)
      } else {
        setFormError('Something went wrong. Please try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  const handleResetSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setSuccessMessage(null)

    if (!email.trim()) {
      setErrors({ email: 'Enter your email address.' })
      return
    }
    if (!isEmail(email)) {
      setErrors({ email: 'That does not look like a valid email address.' })
      return
    }
    setErrors({})
    setBusy(true)

    try {
      await requestPasswordReset(email)
      setSuccessMessage('If an account exists for that address, a reset link has been dispatched.')
    } catch {
      setFormError('Could not reach server. Check your connection and try again.')
    } finally {
      setBusy(false)
    }
  }

  const handleSSOClick = (providerName: string) => {
    setFormError(`Single Sign-On with ${providerName} is enterprise-configured. Please use your work email below.`)
  }

  return (
    <div
      className="relative min-h-screen w-full bg-[#070b1a] bg-cover bg-center bg-no-repeat flex items-center justify-center overflow-x-hidden selection:bg-[#6046f2] selection:text-white"
      style={{
        backgroundImage: `url(${generatedBg})`,
      }}
    >
      {/* Subtle overlay gradient to ensure clean text contrast on both sides */}
      <div className="absolute inset-0 bg-transparent pointer-events-none" />

      {/* Main Container */}
      <div className="relative z-10 mx-auto flex w-full max-w-[1720px] min-h-screen flex-col lg:flex-row items-center justify-between p-4 sm:p-6 md:p-8 lg:p-12 gap-8 lg:gap-4">
        
        {/* ================= LEFT HERO TYPOGRAPHY & BADGES ================= */}
        <div className="w-full lg:w-[56%] xl:w-[58%] flex flex-col justify-center lg:invisible lg:pointer-events-none">
          {/* Brand Logo & TM */}
          <div className="flex items-center gap-3">
            <div className="relative flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-tr from-[#6355f6] to-[#7f71ff] shadow-lg shadow-[#6355f6]/30">
              <svg className="h-6 w-6 text-white" viewBox="0 0 1000 1000" fill="currentColor">
                <path d="M492.97,771.24l-107.47-62.6v-322.34c0-13.53-10.16-23.74-23.64-23.74s-23.76,10.21-23.76,23.74v129.64l-90.57-52.76v-206.22h228.53v375.03c0,7.04,2.8,13.33,7.9,17.72,4.32,3.72,9.97,5.78,15.91,5.78,13.58,0,23.82-10.1,23.82-23.5v-375.03h228.76v207.29l-90.8,51.9v-130.08c0-13.4-10.17-23.5-23.65-23.5s-23.22,9.88-23.73,22.97v320.03s-108.83,65.81-108.83,65.81l-12.47-.14Z" />
              </svg>
            </div>
            <div className="flex items-baseline">
              <span className="text-2xl font-bold tracking-[0.18em] text-white">TALVRIN</span>
              <span className="ml-1 text-[10px] font-semibold text-[#8b7eff]">TM</span>
            </div>
          </div>

          {/* Headline */}
          <h1 className="mt-7 text-3xl font-extrabold tracking-tight text-white sm:text-4xl md:text-5xl lg:leading-[1.15] drop-shadow-md">
            Authoritative <br className="hidden sm:inline" />
            financial research, <br />
            <span className="bg-gradient-to-r from-[#8f82ff] via-[#a397ff] to-[#caa7ff] bg-clip-text text-transparent">
              for a smarter tomorrow.
            </span>
          </h1>

          {/* Sub-headline */}
          <p className="mt-4 text-base font-normal text-slate-200/90 sm:text-lg max-w-[540px] drop-shadow-sm">
            AI-powered insights. Trusted sources. Global markets. Confident decisions.
          </p>

          {/* 4 Feature Badges */}
          <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-3.5 max-w-[560px]">
            {/* 1. Global Markets */}
            <div className="flex flex-col items-center justify-center rounded-2xl border border-white/15 bg-slate-900/40 p-3.5 text-center backdrop-blur-md transition-all hover:border-[#6355f6]/40 hover:bg-slate-900/60 shadow-lg">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#5d4ef2]/30 text-[#a397ff]">
                <TrendingUp className="h-5 w-5" />
              </div>
              <span className="mt-2 text-xs font-semibold leading-tight text-slate-200">
                Global<br />Markets
              </span>
            </div>

            {/* 2. Company Insights */}
            <div className="flex flex-col items-center justify-center rounded-2xl border border-white/15 bg-slate-900/40 p-3.5 text-center backdrop-blur-md transition-all hover:border-[#6355f6]/40 hover:bg-slate-900/60 shadow-lg">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#5d4ef2]/30 text-[#a397ff]">
                <FileText className="h-5 w-5" />
              </div>
              <span className="mt-2 text-xs font-semibold leading-tight text-slate-200">
                Company<br />Insights
              </span>
            </div>

            {/* 3. Trusted Sources */}
            <div className="flex flex-col items-center justify-center rounded-2xl border border-white/15 bg-slate-900/40 p-3.5 text-center backdrop-blur-md transition-all hover:border-[#6355f6]/40 hover:bg-slate-900/60 shadow-lg">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#5d4ef2]/30 text-[#a397ff]">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <span className="mt-2 text-xs font-semibold leading-tight text-slate-200">
                Trusted<br />Sources
              </span>
            </div>

            {/* 4. AI-Powered Analysis */}
            <div className="flex flex-col items-center justify-center rounded-2xl border border-white/15 bg-slate-900/40 p-3.5 text-center backdrop-blur-md transition-all hover:border-[#6355f6]/40 hover:bg-slate-900/60 shadow-lg">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#5d4ef2]/30 text-[#a397ff]">
                <Globe2 className="h-5 w-5" />
              </div>
              <span className="mt-2 text-xs font-semibold leading-tight text-slate-200">
                AI-Powered<br />Analysis
              </span>
            </div>
          </div>
        </div>

        {/* ================= RIGHT CARD COLUMN (WHITE FORM) ================= */}
        <div className="w-full lg:w-[44%] xl:w-[42%] flex items-center justify-center lg:justify-end">
          <div className="relative w-full max-w-[425px] rounded-[26px] bg-white text-slate-900 shadow-2xl p-5 sm:p-6 md:p-7 border border-white/80 flex flex-col justify-between">
            
            {/* Top Navigation Tabs */}
            <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
              <button
                type="button"
                onClick={() => switchTab('login')}
                className={`relative pb-1 text-xs font-semibold tracking-wide transition-colors ${
                  activeTab === 'login'
                    ? 'text-[#6046f2]'
                    : 'text-slate-500 hover:text-slate-900'
                }`}
              >
                Login
                {activeTab === 'login' && (
                  <span className="absolute bottom-[-11px] left-0 right-0 h-[2.5px] rounded-full bg-[#6046f2]" />
                )}
              </button>

              <button
                type="button"
                onClick={() => switchTab('register')}
                className={`relative pb-1 text-xs font-semibold tracking-wide transition-colors ${
                  activeTab === 'register'
                    ? 'text-[#6046f2]'
                    : 'text-slate-500 hover:text-slate-900'
                }`}
              >
                Register
                {activeTab === 'register' && (
                  <span className="absolute bottom-[-11px] left-0 right-0 h-[2.5px] rounded-full bg-[#6046f2]" />
                )}
              </button>

              <button
                type="button"
                onClick={() => switchTab('reset')}
                className={`relative pb-1 text-xs font-semibold tracking-wide transition-colors ${
                  activeTab === 'reset'
                    ? 'text-[#6046f2]'
                    : 'text-slate-500 hover:text-slate-900'
                }`}
              >
                Reset Password
                {activeTab === 'reset' && (
                  <span className="absolute bottom-[-11px] left-0 right-0 h-[2.5px] rounded-full bg-[#6046f2]" />
                )}
              </button>
            </div>

            {/* Brand Header */}
            <div className="mt-4 flex flex-col items-center text-center">
              <div className="flex items-center gap-2">
                <TalvrinMonogram />
                <div className="flex items-baseline">
                  <span className="text-xl font-bold tracking-[0.16em] text-slate-900">TALVRIN</span>
                  <span className="ml-1 text-[9px] font-semibold text-[#6046f2]">TM</span>
                </div>
              </div>

              <h2 className="mt-2.5 text-[21px] font-bold tracking-tight text-slate-900 leading-snug">
                {activeTab === 'login' && 'Welcome back!'}
                {activeTab === 'register' && 'Create your account'}
                {activeTab === 'reset' && 'Reset your password'}
              </h2>
              <p className="mt-0.5 text-[11px] text-slate-500">
                {activeTab === 'login' && 'Sign in to your Talvrin account.'}
                {activeTab === 'register' && 'Start accessing authoritative market intelligence.'}
                {activeTab === 'reset' && 'Enter your email to receive recovery instructions.'}
              </p>
            </div>

            {/* Feedback Alerts */}
            {formError && (
              <div className="mt-3 flex items-start gap-1.5 rounded-xl bg-red-50 p-2 text-xs font-medium text-red-600 border border-red-200">
                <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{formError}</span>
              </div>
            )}
            {successMessage && (
              <div className="mt-3 flex items-start gap-1.5 rounded-xl bg-emerald-50 p-2 text-xs font-medium text-emerald-700 border border-emerald-200">
                <Check className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{successMessage}</span>
              </div>
            )}

            {/* Social SSO Buttons */}
            {activeTab !== 'reset' && (
              <div className="mt-3.5 flex flex-col gap-1.5 sm:gap-2">
                <button
                  type="button"
                  onClick={() => handleSSOClick('Microsoft')}
                  className="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-1.5 sm:py-2 text-xs font-medium text-slate-700 transition hover:bg-slate-50 hover:border-slate-300 shadow-xs"
                >
                  <div className="flex items-center gap-2.5">
                    <MicrosoftIcon />
                    <span>Continue with Microsoft</span>
                  </div>
                  <ChevronRight className="h-3.5 w-3.5 text-slate-400" />
                </button>

                <button
                  type="button"
                  onClick={() => handleSSOClick('Google')}
                  className="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-1.5 sm:py-2 text-xs font-medium text-slate-700 transition hover:bg-slate-50 hover:border-slate-300 shadow-xs"
                >
                  <div className="flex items-center gap-2.5">
                    <GoogleIcon />
                    <span>Continue with Google</span>
                  </div>
                  <ChevronRight className="h-3.5 w-3.5 text-slate-400" />
                </button>

                <button
                  type="button"
                  onClick={() => handleSSOClick('Apple')}
                  className="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-1.5 sm:py-2 text-xs font-medium text-slate-700 transition hover:bg-slate-50 hover:border-slate-300 shadow-xs"
                >
                  <div className="flex items-center gap-2.5">
                    <AppleIcon />
                    <span>Continue with Apple</span>
                  </div>
                  <ChevronRight className="h-3.5 w-3.5 text-slate-400" />
                </button>

                <button
                  type="button"
                  onClick={() => handleSSOClick('Company SSO')}
                  className="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-1.5 sm:py-2 text-xs font-medium text-slate-700 transition hover:bg-slate-50 hover:border-slate-300 shadow-xs"
                >
                  <div className="flex items-center gap-2.5">
                    <Building2 className="h-4 w-4 text-slate-700" />
                    <span>Continue with Company SSO</span>
                  </div>
                  <ChevronRight className="h-3.5 w-3.5 text-slate-400" />
                </button>

                {/* Divider */}
                <div className="relative my-1 flex items-center justify-center">
                  <div className="w-full border-t border-slate-200" />
                  <span className="absolute bg-white px-2.5 text-[10.5px] font-normal text-slate-400">
                    or sign in with email
                  </span>
                </div>
              </div>
            )}

            {/* Login Form */}
            {activeTab === 'login' && (
              <form onSubmit={handleLoginSubmit} noValidate className="mt-1 flex flex-col gap-2.5">
                {!requires2FA ? (
                  <>
                    {/* Work email input */}
                    <div>
                      <label className="block text-[11px] font-medium text-slate-700 mb-1">
                        Work email address
                      </label>
                      <div className="relative flex items-center">
                        <Mail className="absolute left-3 h-3.5 w-3.5 text-slate-400" />
                        <input
                          type="email"
                          placeholder="name@company.com"
                          value={email}
                          onChange={(e) => setEmail(e.target.value)}
                          disabled={busy}
                          className={`w-full rounded-xl border py-1.5 sm:py-2 pl-8 pr-2.5 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 ${
                            errors.email
                              ? 'border-red-400 focus:ring-red-400/30'
                              : 'border-slate-200 focus:border-[#6046f2] focus:ring-[#6046f2]/20'
                          }`}
                        />
                      </div>
                      {errors.email && <p className="mt-0.5 text-[10.5px] text-red-500">{errors.email}</p>}
                    </div>

                    {/* Password input */}
                    <div>
                      <label className="block text-[11px] font-medium text-slate-700 mb-1">
                        Password
                      </label>
                      <div className="relative flex items-center">
                        <Lock className="absolute left-3 h-3.5 w-3.5 text-slate-400" />
                        <input
                          type={showPassword ? 'text' : 'password'}
                          placeholder="Enter your password"
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          disabled={busy}
                          className={`w-full rounded-xl border py-1.5 sm:py-2 pl-8 pr-8 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 ${
                            errors.password
                              ? 'border-red-400 focus:ring-red-400/30'
                              : 'border-slate-200 focus:border-[#6046f2] focus:ring-[#6046f2]/20'
                            }`}
                        />
                        <button
                          type="button"
                          onClick={() => setShowPassword(!showPassword)}
                          className="absolute right-2.5 text-slate-400 hover:text-slate-600 focus:outline-none"
                        >
                          {showPassword ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                        </button>
                      </div>
                      {errors.password && <p className="mt-0.5 text-[10.5px] text-red-500">{errors.password}</p>}
                    </div>

                    {/* Remember Me & Forgot Password */}
                    <div className="flex items-center justify-between pt-0.5">
                      <label className="flex items-center gap-1.5 cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={rememberMe}
                          onChange={(e) => setRememberMe(e.target.checked)}
                          className="h-3.5 w-3.5 rounded border-slate-300 text-[#6046f2] focus:ring-[#6046f2]/30"
                        />
                        <span className="text-[11px] text-slate-600">Remember me for 30 days</span>
                      </label>

                      <button
                        type="button"
                        onClick={() => switchTab('reset')}
                        className="text-[11px] font-medium text-[#6046f2] hover:underline"
                      >
                        Forgot password?
                      </button>
                    </div>
                  </>
                ) : (
                  <div>
                    <label className="block text-[11px] font-medium text-slate-700 mb-1">
                      Two-factor authentication code
                    </label>
                    <input
                      type="text"
                      autoFocus
                      placeholder="6-digit code"
                      value={totpCode}
                      onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                      disabled={busy}
                      className="w-full rounded-xl border border-slate-200 py-2 px-3 text-center text-sm tracking-widest text-slate-900 focus:border-[#6046f2] focus:outline-none focus:ring-2 focus:ring-[#6046f2]/20"
                    />
                    {errors.totp && <p className="mt-1 text-[10.5px] text-red-500">{errors.totp}</p>}
                    <button
                      type="button"
                      onClick={() => {
                        setRequires2FA(false)
                        setTotpCode('')
                      }}
                      className="mt-1 text-xs font-semibold text-[#6046f2] hover:underline"
                    >
                      ← Back to email and password
                    </button>
                  </div>
                )}

                {/* Log in CTA button */}
                <button
                  type="submit"
                  disabled={busy}
                  className="mt-1 flex w-full items-center justify-center gap-1.5 rounded-xl bg-[#6046f2] py-2 sm:py-2.5 text-xs font-semibold text-white shadow-md shadow-[#6046f2]/25 transition hover:bg-[#5238e8] active:scale-[0.99] disabled:opacity-60"
                >
                  <span>{busy ? 'Verifying...' : requires2FA ? 'Verify Code' : 'Log in'}</span>
                  {!busy && <ArrowRight className="h-3.5 w-3.5" />}
                </button>

                {/* New to Talvrin? Register */}
                <div className="text-center text-[11.5px] text-slate-500">
                  New to Talvrin?{' '}
                  <button
                    type="button"
                    onClick={() => switchTab('register')}
                    className="font-bold text-[#6046f2] hover:underline"
                  >
                    Register
                  </button>
                </div>
              </form>
            )}

            {/* Register Form */}
            {activeTab === 'register' && (
              <form onSubmit={handleRegisterSubmit} noValidate className="mt-1 flex flex-col gap-2">
                <div>
                  <label className="block text-[11px] font-medium text-slate-700 mb-1">
                    Work email address
                  </label>
                  <div className="relative flex items-center">
                    <Mail className="absolute left-3 h-3.5 w-3.5 text-slate-400" />
                    <input
                      type="email"
                      placeholder="name@company.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      disabled={busy}
                      className={`w-full rounded-xl border py-1.5 pl-8 pr-2.5 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 ${
                        errors.email
                          ? 'border-red-400 focus:ring-red-400/30'
                          : 'border-slate-200 focus:border-[#6046f2] focus:ring-[#6046f2]/20'
                      }`}
                    />
                  </div>
                  {errors.email && <p className="mt-0.5 text-[10.5px] text-red-500">{errors.email}</p>}
                </div>

                <div>
                  <label className="block text-[11px] font-medium text-slate-700 mb-1">
                    Password
                  </label>
                  <div className="relative flex items-center">
                    <Lock className="absolute left-3 h-3.5 w-3.5 text-slate-400" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      placeholder="At least 8 characters"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      disabled={busy}
                      className={`w-full rounded-xl border py-1.5 pl-8 pr-8 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 ${
                        errors.password
                          ? 'border-red-400 focus:ring-red-400/30'
                          : 'border-slate-200 focus:border-[#6046f2] focus:ring-[#6046f2]/20'
                      }`}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-2.5 text-slate-400 hover:text-slate-600 focus:outline-none"
                    >
                      {showPassword ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                  {errors.password && <p className="mt-0.5 text-[10.5px] text-red-500">{errors.password}</p>}
                </div>

                <div>
                  <label className="block text-[11px] font-medium text-slate-700 mb-1">
                    Confirm Password
                  </label>
                  <div className="relative flex items-center">
                    <Lock className="absolute left-3 h-3.5 w-3.5 text-slate-400" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      placeholder="Re-enter password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      disabled={busy}
                      className={`w-full rounded-xl border py-1.5 pl-8 pr-2.5 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 ${
                        errors.confirmPassword
                          ? 'border-red-400 focus:ring-red-400/30'
                          : 'border-slate-200 focus:border-[#6046f2] focus:ring-[#6046f2]/20'
                      }`}
                    />
                  </div>
                  {errors.confirmPassword && (
                    <p className="mt-0.5 text-[10.5px] text-red-500">{errors.confirmPassword}</p>
                  )}
                </div>

                <div className="pt-0.5">
                  <label className="flex items-start gap-1.5 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={acceptTerms}
                      onChange={(e) => setAcceptTerms(e.target.checked)}
                      className="mt-0.5 h-3.5 w-3.5 rounded border-slate-300 text-[#6046f2] focus:ring-[#6046f2]/30"
                    />
                    <span className="text-[10px] leading-tight text-slate-600">
                      I agree to Talvrin's <Link to="/terms" className="text-[#6046f2] underline">Terms</Link> and <Link to="/privacy" className="text-[#6046f2] underline">Privacy Policy</Link>.
                    </span>
                  </label>
                  {errors.terms && <p className="mt-0.5 text-[10.5px] text-red-500">{errors.terms}</p>}
                </div>

                <button
                  type="submit"
                  disabled={busy}
                  className="mt-1 flex w-full items-center justify-center gap-1.5 rounded-xl bg-[#6046f2] py-2 text-xs font-semibold text-white shadow-md shadow-[#6046f2]/25 transition hover:bg-[#5238e8] active:scale-[0.99] disabled:opacity-60"
                >
                  <span>{busy ? 'Creating account...' : 'Create account'}</span>
                  {!busy && <ArrowRight className="h-3.5 w-3.5" />}
                </button>

                <div className="text-center text-[11px] text-slate-500">
                  Already have an account?{' '}
                  <button
                    type="button"
                    onClick={() => switchTab('login')}
                    className="font-bold text-[#6046f2] hover:underline"
                  >
                    Log in
                  </button>
                </div>
              </form>
            )}

            {/* Reset Form */}
            {activeTab === 'reset' && (
              <form onSubmit={handleResetSubmit} noValidate className="mt-1 flex flex-col gap-2.5">
                <div>
                  <label className="block text-[11px] font-medium text-slate-700 mb-1">
                    Account email address
                  </label>
                  <div className="relative flex items-center">
                    <Mail className="absolute left-3 h-3.5 w-3.5 text-slate-400" />
                    <input
                      type="email"
                      placeholder="name@company.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      disabled={busy}
                      className={`w-full rounded-xl border py-2 pl-8 pr-2.5 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 ${
                        errors.email
                          ? 'border-red-400 focus:ring-red-400/30'
                          : 'border-slate-200 focus:border-[#6046f2] focus:ring-[#6046f2]/20'
                      }`}
                    />
                  </div>
                  {errors.email && <p className="mt-0.5 text-[10.5px] text-red-500">{errors.email}</p>}
                </div>

                <button
                  type="submit"
                  disabled={busy}
                  className="mt-1 flex w-full items-center justify-center gap-1.5 rounded-xl bg-[#6046f2] py-2 text-xs font-semibold text-white shadow-md shadow-[#6046f2]/25 transition hover:bg-[#5238e8] active:scale-[0.99] disabled:opacity-60"
                >
                  <span>{busy ? 'Sending link...' : 'Send reset instructions'}</span>
                  {!busy && <ArrowRight className="h-3.5 w-3.5" />}
                </button>

                <div className="text-center text-[11px] text-slate-500">
                  Remembered password?{' '}
                  <button
                    type="button"
                    onClick={() => switchTab('login')}
                    className="font-bold text-[#6046f2] hover:underline"
                  >
                    Back to login
                  </button>
                </div>
              </form>
            )}

            {/* Footer Inside Card */}
            <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between text-[9.5px] text-slate-400">
              <div className="flex items-center gap-1.5">
                <Link to="/privacy" className="hover:text-slate-600 transition">Privacy</Link>
                <span>|</span>
                <Link to="/terms" className="hover:text-slate-600 transition">Terms</Link>
                <span>|</span>
                <Link to="/help" className="hover:text-slate-600 transition">Accessibility</Link>
                <span>|</span>
                <Link to="/help" className="hover:text-slate-600 transition">Help</Link>
              </div>
              <div>
                <span>© 2026 Talvrin. All rights reserved.</span>
              </div>
            </div>

          </div>
        </div>

      </div>
    </div>
  )
}
