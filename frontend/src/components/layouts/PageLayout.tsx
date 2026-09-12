import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { cn } from '@/lib/utils'
import wordmarkOnDark from '@/assets/brand/talvrin-wordmark-on-dark.svg'
import wordmarkOnLight from '@/assets/brand/talvrin-wordmark-on-light.svg'

export interface TocEntry {
  id: string
  label: string
}

interface PageLayoutProps {
  title: string
  /** Shown under the title — a standfirst, or the revision state. */
  meta?: string
  /** When given, a sticky contents rail appears alongside on large screens. */
  toc?: TocEntry[]
  children: React.ReactNode
}

const FOOTER_LINKS = [
  { to: '/privacy', label: 'Privacy' },
  { to: '/terms', label: 'Terms' },
  { to: '/help', label: 'Help' },
  { to: '/contact', label: 'Contact' },
]

/**
 * Tracks which section is in view so the contents rail can mark it.
 *
 * `rootMargin` pulls the detection band up to the top third of the viewport:
 * without it, the entry that "intersects" is whatever is scrolling in at the
 * bottom, and the highlight runs ahead of what you are actually reading.
 */
function useActiveSection(ids: string[]): string | null {
  const [active, setActive] = useState<string | null>(ids[0] ?? null)

  useEffect(() => {
    if (ids.length === 0 || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
        if (visible[0]) setActive(visible[0].target.id)
      },
      { rootMargin: '-80px 0px -66% 0px', threshold: 0 }
    )
    for (const id of ids) {
      const el = document.getElementById(id)
      if (el) observer.observe(el)
    }
    return () => observer.disconnect()
  }, [ids])

  return active
}

/** Shared shell for the public content pages. */
export default function PageLayout({
  title,
  meta,
  toc,
  children,
}: PageLayoutProps) {
  const active = useActiveSection(toc?.map((t) => t.id) ?? [])

  return (
    <div className="relative flex min-h-screen flex-col bg-background">
      <div aria-hidden className="app-ambient" />

      {/* Sticky so the way back is always one click away on a long policy. */}
      <header className="sticky top-0 z-20 border-b border-border/60 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-6 py-3.5">
          <Link
            to="/"
            aria-label="Talvrin home"
            className="shrink-0 rounded transition-opacity hover:opacity-80"
          >
            <img src={wordmarkOnDark} alt="Talvrin" className="brand-on-dark h-7 w-auto" />
            <img src={wordmarkOnLight} alt="Talvrin" className="brand-on-light h-7 w-auto" />
          </Link>

          <Link
            to="/"
            className="ml-auto flex items-center gap-1.5 rounded-full border border-border/70 px-3.5 py-1.5 text-[13px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to Talvrin
          </Link>
        </div>
      </header>

      <main className="relative z-10 flex-1">
        <div className="mx-auto max-w-6xl px-6 pb-24 pt-12">
          <header className="max-w-3xl">
            <h1 className="text-[34px] font-semibold leading-[1.12] tracking-[-0.025em]">
              {title}
            </h1>
            {meta && (
              <p className="mt-3 text-[13.5px] leading-relaxed text-muted-foreground">
                {meta}
              </p>
            )}
          </header>

          <div className="mt-12 flex gap-14">
            <div className="min-w-0 max-w-3xl flex-1">{children}</div>

            {toc && toc.length > 0 && (
              <nav
                aria-label="On this page"
                className="sticky top-24 hidden h-fit w-52 shrink-0 lg:block"
              >
                <p className="mb-3 text-[10.5px] font-semibold uppercase tracking-widest text-muted-foreground/70">
                  On this page
                </p>
                <ul className="flex flex-col gap-0.5 border-l border-border">
                  {toc.map((t) => (
                    <li key={t.id}>
                      <a
                        href={`#${t.id}`}
                        aria-current={active === t.id ? 'true' : undefined}
                        className={cn(
                          '-ml-px block border-l py-1.5 pl-4 text-[13px] leading-snug transition-colors',
                          active === t.id
                            ? 'border-primary font-medium text-foreground'
                            : 'border-transparent text-muted-foreground hover:border-border hover:text-foreground'
                        )}
                      >
                        {t.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </nav>
            )}
          </div>
        </div>
      </main>

      <footer className="relative z-10 border-t border-border/60">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-6 py-6 text-[12.5px] text-muted-foreground">
          <span>© {new Date().getFullYear()} Zoiko Group</span>
          {FOOTER_LINKS.map((l) => (
            <Link
              key={l.to}
              to={l.to}
              className="rounded transition-colors hover:text-foreground"
            >
              {l.label}
            </Link>
          ))}
          <span className="ml-auto text-muted-foreground/60">
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
    <section
      id={id}
      // Clears the sticky header when jumped to from the contents rail.
      className="scroll-mt-24 border-t border-border/60 pt-10 first:border-0 first:pt-0"
    >
      <h2 className="text-[19px] font-semibold tracking-[-0.015em]">{heading}</h2>
      <div className="mt-4 flex flex-col gap-4 text-[14.5px] leading-[1.75] text-muted-foreground">
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
          className="flex flex-col gap-1 border-b border-border px-4 py-3.5 last:border-b-0 sm:flex-row sm:gap-5"
        >
          <span className="shrink-0 text-[13.5px] font-medium leading-relaxed text-foreground sm:basis-[38%]">
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
    <ul className="flex flex-col gap-3">
      {items.map((t) => (
        <li key={t} className="flex gap-3">
          <span
            aria-hidden
            className="mt-[10px] h-1 w-1 shrink-0 rounded-full bg-muted-foreground/50"
          />
          <span>{t}</span>
        </li>
      ))}
    </ul>
  )
}
