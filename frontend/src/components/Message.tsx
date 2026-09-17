import { useEffect, useState } from 'react'
import {
  ShieldCheck,
  Link2,
  FileText,
  BookOpen,
  Table2,
  ChevronDown,
  Info,
  Loader2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { getResearchEvidence, type EvidenceItem } from '@/lib/api'
import brandIcon from '@/assets/brand/talvrin-icon.svg'
import type {
  ChatMessage,
  Citation,
  FactTable,
  Freshness,
} from '@/data/mockReply'

const CITE_ICON = { doc: FileText, book: BookOpen, link: Link2 } as const

const PILL_STYLE: Record<Freshness, string> = {
  CURRENT: 'bg-fresh/15 text-fresh',
  DELAYED: 'bg-delayed/15 text-delayed',
  STALE: 'bg-stale/15 text-stale',
  UNAVAILABLE: 'bg-unavailable/15 text-unavailable',
  SOURCE: 'bg-secondary text-muted-foreground',
}

/** Render **bold** spans without pulling in a markdown dependency. */
function RichText({ children }: { children: string }) {
  return (
    <>
      {children.split(/(\*\*[^*]+\*\*)/g).map((p, i) =>
        p.startsWith('**') && p.endsWith('**') ? (
          <strong key={i} className="font-semibold">
            {p.slice(2, -2)}
          </strong>
        ) : (
          <span key={i}>{p}</span>
        )
      )}
    </>
  )
}

function Facts({ title, rows }: FactTable) {
  return (
    <div className="mt-3.5 overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex items-center gap-2 border-b border-border bg-secondary/60 px-3.5 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        <Table2 className="h-3.5 w-3.5" />
        {title}
      </div>
      {rows.map(([k, v]) => (
        <div
          key={k}
          className="flex items-baseline gap-3 border-b border-border px-3.5 py-2.5 text-[13.5px] last:border-b-0"
        >
          <span className="basis-[42%] text-muted-foreground">{k}</span>
          <span className="font-mono text-[13px] font-medium">{v}</span>
        </div>
      ))}
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
      <div className="flex flex-col gap-1.5">
        {state.items.map((item, i) => (
          <div key={i} className="flex flex-wrap items-baseline gap-x-2 text-[12px]">
            <span className="font-mono text-muted-foreground">{item.metricId ?? item.kind}</span>
            {item.basis === 'MODEL_IMPLIED' && (
              <span className="rounded bg-secondary px-1 py-0.5 text-[9.5px] font-bold uppercase tracking-wider text-muted-foreground">
                estimate
              </span>
            )}
            {item.asOf && <span className="text-muted-foreground/60">as of {item.asOf}</span>}
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
    <div className="mt-3.5 overflow-hidden rounded-xl border border-border bg-card">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3.5 py-2.5 text-[11.5px] font-semibold text-muted-foreground transition-colors hover:bg-secondary/60"
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
                className="flex items-center gap-2.5 border-b border-border px-3.5 py-2.5 text-[13px] last:border-b-0"
              >
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-primary/15 text-primary">
                  <Ico className="h-3.5 w-3.5" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate">{c.label}</span>
                  {c.meta && (
                    <span className="mt-0.5 block text-[11.5px] text-muted-foreground/70">
                      {c.meta}
                    </span>
                  )}
                </span>
                <span
                  className={cn(
                    'shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider',
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

export default function Message({
  role,
  text,
  model,
  facts,
  citations = [],
  note,
  messageId,
}: ChatMessage) {
  if (role === 'user') {
    return (
      <div className="mb-6 flex animate-rise justify-end">
        <div className="max-w-[78%] whitespace-pre-wrap break-words rounded-2xl rounded-br-sm border border-border bg-secondary px-4 py-2.5 text-[14.75px] leading-relaxed">
          {text}
        </div>
      </div>
    )
  }

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
          <RichText>{text}</RichText>
        </div>

        {facts && <Facts {...facts} />}
        {citations.length > 0 && <Evidence citations={citations} messageId={messageId} />}

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
