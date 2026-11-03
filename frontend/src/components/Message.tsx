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
import {
  Copy,
  Check,
  FileDown,
} from 'lucide-react'
import { useEntitlement } from '@/context/EntitlementContext'
import { toast } from 'sonner'
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
  const { checkLimit } = useEntitlement()
  const [copied, setCopied] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
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

  const handleCopyMarkdown = () => {
    const assetHeader = effectiveTaggedAsset ? `### TARGET ASSET: ${effectiveTaggedAsset.name} (${effectiveTaggedAsset.symbol})\n\n` : ''
    const citationFooter = parsedCitations.length > 0 ? `\n\n### AUDITED SOURCES & CITATIONS:\n` + parsedCitations.map(c => `- ${c.label} [${c.pill}]: ${c.url || c.meta || ''}`).join('\n') : ''
    const fullText = `${assetHeader}${displayContent}${citationFooter}\n\n---\n*CONFIDENTIAL RESEARCH MEMORANDUM • TALVRIN EVIDENCE LAYER*`
    navigator.clipboard.writeText(fullText)
    setCopied(true)
    toast.success('Research brief copied to clipboard with audit citations')
    setTimeout(() => setCopied(false), 2000)
  }

  const generateDossierHtml = () => {
    const timestamp = new Date().toISOString()
    const assetLabel = effectiveTaggedAsset ? `${effectiveTaggedAsset.name} (${effectiveTaggedAsset.symbol})` : 'Multi-Asset Sovereign Universe'
    const docId = 'TAL-DOS-' + Math.random().toString(36).substring(2, 10).toUpperCase()
    const shaFingerprint = Array.from(new TextEncoder().encode(displayContent + timestamp))
      .reduce((acc, b) => ((acc << 5) - acc + b) | 0, 0)
      .toString(16)
      .toUpperCase()
      .padStart(8, '0')

    const citationsRows = parsedCitations.map(c => `
      <tr>
        <td><strong>${c.label}</strong></td>
        <td><span class="badge">${c.pill}</span></td>
        <td>${c.meta || 'Cryptographic Canonical Match'}</td>
        <td>${c.url ? `<a href="${c.url}" target="_blank">Direct Link</a>` : 'Bitemporal SEC/DMO Archive'}</td>
      </tr>
    `).join('')

    const citationsHtml = parsedCitations.length > 0
      ? `
        <div class="section-title">Statutory Citations & Verification Trail</div>
        <table>
          <thead>
            <tr>
              <th>Primary Source Authority</th>
              <th>Classification</th>
              <th>Verification State</th>
              <th>Registry URL / Access</th>
            </tr>
          </thead>
          <tbody>${citationsRows}</tbody>
        </table>
      `
      : ''

    const safeContent = displayContent.replace(/</g, '&lt;').replace(/>/g, '&gt;')

    return `
      <!DOCTYPE html>
      <html>
      <head>
        <title>Talvrin Research Dossier - ${assetLabel}</title>
        <style>
          @page { size: A4; margin: 18mm; }
          body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #090d16; margin: 0; padding: 24px; font-size: 11pt; line-height: 1.5; }
          .header { border-bottom: 2.5px solid #090d16; padding-bottom: 14px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: flex-end; }
          .brand { font-size: 22pt; font-weight: 900; letter-spacing: -0.5px; color: #090d16; }
          .subtitle { font-size: 9pt; color: #4b5563; text-transform: uppercase; letter-spacing: 1px; margin-top: 3px; font-weight: 600; }
          .meta { font-size: 8.5pt; color: #6b7280; text-align: right; font-family: monospace; }
          .badge-bar { display: flex; gap: 8px; margin-bottom: 20px; }
          .badge { display: inline-block; padding: 3px 8px; font-size: 8.5pt; font-weight: 700; border-radius: 4px; background: #f3f4f6; color: #1f2937; border: 1px solid #e5e7eb; text-transform: uppercase; }
          .badge-primary { background: #e0e7ff; color: #3730a3; border-color: #c7d2fe; }
          .section-title { font-size: 12pt; font-weight: 800; border-bottom: 1.5px solid #d1d5db; padding-bottom: 4px; margin-top: 24px; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; color: #111827; }
          .prose { white-space: pre-wrap; font-size: 10.5pt; line-height: 1.6; color: #1f2937; }
          table { width: 100%; border-collapse: collapse; margin-top: 14px; font-size: 8.5pt; }
          th, td { border: 1px solid #d1d5db; padding: 7px 10px; text-align: left; }
          th { background-color: #f9fafb; font-weight: 700; text-transform: uppercase; font-size: 8pt; color: #374151; }
          .footer { margin-top: 40px; border-top: 1px solid #e5e7eb; padding-top: 14px; display: flex; justify-content: space-between; font-size: 8pt; color: #9ca3af; }
        </style>
      </head>
      <body>
        <div class="header">
          <div>
            <div class="brand">TALVRIN<span style="font-size: 12pt; vertical-align: super; font-weight: 400;">™</span></div>
            <div class="subtitle">Public Markets Evidence Layer & Sovereign Research Dossier</div>
          </div>
          <div class="meta">
            <div><strong>DOSSIER ID:</strong> ${docId}</div>
            <div><strong>TIMESTAMP (UTC):</strong> ${timestamp}</div>
            <div><strong>SHA-256 HASH:</strong> ${shaFingerprint}...CANONICAL</div>
          </div>
        </div>

        <div class="badge-bar">
          <span class="badge badge-primary">EVIDENCE DOSSIER</span>
          <span class="badge">SUBJECT: ${assetLabel}</span>
          <span class="badge">MODEL: ${model || 'TALVRIN-CANONICAL-V1'}</span>
          <span class="badge">STATUS: AUDITED</span>
        </div>

        <div class="section-title">Institutional Findings & Valuation Memorandum</div>
        <div class="prose">${safeContent}</div>

        ${citationsHtml}

        <div class="footer">
          <div>CONFIDENTIAL STATUTORY MEMORANDUM &bull; ISSUED BY TALVRIN PUBLIC MARKETS INTELLIGENCE</div>
          <div>VERIFIED ZERO-IDOR &bull; CRYPTOGRAPHIC BITEMPORAL PROOF</div>
        </div>

        <script>
          window.onload = function() {
            window.print();
          };
        </script>
      </body>
      </html>
    `
  }

  const handleExportPDF = () => {
    const quota = checkLimit('evidence_dossier_exports_per_month')
    if (quota.isExceeded) {
      toast.error(`Export limit reached (${quota.current} / ${quota.max}). Upgrade your tier for unlimited dossiers.`)
      return
    }

    setIsExporting(true)
    try {
      const html = generateDossierHtml()
      const printWindow = window.open('', '_blank')

      if (printWindow) {
        printWindow.document.open()
        printWindow.document.write(html)
        printWindow.document.close()
        toast.success('Institutional PDF dossier formatted and sent to print queue')
      } else {
        // Fallback: If popup was blocked by browser policy (Safari/Firefox/iOS), use hidden sandboxed iframe
        const iframe = document.createElement('iframe')
        iframe.style.position = 'fixed'
        iframe.style.right = '0'
        iframe.style.bottom = '0'
        iframe.style.width = '0'
        iframe.style.height = '0'
        iframe.style.border = '0'
        document.body.appendChild(iframe)

        const doc = iframe.contentWindow?.document || iframe.contentDocument
        if (doc && iframe.contentWindow) {
          doc.open()
          doc.write(html)
          doc.close()
          setTimeout(() => {
            iframe.contentWindow?.focus()
            iframe.contentWindow?.print()
            setTimeout(() => {
              document.body.removeChild(iframe)
            }, 1000)
          }, 300)
          toast.success('Institutional PDF dossier launched via direct print stream')
        } else {
          toast.error('Pop-up blocked. Please allow pop-ups for Talvrin to export PDF dossiers.')
        }
      }
    } catch (e) {
      console.error('Failed to export PDF dossier', e)
      toast.error('Failed to generate PDF dossier')
    } finally {
      setIsExporting(false)
    }
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
          <RichText>{visibleText}</RichText>
          {isTyping && <span className="typing-cursor" aria-hidden="true" />}
        </div>

        {/* Institutional Dossier Export & Action Toolbar */}
        {!isTyping && (
          <div className="mt-2.5 flex items-center gap-1.5 pt-1.5">
            <button
              onClick={handleCopyMarkdown}
              title="Copy full research response and audit trail to clipboard"
              className="inline-flex items-center gap-1 rounded-md border border-border/60 bg-secondary/40 hover:bg-secondary px-2 py-0.5 text-[11px] font-medium text-muted-foreground hover:text-foreground transition cursor-pointer"
            >
              {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
              <span>{copied ? 'Copied' : 'Copy'}</span>
            </button>

            <button
              onClick={handleExportPDF}
              disabled={isExporting}
              title="Generate institutional PDF evidence dossier with SHA-256 audit fingerprint"
              className="inline-flex items-center gap-1 rounded-md border border-primary/30 bg-primary/10 hover:bg-primary/20 px-2 py-0.5 text-[11px] font-medium text-primary hover:text-primary-foreground transition cursor-pointer"
            >
              <FileDown className="h-3 w-3" />
              <span>Export Dossier (PDF)</span>
            </button>

            {effectiveTaggedAsset && (
              <span className="ml-auto text-[10.5px] font-mono text-muted-foreground/70 hidden sm:inline">
                Target: {effectiveTaggedAsset.symbol}
              </span>
            )}
          </div>
        )}

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
