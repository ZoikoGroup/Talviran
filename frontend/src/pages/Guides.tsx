import { useState, useMemo, useEffect } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import {
  Search,
  CheckCircle2,
  AlertTriangle,
  Play,
  Copy,
  Check,
  ArrowRight,
  Clock,
} from 'lucide-react'
import PageLayout from '@/components/layouts/PageLayout'
import { GUIDE_TOPICS, type GuideExampleQuery } from '@/data/guidesData'
import { cn } from '@/lib/utils'

function ExampleQueryCard({
  example,
  onRun,
}: {
  example: GuideExampleQuery
  onRun: (query: string) => void
}) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(example.query)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="rounded-xl border border-border/80 bg-background/50 p-4 transition-all hover:border-primary/40 hover:bg-card/90">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="rounded-md bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary">
            {example.model}
          </span>
          <span className="text-[11px] font-medium text-muted-foreground">
            {example.outputType}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={handleCopy}
            title="Copy query text"
            className="flex h-7 items-center gap-1 rounded-lg border border-border/60 px-2 text-[11.5px] font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            {copied ? (
              <>
                <Check className="h-3 w-3 text-emerald-500" />
                <span>Copied</span>
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" />
                <span>Copy</span>
              </>
            )}
          </button>
          <button
            onClick={() => onRun(example.query)}
            title="Run query in research chat"
            className="flex h-7 items-center gap-1 rounded-lg bg-primary/90 px-2.5 text-[11.5px] font-medium text-primary-foreground shadow-sm transition-all hover:bg-primary active:scale-95"
          >
            <Play className="h-3 w-3 fill-current" />
            <span>Try in Chat</span>
          </button>
        </div>
      </div>

      <h4 className="mt-2 text-[13.5px] font-semibold text-foreground">
        {example.title}
      </h4>
      <p className="mt-1 text-[12.5px] text-muted-foreground">
        {example.description}
      </p>

      <div className="mt-3 rounded-lg border border-border/50 bg-black/20 p-2.5 font-mono text-[12px] leading-relaxed text-foreground/90">
        “{example.query}”
      </div>
    </div>
  )
}

