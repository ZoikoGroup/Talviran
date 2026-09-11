import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import wordmarkOnDark from '@/assets/brand/talvrin-wordmark-on-dark.svg'
import wordmarkOnLight from '@/assets/brand/talvrin-wordmark-on-light.svg'

interface PageLayoutProps {
  title: string
  /** Shown under the title — a standfirst, or the revision state. */
  meta?: string
  children: React.ReactNode
}

/** Shared shell for the public content pages. */
export default function PageLayout({ title, meta, children }: PageLayoutProps) {
  return (
    <div className="relative flex min-h-screen flex-col bg-background">
      <div aria-hidden className="app-ambient" />

      <header className="relative z-10 border-b border-border/70">
        <div className="mx-auto flex max-w-3xl items-center gap-4 px-5 py-4">
          <Link to="/" aria-label="Talvrin home" className="shrink-0">
            <img src={wordmarkOnDark} alt="Talvrin" className="brand-on-dark h-7 w-auto" />
            <img src={wordmarkOnLight} alt="Talvrin" className="brand-on-light h-7 w-auto" />
          </Link>

          <Link
            to="/"
            className="ml-auto flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to Talvrin
          </Link>
        </div>
      </header>

      <main className="relative z-10 flex-1">
        <div className="mx-auto max-w-3xl px-5 pb-20 pt-10">
          <h1 className="text-[30px] font-semibold leading-tight tracking-tight">
            {title}
          </h1>
          {meta && <p className="mt-2 text-[13px] text-muted-foreground">{meta}</p>}
          <div className="mt-9">{children}</div>
        </div>
      </main>

      <footer className="relative z-10 border-t border-border/70">
        <div className="mx-auto flex max-w-3xl flex-wrap items-center gap-x-5 gap-y-2 px-5 py-5 text-[12.5px] text-muted-foreground">
          <span>© {new Date().getFullYear()} Zoiko Group</span>
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
          <span className="ml-auto text-muted-foreground/70">
            Talvrin does not give investment advice.
          </span>
        </div>
      </footer>
    </div>
  )
}

/* ------------------------------------------------------------------
   Prose building blocks, so the content pages stay consistent
   ------------------------------------------------------------------ */

export function Section({
  id,
  heading,
  children,
}: {
  id: string
  heading: string
  children: React.ReactNode
}) {
  return (
    <section id={id} className="scroll-mt-6 border-t border-border/70 pt-8 first:border-0 first:pt-0">
      <h2 className="text-[18px] font-semibold tracking-tight">{heading}</h2>
      <div className="mt-3 flex flex-col gap-3.5 text-[14.5px] leading-[1.75] text-muted-foreground">
        {children}
      </div>
    </section>
  )
}

/** Two-column rule list — how the specs themselves express most policy. */
export function RuleTable({ rows }: { rows: [string, string][] }) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      {rows.map(([term, rule]) => (
        <div
          key={term}
          className="flex flex-col gap-1 border-b border-border px-4 py-3 last:border-b-0 sm:flex-row sm:gap-4"
        >
          <span className="shrink-0 text-[13.5px] font-medium text-foreground sm:basis-[38%]">
            {term}
          </span>
          <span className="text-[13.5px] leading-relaxed">{rule}</span>
        </div>
      ))}
    </div>
  )
}

export function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="flex flex-col gap-2.5">
      {items.map((t) => (
        <li key={t} className="flex gap-2.5">
          <span aria-hidden className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-muted-foreground/60" />
          <span>{t}</span>
        </li>
      ))}
    </ul>
  )
}
