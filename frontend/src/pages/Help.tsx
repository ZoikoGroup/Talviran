import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown, Mail, Search } from 'lucide-react'
import PageLayout from '@/components/layouts/PageLayout'
import { ARTICLES, CATEGORIES, type Article } from '@/data/helpArticles'
import { SUPPORT_EMAIL } from '@/data/contact'
import { cn } from '@/lib/utils'

function Entry({ article }: { article: Article }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border-b border-border last:border-b-0">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-start gap-3 px-4 py-3.5 text-left transition-colors hover:bg-accent/50"
      >
        <ChevronDown
          className={cn(
            'mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform',
            open && 'rotate-180'
          )}
        />
        <span className="text-[14px] font-medium leading-relaxed">
          {article.question}
        </span>
      </button>

      {open && (
        <div className="flex flex-col gap-3 px-4 pb-4 pl-11 text-[13.5px] leading-[1.75] text-muted-foreground">
          {article.answer.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Help() {
  const [query, setQuery] = useState('')

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return ARTICLES
    return ARTICLES.filter(
      (a) =>
        a.question.toLowerCase().includes(q) ||
        a.answer.some((p) => p.toLowerCase().includes(q)) ||
        a.category.toLowerCase().includes(q)
    )
  }, [query])

  const grouped = CATEGORIES.map((c) => ({
    category: c,
    items: matches.filter((a) => a.category === c),
  })).filter((g) => g.items.length > 0)

  return (
    <PageLayout
      title="Help centre"
      meta="How Talvrin works, and what it deliberately won't do"
    >
      <div className="relative mb-8">
        <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search help…"
          aria-label="Search help"
          className="w-full rounded-xl border border-border bg-background/60 py-2.5 pl-10 pr-3.5 text-[14px] outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-ring/70 focus:ring-2 focus:ring-ring/20"
        />
      </div>

      {grouped.length === 0 ? (
        <div className="rounded-xl border border-border bg-card px-4 py-8 text-center">
          <p className="text-[14px] font-medium">No articles match “{query}”.</p>
          <p className="mx-auto mt-1.5 max-w-sm text-[13.5px] leading-relaxed text-muted-foreground">
            Try a different word, or{' '}
            <Link to="/contact" className="text-primary hover:underline">
              ask us directly
            </Link>
            .
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-8">
          {grouped.map(({ category, items }) => (
            <section key={category}>
              <h2 className="mb-2.5 text-[10.5px] font-semibold uppercase tracking-widest text-muted-foreground">
                {category}
              </h2>
              <div className="overflow-hidden rounded-xl border border-border bg-card">
                {items.map((a) => (
                  <Entry key={a.id} article={a} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      <div className="mt-10 flex flex-col gap-3 rounded-xl border border-border bg-card px-5 py-5 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <p className="text-[14px] font-medium">Still stuck?</p>
          <p className="mt-1 text-[13.5px] leading-relaxed text-muted-foreground">
            If a figure looks wrong, tell us — that matters more than anything
            else you could report.
          </p>
        </div>
        <a
          href={`mailto:${SUPPORT_EMAIL}`}
          className="inline-flex shrink-0 items-center gap-2 rounded-xl border border-border px-4 py-2.5 text-[13.5px] font-medium transition-colors hover:bg-accent"
        >
          <Mail className="h-4 w-4 text-primary" />
          {SUPPORT_EMAIL}
        </a>
      </div>
    </PageLayout>
  )
}
