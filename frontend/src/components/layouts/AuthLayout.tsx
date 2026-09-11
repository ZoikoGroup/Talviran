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
      <div className="relative flex w-full flex-col px-5 py-10 lg:w-[55%] lg:px-12">
        <div aria-hidden className="app-ambient lg:hidden" />

        <Link to="/" className="relative z-10 self-start" aria-label="Talvrin home">
          <img src={wordmarkOnDark} alt="Talvrin" className="brand-on-dark h-8 w-auto" />
          <img src={wordmarkOnLight} alt="Talvrin" className="brand-on-light h-8 w-auto" />
        </Link>

        <div className="relative z-10 flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[380px]">
            <h1 className="text-[26px] font-semibold leading-tight tracking-tight">
              {title}
            </h1>
            <p className="mt-2 text-[13.5px] leading-relaxed text-muted-foreground">
              {subtitle}
            </p>

            <div className="mt-7">{children}</div>

            {footer && (
              <div className="mt-6 text-[13.5px] text-muted-foreground">{footer}</div>
            )}

            <p className="mt-8 text-[11.5px] leading-relaxed text-muted-foreground/70">
              Prototype — no authentication backend is connected yet. Sessions
              are held locally on this device only.
            </p>

            <div className="mt-4 flex gap-4 text-[11.5px] text-muted-foreground/70">
              <Link to="/privacy" className="transition-colors hover:text-foreground">
                Privacy
              </Link>
              <Link to="/terms" className="transition-colors hover:text-foreground">
                Terms
              </Link>
              <Link to="/help" className="transition-colors hover:text-foreground">
                Help
              </Link>
              <Link to="/contact" className="transition-colors hover:text-foreground">
                Contact
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* ---------------- Brand banner ----------------
          Hidden below lg: at tablet width and under, two columns would
          squeeze the form rather than support it. */}
      <aside className="auth-banner relative hidden w-[45%] flex-col justify-between p-8 lg:flex xl:p-11">
        <img
          src={wordmarkOnDark}
          alt=""
          aria-hidden
          className="relative z-10 h-8 w-auto self-start opacity-95"
        />

        <div className="relative z-10 max-w-[400px]">
          <h2 className="text-[25px] font-semibold leading-[1.22] tracking-tight text-white xl:text-[29px]">
            Reach a defensible view faster.
          </h2>
          <p className="mt-3 text-[13.5px] leading-relaxed text-white/70 xl:text-[14.5px]">
            Source-linked research and monitoring for public markets.
          </p>

          <ul className="mt-8 flex flex-col gap-[18px] xl:mt-9 xl:gap-5">
            {PROMISES.map(({ Icon, title: t, body }) => (
              <li key={t} className="flex gap-3.5">
                <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-white/10 text-white ring-1 ring-inset ring-white/15">
                  <Icon className="h-4 w-4" />
                </span>
                <span className="min-w-0">
                  <span className="block text-[14px] font-medium text-white">{t}</span>
                  <span className="mt-0.5 block text-[13px] leading-relaxed text-white/65">
                    {body}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative z-10 text-[11.5px] text-white/45">
          Talvrin does not give investment advice. A Zoiko Group platform.
        </p>
      </aside>
    </div>
  )
}
