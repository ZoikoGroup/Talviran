import { useEffect, useState, lazy, Suspense } from 'react'
import {
  ShieldCheck,
  Link2,
  FileText,
  BookOpen,
  ChevronDown,
  Info,
  Loader2,
  ExternalLink,
  Tag,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { getResearchEvidence, type EvidenceItem } from '@/lib/api'
import brandIcon from '@/assets/brand/talvrin-icon.svg'
import type {
  ChatMessage,
  Citation,
  Freshness,
} from '@/data/mockReply'

const Facts = lazy(() => import('./Facts'))

const CITE_ICON = { doc: FileText, book: BookOpen, link: Link2 } as const

const PILL_STYLE: Record<Freshness, string> = {
  CURRENT: 'bg-fresh/15 text-fresh',
  DELAYED: 'bg-delayed/15 text-delayed',
  STALE: 'bg-stale/15 text-stale',
  UNAVAILABLE: 'bg-unavailable/15 text-unavailable',
  SOURCE: 'bg-secondary text-muted-foreground',
}

/** Render headings (###, ##, #), bullets, and **bold** spans without breaking into raw markdown. */
function InlineFormatted({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\*\*[^*]+\*\*)/g).map((p, i) =>
        p.startsWith('**') && p.endsWith('**') ? (
          <strong key={i} className="font-semibold text-foreground">
            {p.slice(2, -2)}
          </strong>
        ) : (
          <span key={i}>{p}</span>
        )
      )}
    </>
  )
}

