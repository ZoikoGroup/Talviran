import { Link } from 'react-router-dom'
import { Landmark, Link2, Scale } from 'lucide-react'
import wordmarkOnDark from '@/assets/brand/talvrin-wordmark-on-dark.svg'
import wordmarkOnLight from '@/assets/brand/talvrin-wordmark-on-light.svg'

interface AuthLayoutProps {
  title: string
  subtitle: string
  children: React.ReactNode
  /** Rendered under the form — usually the link to the opposite flow. */
  footer?: React.ReactNode
}

/** Accurate to the spec, not marketing claims we can't stand behind. */
const PROMISES = [
  {
    Icon: Landmark,
    title: 'Official sources only',
    body: 'Exchanges, regulators, central banks and issuer filings — not open-web commentary.',
  },
  {
    Icon: Link2,
    title: 'Every figure traceable',
    body: 'Each material number resolves to the document it came from. If it can’t be sourced, it isn’t shown.',
  },
  {
    Icon: Scale,
    title: 'Evidence, not advice',
    body: 'No buy, sell or hold. You get the verified facts and reach your own view.',
  },
]

const LEGAL = [
  { to: '/privacy', label: 'Privacy' },
  { to: '/terms', label: 'Terms' },
  { to: '/help', label: 'Help' },
  { to: '/contact', label: 'Contact' },
]

/** Shared shell for sign in / sign up / forgot password. */
export default function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: AuthLayoutProps) {
  return (
    <div className="flex min-h-screen bg-background">
      {/* ---------------- Form ---------------- */}
      <div className="relative flex w-full flex-col px-6 py-8 lg:w-[55%] lg:px-14 lg:py-10">
        <div aria-hidden className="app-ambient lg:hidden" />

        <Link
          to="/"
          aria-label="Talvrin home"
          className="relative z-10 self-start rounded-lg transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-offset-4 focus-visible:ring-offset-background"
        >
          <img src={wordmarkOnDark} alt="Talvrin" className="brand-on-dark h-8 w-auto" />
          <img src={wordmarkOnLight} alt="Talvrin" className="brand-on-light h-8 w-auto" />
        </Link>

        {/* The form block is optically centred in the space left over, rather
            than in the column — otherwise the wordmark above drags it low. */}
        <div className="relative z-10 flex flex-1 items-center justify-center py-12">
          <div className="w-full max-w-[384px] animate-rise">
            <h1 className="text-[27px] font-semibold leading-[1.15] tracking-[-0.02em]">
              {title}
            </h1>
            <p className="mt-2.5 text-[14px] leading-relaxed text-muted-foreground">
              {subtitle}
            </p>

            <div className="mt-8">{children}</div>

            {footer && (
              <div className="mt-7 border-t border-border/60 pt-6 text-[13.5px] text-muted-foreground">
                {footer}
              </div>
            )}
          </div>
        </div>

        {/* Pinned to the bottom of the column so it reads as page furniture,
            not as part of the form. */}
        <div className="relative z-10 flex flex-wrap items-center gap-x-5 gap-y-2 text-[11.5px] text-muted-foreground/60">
          {LEGAL.map((l) => (
            <Link
              key={l.to}
              to={l.to}
              className="rounded transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
            >
              {l.label}
            </Link>
          ))}
          <span className="ml-auto hidden sm:inline">
            Prototype — sessions are held locally on this device.
          </span>
        </div>
      </div>

      {/* ---------------- Brand banner ----------------
          Hidden below lg: at tablet width and under, two columns would
          squeeze the form rather than support it. */}
      <aside className="auth-banner relative hidden w-[45%] flex-col justify-start px-10 pb-10 pt-20 lg:flex xl:px-14 xl:pb-14 xl:pt-24">
        <div className="relative z-10 max-w-[400px]">
          <h2 className="text-[26px] font-semibold leading-[1.2] tracking-[-0.02em] text-white xl:text-[30px]">
            Reach a defensible view faster.
          </h2>
          <p className="mt-3.5 text-[14px] leading-relaxed text-white/65 xl:text-[15px]">
            Source-linked research and monitoring for public markets.
          </p>

          <ul className="mt-10 flex flex-col gap-6">
            {PROMISES.map(({ Icon, title: t, body }) => (
              <li key={t} className="flex gap-4">
                <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/[0.08] text-white/90 ring-1 ring-inset ring-white/10 backdrop-blur-sm">
                  <Icon className="h-[17px] w-[17px]" />
                </span>
                <span className="min-w-0">
                  <span className="block text-[14px] font-medium leading-snug text-white">
                    {t}
                  </span>
                  <span className="mt-1 block text-[13px] leading-relaxed text-white/55">
                    {body}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <p className="absolute inset-x-10 bottom-10 z-10 text-[11.5px] leading-relaxed text-white/40 xl:inset-x-14 xl:bottom-14">
          Talvrin does not give investment advice. A Zoiko Group platform.
        </p>
      </aside>
    </div>
  )
}