export default function Guides() {
  const navigate = useNavigate()
  const location = useLocation()

  // Read ?topic= from query string if present
  const getInitialTopicId = () => {
    const params = new URLSearchParams(location.search)
    const topicParam = params.get('topic')
    if (topicParam && GUIDE_TOPICS.some((t) => t.id === topicParam || t.slug === topicParam)) {
      const match = GUIDE_TOPICS.find((t) => t.id === topicParam || t.slug === topicParam)
      return match ? match.id : GUIDE_TOPICS[0].id
    }
    return GUIDE_TOPICS[0].id
  }

  const [selectedTopicId, setSelectedTopicId] = useState<string>(getInitialTopicId)
  const [searchQuery, setSearchQuery] = useState('')

  // Sync state if user navigates to /guides?topic=xyz
  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const topicParam = params.get('topic')
    if (topicParam) {
      const match = GUIDE_TOPICS.find((t) => t.id === topicParam || t.slug === topicParam)
      if (match) setSelectedTopicId(match.id)
    }
  }, [location.search])

  const activeTopic = useMemo(() => {
    return GUIDE_TOPICS.find((t) => t.id === selectedTopicId) || GUIDE_TOPICS[0]
  }, [selectedTopicId])

  const filteredTopics = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return GUIDE_TOPICS
    return GUIDE_TOPICS.filter(
      (topic) =>
        topic.title.toLowerCase().includes(q) ||
        topic.summary.toLowerCase().includes(q) ||
        topic.sections.some(
          (s) =>
            s.title.toLowerCase().includes(q) ||
            s.content.some((c) => c.toLowerCase().includes(q))
        )
    )
  }, [searchQuery])

  const handleRunInChat = (queryText: string) => {
    sessionStorage.setItem('talvrin_pending_prompt', queryText)
    navigate('/#research')
  }

  const tocEntries = useMemo(() => {
    return activeTopic.sections.map((s) => ({
      id: s.id,
      label: s.title,
    }))
  }, [activeTopic])

  return (
    <PageLayout
      title="Talvrin Guides & Documentation"
      meta="In-depth walkthroughs on source-grounded research, deterministic market math, and querying techniques."
      toc={tocEntries}
    >
      {/* Top Search & Category Filter */}
      <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search guides, query patterns, and formulas…"
            aria-label="Search guides"
            className="w-full rounded-xl border border-border bg-card/60 py-2.5 pl-10 pr-3.5 text-[14px] outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-ring/70 focus:ring-2 focus:ring-ring/20"
          />
        </div>
        <Link
          to="/help"
          className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-border bg-card/80 px-4 py-2.5 text-[13px] font-medium text-foreground transition-colors hover:bg-accent"
        >
          <span>Frequently Asked Questions</span>
          <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
        </Link>
      </div>

      {/* Guide Category Selection Pill Cards */}
      {filteredTopics.length === 0 ? (
        <div className="mb-10 rounded-xl border border-border bg-card p-6 text-center text-[13.5px] text-muted-foreground">
          No guides match “{searchQuery}”. Try searching for “gilt”, “duration”, “formula”, or “policy”.
        </div>
      ) : (
        <div className="mb-10 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {filteredTopics.map((topic) => {
            const isSelected = topic.id === activeTopic.id
            return (
              <button
                key={topic.id}
                onClick={() => setSelectedTopicId(topic.id)}
                className={cn(
                  'flex flex-col items-start rounded-xl border p-3.5 text-left transition-all',
                  isSelected
                    ? 'border-primary bg-primary/5 ring-1 ring-primary/40 shadow-sm'
                    : 'border-border bg-card/50 hover:border-border/80 hover:bg-card'
                )}
              >
                <div className="flex w-full items-center justify-between">
                  <span className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {topic.category}
                  </span>
                  <span className="flex items-center gap-1 text-[11px] text-muted-foreground/80">
                    <Clock className="h-3 w-3" />
                    {topic.readTimeMinutes}m
                  </span>
                </div>
                <h3 className="mt-1.5 text-[13.5px] font-semibold leading-snug text-foreground">
                  {topic.title}
                </h3>
                <p className="mt-1 line-clamp-2 text-[12px] text-muted-foreground leading-relaxed">
                  {topic.summary}
                </p>
              </button>
            )
          })}
        </div>
      )}

      {/* Active Guide Content */}
      <article className="rounded-2xl border border-border bg-card p-6 sm:p-8">
        <div className="border-b border-border/80 pb-6">
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-[11.5px] font-semibold text-primary">
              {activeTopic.category}
            </span>
            <span className="text-[12px] text-muted-foreground">
              • {activeTopic.readTimeMinutes} min read
            </span>
          </div>
          <h2 className="mt-2 text-[26px] font-bold tracking-tight text-foreground">
            {activeTopic.title}
          </h2>
          <p className="mt-2 text-[14px] leading-relaxed text-muted-foreground">
            {activeTopic.summary}
          </p>
        </div>

        {/* Sections */}
        <div className="mt-8 flex flex-col gap-10">
          {activeTopic.sections.map((section) => (
            <section key={section.id} id={section.id} className="scroll-mt-28">
              <div className="flex items-center gap-2.5">
                <h3 className="text-[18px] font-semibold tracking-tight text-foreground">
                  {section.title}
                </h3>
                {section.badge && (
                  <span className="rounded-md border border-border bg-accent/50 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                    {section.badge}
                  </span>
                )}
              </div>

              <div className="mt-3 flex flex-col gap-3 text-[14px] leading-relaxed text-muted-foreground">
                {section.content.map((paragraph, idx) => (
                  <p key={idx}>{paragraph}</p>
                ))}
              </div>

              {/* Key points checklist */}
              {section.keyPoints && section.keyPoints.length > 0 && (
                <div className="mt-4 rounded-xl border border-border/70 bg-accent/30 p-4">
                  <p className="text-[12px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Core Doctrine Takeaways
                  </p>
                  <ul className="mt-2.5 flex flex-col gap-2">
                    {section.keyPoints.map((pt, idx) => (
                      <li key={idx} className="flex items-start gap-2.5 text-[13px] text-foreground/90 leading-snug">
                        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                        <span>{pt}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Caution Callout */}
              {section.caution && (
                <div className="mt-4 flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-[13px] text-amber-200">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
                  <div>
                    <span className="font-semibold text-amber-300">Compliance Perimeter: </span>
                    <span>{section.caution}</span>
                  </div>
                </div>
              )}

              {/* Example Queries (if cookbook) */}
              {section.exampleQueries && section.exampleQueries.length > 0 && (
                <div className="mt-5 grid grid-cols-1 gap-3.5 sm:grid-cols-2">
                  {section.exampleQueries.map((ex, idx) => (
                    <ExampleQueryCard
                      key={idx}
                      example={ex}
                      onRun={handleRunInChat}
                    />
                  ))}
                </div>
              )}
            </section>
          ))}
        </div>
      </article>

      {/* Footer Banner */}
      <div className="mt-10 flex flex-col items-center justify-between gap-4 rounded-2xl border border-border bg-card/60 p-6 sm:flex-row">
        <div>
          <h4 className="text-[15px] font-semibold text-foreground">Need help formulating a complex calculation?</h4>
          <p className="mt-1 text-[13px] text-muted-foreground">
            Our documentation is backed by institutional golden fixtures. You can inspect exact formulas or reach our desk.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/help"
            className="rounded-xl border border-border px-4 py-2 text-[13px] font-medium transition-colors hover:bg-accent"
          >
            FAQ
          </Link>
          <Link
            to="/contact"
            className="rounded-xl bg-primary px-4 py-2 text-[13px] font-medium text-primary-foreground shadow transition-all hover:bg-primary/90"
          >
            Contact Desk
          </Link>
        </div>
      </div>
    </PageLayout>
  )
}