function RichText({ children }: { children: string }) {
  const lines = children.split('\n')

  return (
    <div className="space-y-2">
      {lines.map((line, idx) => {
        const trimmed = line.trim()
        if (!trimmed) {
          return <div key={idx} className="h-1.5" />
        }

        // Headings: ### H3, ## H2, # H1
        const h3Match = line.match(/^###\s+(.*)$/)
        if (h3Match) {
          return (
            <h3 key={idx} className="pt-1.5 pb-1 text-[15px] font-bold tracking-tight text-foreground/95">
              <InlineFormatted text={h3Match[1]} />
            </h3>
          )
        }

        const h2Match = line.match(/^##\s+(.*)$/)
        if (h2Match) {
          return (
            <h2 key={idx} className="pt-2 pb-1 text-[16px] font-bold tracking-tight text-foreground">
              <InlineFormatted text={h2Match[1]} />
            </h2>
          )
        }

        const h1Match = line.match(/^#\s+(.*)$/)
        if (h1Match) {
          return (
            <h1 key={idx} className="pt-2.5 pb-1 text-[17px] font-extrabold tracking-tight text-foreground">
              <InlineFormatted text={h1Match[1]} />
            </h1>
          )
        }

        // Unordered lists: • or - or *
        const bulletMatch = line.match(/^([•\-\*]|\d+\.)\s+(.*)$/)
        if (bulletMatch) {
          return (
            <div key={idx} className="flex items-start gap-2 pl-1 leading-relaxed">
              <span className="select-none text-muted-foreground/80">•</span>
              <div className="flex-1">
                <InlineFormatted text={bulletMatch[2]} />
              </div>
            </div>
          )
        }

        return (
          <p key={idx} className="leading-relaxed">
            <InlineFormatted text={line} />
          </p>
        )
      })}
    </div>
  )
}



/** The resolved fact/calculation behind a citation - fetched on demand from
 * GET /research/{id}/evidence, not embedded in the reply itself (that
 * endpoint didn't exist when the citation list was first built). Only
 * fetched once, the first time the panel opens, for a message that came
 * from the real backend (mock replies have no messageId to fetch with). */
function RawEvidence({ messageId }: { messageId: string }) {
  const [state, setState] = useState<
    { status: 'loading' } | { status: 'error' } | { status: 'ready'; items: EvidenceItem[] }
  >({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    getResearchEvidence(messageId)
      .then((detail) => {
        if (!cancelled) setState({ status: 'ready', items: detail.items })
      })
      .catch((err: unknown) => {
        // A message with no evidence bundle at all (e.g. an advice-redirect
        // reply) never renders this component in the first place - Evidence
        // only mounts once citations.length > 0 - so any failure here is a
        // genuine fetch problem, not the normal "nothing to show" case.
        if (!cancelled) {
          console.error('Failed to load evidence detail', err)
          setState({ status: 'error' })
        }
      })
    return () => {
      cancelled = true
    }
  }, [messageId])

  if (state.status === 'loading') {
    return (
      <div className="flex items-center gap-2 border-t border-border px-3.5 py-2.5 text-[12px] text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" />
        Loading resolved evidence…
      </div>
    )
  }

  if (state.status === 'error' || state.items.length === 0) {
    return null
  }

  return (
    <div className="border-t border-border bg-secondary/30 px-3.5 py-2.5">
      <div className="mb-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground/70">
        Resolved values
      </div>
      <div className="flex flex-col gap-2">
        {state.items.map((item, i) => (
          <div key={i} className="flex flex-col gap-0.5 text-[12px]">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-mono text-muted-foreground">{item.metricId ?? item.kind}</span>
              {item.basis === 'MODEL_IMPLIED' && (
                <span className="rounded bg-secondary px-1 py-0.5 text-[9.5px] font-bold uppercase tracking-wider text-muted-foreground">
                  estimate
                </span>
              )}
              {item.source && <span className="text-muted-foreground/60">{item.source}</span>}
            </div>
            {(item.effectiveTime || item.asOf) && (
              <div className="flex flex-wrap items-baseline gap-x-2 text-muted-foreground/60">
                {item.effectiveTime && <span>market-effective {item.effectiveTime}</span>}
                {item.asOf && <span>known to Talvrin {item.asOf}</span>}
              </div>
            )}
            {item.permittedUse && (
              <div className="text-muted-foreground/50">{item.permittedUse}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function Evidence({
  citations,
  messageId,
}: {
  citations: Citation[]
  messageId?: string
}) {
  const [open, setOpen] = useState(false)

  return (
    <div className="mt-3.5 animate-rise overflow-hidden rounded-xl border border-border bg-card shadow-sm transition-all hover:shadow-md">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3.5 py-2.5 text-[11.5px] font-semibold text-muted-foreground transition-all duration-200 hover:bg-secondary/80 hover:text-foreground active:scale-[0.99]"
      >
        <ShieldCheck className="h-3.5 w-3.5" />
        Evidence
        <span className="ml-auto flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground/70">
          {citations.length} source{citations.length === 1 ? '' : 's'}
          <ChevronDown
            className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-180')}
          />
        </span>
      </button>

      {open && (
        <div className="border-t border-border">
          {citations.map((c, i) => {
            const Ico = CITE_ICON[c.kind] ?? Link2
            return (
              <div
                key={i}
                className="group flex animate-in fade-in slide-in-from-top-2 items-center gap-2.5 border-b border-border px-3.5 py-2.5 text-[13px] transition-colors hover:bg-secondary/40 last:border-b-0"
                style={{ animationDelay: `${i * 60}ms` }}
              >
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-primary/15 text-primary transition-transform group-hover:scale-110">
                  <Ico className="h-3.5 w-3.5" />
                </span>
                <span className="min-w-0 flex-1">
                  {c.url ? (
                    <a href={c.url} target="_blank" rel="noreferrer" className="block truncate font-medium text-indigo-400 transition-colors hover:text-indigo-300 hover:underline">
                      {c.label}
                    </a>
                  ) : (
                    <span className="block truncate font-medium transition-colors group-hover:text-primary">{c.label}</span>
                  )}
                  {c.meta && (
                    <span className="mt-0.5 block text-[11.5px] text-muted-foreground/70 transition-colors group-hover:text-muted-foreground">
                      {c.meta}
                    </span>
                  )}
                </span>
                <span
                  className={cn(
                    'shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider transition-all group-hover:brightness-110',
                    PILL_STYLE[c.pill]
                  )}
                >
                  {c.pill}
                </span>
              </div>
            )
          })}
          {messageId && <RawEvidence messageId={messageId} />}
        </div>
      )}
    </div>
  )
}

interface MessageProps extends ChatMessage {
  isLatestAssistant?: boolean
}

export default function Message({
  role,
  text,
  model,
  facts,
  citations = [],
  note,
  messageId,
  taggedAsset,
  isLatestAssistant = false,
}: MessageProps) {
  let displayContent = text
  let parsedFacts = facts
  let parsedCitations = citations || []
  let effectiveTaggedAsset = taggedAsset || null

  // If text contains context header, extract it cleanly
  if (displayContent) {
    const contextMatch = displayContent.match(/^\[Context: Tagged Asset ([^(\]]+)(?:\(([^)]+)\))?[^\]]*\]\.?\s*(?:Query:\s*)?([\s\S]*)$/i)
    if (contextMatch) {
      if (!effectiveTaggedAsset) {
        effectiveTaggedAsset = {
          name: contextMatch[1].trim(),
          symbol: contextMatch[2] ? contextMatch[2].trim() : contextMatch[1].trim(),
        }
      }
      displayContent = contextMatch[3].trim()
    }

    const metaMatch = displayContent.match(/<!--METADATA\n([\s\S]*?)\n-->/)
    if (metaMatch) {
      try {
        const meta = JSON.parse(metaMatch[1])
        if (meta.facts && !parsedFacts) parsedFacts = meta.facts
        if (meta.citations && parsedCitations.length === 0) parsedCitations = meta.citations
        displayContent = displayContent.replace(/<!--METADATA\n[\s\S]*?\n-->/, '').trim()
      } catch (e) {
        console.error("Failed to parse metadata", e)
      }
    }
  }

  // ChatGPT-style typing streaming state for newly received assistant messages
  const [typedLength, setTypedLength] = useState(() => (isLatestAssistant ? 0 : displayContent.length))
  const isTyping = isLatestAssistant && typedLength < displayContent.length

  useEffect(() => {
    if (!isLatestAssistant) {
      setTypedLength(displayContent.length)
      return
    }

    if (typedLength < displayContent.length) {
      // Dynamic chunk size and interval: faster on long prose, natural pacing on short answers
      const remaining = displayContent.length - typedLength
      const step = remaining > 180 ? 5 : remaining > 80 ? 3 : 2
      const timer = setTimeout(() => {
        setTypedLength((prev) => Math.min(prev + step, displayContent.length))
      }, 16)
      return () => clearTimeout(timer)
    }
  }, [isLatestAssistant, typedLength, displayContent.length])

  if (role === 'user') {
    return (
      <div className="mb-6 flex flex-col items-end animate-rise">
        {effectiveTaggedAsset && (
          <div className="mb-1.5 flex items-center gap-1.5">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/20 px-2.5 py-0.5 text-[11px] font-medium text-primary shadow-xs">
              <Tag className="h-3 w-3" />
              <span>{effectiveTaggedAsset.name}</span>
              <span className="font-mono text-[10px] opacity-80">({effectiveTaggedAsset.symbol})</span>
            </span>
          </div>
        )}
        <div className="max-w-[78%] whitespace-pre-wrap break-words rounded-2xl rounded-br-sm border border-border bg-secondary px-4 py-2.5 text-[14.75px] leading-relaxed">
          {displayContent}
        </div>
      </div>
    )
  }

  const visibleText = displayContent.slice(0, typedLength)

  return (
    <div className="mb-7 flex animate-rise gap-3.5">
      <img
        src={brandIcon}
        alt=""
        className="h-7 w-7 shrink-0 rounded-lg shadow-lg shadow-indigo-500/25"
      />

      <div className="min-w-0 flex-1 pt-0.5">
        <div className="mb-1.5 flex items-baseline gap-2 text-[13px] font-semibold">
          Talvrin
          {model && (
            <span className="font-normal text-[11.5px] text-muted-foreground">
              {model}
            </span>
          )}
        </div>
        <div className="whitespace-pre-wrap break-words text-[14.75px] leading-relaxed">
          <RichText>{visibleText}</RichText>
          {isTyping && <span className="typing-cursor" aria-hidden="true" />}
        </div>

        {/* Immediate Trusted Primary Sources Link Bar */}
        {parsedCitations.some((c) => Boolean(c.url)) && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5 pt-2 border-t border-border/40">
            <span className="inline-flex items-center gap-1 text-[11.5px] font-semibold text-emerald-400 mr-1">
              <ShieldCheck className="h-3.5 w-3.5" />
              Trusted Sources:
            </span>
            {parsedCitations
              .filter((c) => Boolean(c.url))
              .map((c, i) => (
                <a
                  key={i}
                  href={c.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded-lg border border-border bg-card/80 hover:bg-card px-2.5 py-1 text-[11.5px] font-medium text-indigo-400 hover:text-indigo-300 hover:border-primary/50 transition shadow-2xs"
                >
                  <span>{c.label.split('—')[0].trim()}</span>
                  <ExternalLink className="h-2.5 w-2.5 opacity-70" />
                </a>
              ))}
          </div>
        )}

        {parsedCitations.length > 0 && <Evidence citations={parsedCitations} messageId={messageId} />}
        {parsedFacts && (
          <Suspense fallback={<div className="mt-3.5 h-[280px] animate-pulse rounded-xl bg-secondary/30" />}>
            <Facts {...parsedFacts} />
          </Suspense>
        )}

        {note && (
          <div className="mt-3 flex items-start gap-2.5 rounded-xl border border-primary/25 bg-primary/10 px-3 py-2.5 text-[12.25px] leading-relaxed text-muted-foreground">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
            <span>{note}</span>
          </div>
        )}
      </div>
    </div>
  )
}
