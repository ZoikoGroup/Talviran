import { useState } from 'react'
import {
  ShieldCheck,
  Link2,
  FileText,
  BookOpen,
  Table2,
  ChevronDown,
  Info,
} from 'lucide-react'
import { cn } from '@/lib/utils'
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

function Evidence({ citations }: { citations: Citation[] }) {
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
        </div>
      )}
    </div>
  )
}

export default function Message({
  role,
  text,
  facts,
  citations = [],
  note,
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
      <div className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-purple-500 text-[11.5px] font-bold text-white shadow-lg shadow-indigo-500/25">
        T
      </div>

      <div className="min-w-0 flex-1 pt-0.5">
        <div className="mb-1.5 text-[13px] font-semibold">Talvrin</div>
        <div className="whitespace-pre-wrap break-words text-[14.75px] leading-relaxed">
          <RichText>{text}</RichText>
        </div>

        {facts && <Facts {...facts} />}
        {citations.length > 0 && <Evidence citations={citations} />}

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
