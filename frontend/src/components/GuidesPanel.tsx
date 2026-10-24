import { useState, useMemo, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  X,
  Search,
  BookOpen,
  Play,
  Copy,
  Check,
  CheckCircle2,
  AlertTriangle,
  Clock,
  ExternalLink,
  ChevronRight,
  Send,
  Headphones,
  Mail,
} from 'lucide-react'
import { GUIDE_TOPICS } from '@/data/guidesData'
import { ARTICLES } from '@/data/helpArticles'
import { SUPPORT_EMAIL } from '@/data/contact'
import { submitSupportTicket, type CreateSupportTicketPayload, type SupportTicketResult } from '@/lib/api'
import { cn } from '@/lib/utils'

interface GuidesPanelProps {
  isOpen: boolean
  onClose: () => void
  initialTopicId?: string | null
  initialTab?: PanelTab
  onRunPrompt?: (prompt: string) => void
}

type PanelTab = 'guides' | 'faq' | 'ticket'

export default function GuidesPanel({
  isOpen,
  onClose,
  initialTopicId,
  initialTab = 'guides',
  onRunPrompt,
}: GuidesPanelProps) {
  const [tab, setTab] = useState<PanelTab>(initialTab)
  const [selectedTopicId, setSelectedTopicId] = useState<string>(
    initialTopicId || GUIDE_TOPICS[0].id
  )
  const [searchQuery, setSearchQuery] = useState('')
  const [copiedQuery, setCopiedQuery] = useState<string | null>(null)
  const [expandedFaqId, setExpandedFaqId] = useState<string | null>(null)

  // Ticket state
  const [ticketTopic, setTicketTopic] = useState('Data Discrepancy / Incorrect Figure')
  const [ticketName, setTicketName] = useState('')
  const [ticketEmail, setTicketEmail] = useState('')
  const [ticketDesc, setTicketDesc] = useState('')
  const [ticketInstrument, setTicketInstrument] = useState('')
  const [submittingTicket, setSubmittingTicket] = useState(false)
  const [ticketResult, setTicketResult] = useState<SupportTicketResult | null>(null)
  const [ticketError, setTicketError] = useState<string | null>(null)

  useEffect(() => {
    if (initialTopicId) {
      const match = GUIDE_TOPICS.find((t) => t.id === initialTopicId || t.slug === initialTopicId)
      if (match) {
        setSelectedTopicId(match.id)
        setTab('guides')
      }
    }
  }, [initialTopicId])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

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

  const filteredFaqs = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return ARTICLES
    return ARTICLES.filter(
      (a) =>
        a.question.toLowerCase().includes(q) ||
        a.answer.some((p) => p.toLowerCase().includes(q)) ||
        a.category.toLowerCase().includes(q)
    )
  }, [searchQuery])

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedQuery(text)
    setTimeout(() => setCopiedQuery(null), 2000)
  }

  const handleRun = (prompt: string) => {
    if (onRunPrompt) {
      onRunPrompt(prompt)
      onClose()
    } else {
      sessionStorage.setItem('talvrin_pending_prompt', prompt)
      window.location.hash = '#research'
      onClose()
    }
  }

  const handleTicketSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!ticketDesc.trim()) return setTicketError('Please provide a message or description.')
    setTicketError(null)
    setSubmittingTicket(true)

    try {
      const payload: CreateSupportTicketPayload = {
        category: ticketTopic.toLowerCase().includes('data')
          ? 'data_discrepancy'
          : ticketTopic.toLowerCase().includes('calculation')
          ? 'calculation_error'
          : 'general_inquiry',
        severity: 'standard',
        subject: `${ticketTopic}: ${ticketName || 'User'}`,
        description: ticketDesc.trim(),
        contact_email: ticketEmail.trim() || undefined,
        instrument_symbol: ticketInstrument.trim() || undefined,
      }
      const res = await submitSupportTicket(payload)
      setTicketResult(res)
    } catch {
      setTicketError("Failed to submit ticket. Please email desk directly.")
    } finally {
      setSubmittingTicket(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-xs transition-opacity duration-300">
      {/* Click outside backdrop to close */}
      <div className="flex-1" onClick={onClose} />

      {/* Right Drawer Panel */}
      <div className="flex h-full w-full max-w-xl flex-col border-l border-border/80 bg-background shadow-2xl shadow-black/60 transition-transform duration-300 sm:w-[560px]">
        {/* Top Header */}
        <div className="flex items-center justify-between border-b border-border/80 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-primary/10 text-primary border border-primary/20">
              <BookOpen className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-[15px] font-bold text-foreground leading-tight">
                Guides, FAQ's & Support
              </h2>
              <p className="text-[11.5px] text-muted-foreground">
                Institutional documentation, query recipes & support
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Link
              to="/guides"
              target="_blank"
              rel="noreferrer"
              title="Open full page in new tab"
              className="grid h-8 w-8 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <ExternalLink className="h-4 w-4" />
            </Link>
            <button
              onClick={onClose}
              aria-label="Close panel"
              className="grid h-8 w-8 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Tab Switcher */}
        <div className="flex items-center border-b border-border/80 px-5 pt-2">
          <button
            onClick={() => setTab('guides')}
            className={cn(
              'border-b-2 px-3 py-2 text-[12.5px] font-medium transition cursor-pointer',
              tab === 'guides'
                ? 'border-primary text-foreground font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            )}
          >
            Guides
          </button>
          <button
            onClick={() => setTab('faq')}
            className={cn(
              'border-b-2 px-3 py-2 text-[12.5px] font-medium transition cursor-pointer',
              tab === 'faq'
                ? 'border-primary text-foreground font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            )}
          >
            FAQ's ({ARTICLES.length})
          </button>
          <button
            onClick={() => setTab('ticket')}
            className={cn(
              'border-b-2 px-3 py-2 text-[12.5px] font-medium transition cursor-pointer',
              tab === 'ticket'
                ? 'border-primary text-foreground font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            )}
          >
            Support
          </button>
        </div>

        {/* Search Bar for Guides & FAQs */}
        {tab !== 'ticket' && (
          <div className="border-b border-border/60 p-3 px-5">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={tab === 'guides' ? 'Filter topics, formulas, or rules...' : 'Search FAQ articles...'}
                className="w-full rounded-lg border border-border bg-card/60 py-1.5 pl-8 pr-3 text-[13px] outline-none transition placeholder:text-muted-foreground/60 focus:border-primary focus:ring-1 focus:ring-primary/20"
              />
            </div>
          </div>
        )}

        {/* Panel Body Content */}
        <div className="flex-1 overflow-y-auto p-5 scrollbar-slim">
          {/* TAB 1: GUIDES */}
          {tab === 'guides' && (
            <div className="flex flex-col gap-5">
              {/* Horizontal / Scrollable Topic Selector Pills */}
              <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-slim">
                {filteredTopics.map((topic) => {
                  const isSelected = topic.id === activeTopic.id
                  return (
                    <button
                      key={topic.id}
                      onClick={() => setSelectedTopicId(topic.id)}
                      className={cn(
                        'shrink-0 rounded-lg border px-3 py-1.5 text-left transition text-[12px]',
                        isSelected
                          ? 'border-primary bg-primary/10 font-semibold text-primary'
                          : 'border-border/80 bg-card/50 text-muted-foreground hover:bg-card hover:text-foreground'
                      )}
                    >
                      <span>{topic.title}</span>
                    </button>
                  )
                })}
              </div>

              {/* Active Guide Article */}
              <div className="rounded-xl border border-border/80 bg-card/70 p-4">
                <div className="border-b border-border/70 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="rounded-md bg-primary/15 px-2 py-0.5 text-[10.5px] font-semibold text-primary">
                      {activeTopic.category}
                    </span>
                    <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      {activeTopic.readTimeMinutes} min read
                    </span>
                  </div>
                  <h3 className="mt-1.5 text-[16px] font-bold text-foreground">
                    {activeTopic.title}
                  </h3>
                  <p className="mt-1 text-[12.5px] text-muted-foreground leading-relaxed">
                    {activeTopic.summary}
                  </p>
                </div>

                {/* Guide Sections */}
                <div className="mt-4 flex flex-col gap-6">
                  {activeTopic.sections.map((sec) => (
                    <div key={sec.id} className="flex flex-col gap-2">
                      <div className="flex items-center gap-2">
                        <h4 className="text-[13.5px] font-semibold text-foreground">
                          {sec.title}
                        </h4>
                        {sec.badge && (
                          <span className="rounded bg-accent px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                            {sec.badge}
                          </span>
                        )}
                      </div>

                      <div className="flex flex-col gap-2 text-[12.5px] text-muted-foreground leading-relaxed">
                        {sec.content.map((p, idx) => (
                          <p key={idx}>{p}</p>
                        ))}
                      </div>

                      {/* Key Points */}
                      {sec.keyPoints && sec.keyPoints.length > 0 && (
                        <div className="mt-1 rounded-lg border border-border/70 bg-accent/30 p-3">
                          <ul className="flex flex-col gap-1.5">
                            {sec.keyPoints.map((pt, idx) => (
                              <li key={idx} className="flex items-start gap-2 text-[12px] text-foreground/90">
                                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                                <span>{pt}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Caution */}
                      {sec.caution && (
                        <div className="mt-1 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-2.5 text-[12px] text-amber-200">
                          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
                          <span>{sec.caution}</span>
                        </div>
                      )}

                      {/* Example Queries */}
                      {sec.exampleQueries && sec.exampleQueries.length > 0 && (
                        <div className="mt-2 flex flex-col gap-2.5">
                          {sec.exampleQueries.map((ex, idx) => (
                            <div
                              key={idx}
                              className="rounded-lg border border-border/80 bg-background/60 p-3"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="font-semibold text-[12.5px] text-foreground">
                                  {ex.title}
                                </span>
                                <div className="flex items-center gap-1.5">
                                  <button
                                    onClick={() => handleCopy(ex.query)}
                                    className="flex h-6 items-center gap-1 rounded border border-border px-1.5 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground"
                                  >
                                    {copiedQuery === ex.query ? (
                                      <Check className="h-3 w-3 text-emerald-500" />
                                    ) : (
                                      <Copy className="h-3 w-3" />
                                    )}
                                  </button>
                                  <button
                                    onClick={() => handleRun(ex.query)}
                                    className="flex h-6 items-center gap-1 rounded bg-primary/90 px-2 text-[11px] font-medium text-primary-foreground hover:bg-primary active:scale-95"
                                  >
                                    <Play className="h-2.5 w-2.5 fill-current" />
                                    <span>Try</span>
                                  </button>
                                </div>
                              </div>
                              <p className="mt-1 font-mono text-[11.5px] text-foreground/80 leading-snug">
                                “{ex.query}”
                              </p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: FAQS */}
          {tab === 'faq' && (
            <div className="flex flex-col gap-3">
              {filteredFaqs.map((article) => {
                const isOpen = expandedFaqId === article.id
                return (
                  <div
                    key={article.id}
                    className="overflow-hidden rounded-xl border border-border/80 bg-card/60 transition"
                  >
                    <button
                      onClick={() => setExpandedFaqId(isOpen ? null : article.id)}
                      className="flex w-full items-center justify-between gap-3 p-3.5 text-left hover:bg-accent/40"
                    >
                      <span className="text-[13px] font-semibold text-foreground">
                        {article.question}
                      </span>
                      <ChevronRight
                        className={cn(
                          'h-4 w-4 shrink-0 text-muted-foreground transition-transform',
                          isOpen && 'rotate-90'
                        )}
                      />
                    </button>
                    {isOpen && (
                      <div className="flex flex-col gap-2 border-t border-border/60 bg-background/50 p-3.5 text-[12.5px] leading-relaxed text-muted-foreground">
                        {article.answer.map((p, idx) => (
                          <p key={idx}>{p}</p>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* TAB 3: SUPPORT & TICKET DESK */}
          {tab === 'ticket' && (
            <div className="flex flex-col gap-4">
              {/* Institutional Support Overview Card */}
              <div className="rounded-xl border border-border/80 bg-card/60 p-3.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Headphones className="h-4 w-4 text-primary" />
                    <span className="text-[13px] font-semibold text-foreground">
                      Talvrin Institutional Desk
                    </span>
                  </div>
                  <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10.5px] font-medium text-emerald-400 border border-emerald-500/20">
                    Live Desk Active
                  </span>
                </div>
                <p className="mt-1.5 text-[12px] text-muted-foreground leading-relaxed">
                  Every data discrepancy or calculation report submitted here writes directly to the immutable platform audit ledger (<code className="font-mono text-primary/90">audit.event_log</code>) and is assigned an immediate reference code.
                </p>
                <div className="mt-2.5 flex items-center justify-between border-t border-border/60 pt-2 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Mail className="h-3 w-3 text-primary" />
                    {SUPPORT_EMAIL}
                  </span>
                  <span>Enterprise SLA: &lt; 1 hour</span>
                </div>
              </div>
              {ticketResult ? (
                <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-foreground">
                  <div className="flex items-center gap-2.5">
                    <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                    <div>
                      <h4 className="font-semibold text-[14px] text-emerald-300">
                        Ticket Logged: {ticketResult.reference_code}
                      </h4>
                      <p className="text-[12px] text-muted-foreground">
                        {ticketResult.message}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      setTicketResult(null)
                      setTicketDesc('')
                      setTicketInstrument('')
                    }}
                    className="mt-3 rounded-lg border border-border bg-card px-3 py-1.5 text-[12px] font-medium hover:bg-accent"
                  >
                    Log Another Ticket
                  </button>
                </div>
              ) : (
                <form onSubmit={handleTicketSubmit} className="flex flex-col gap-3">
                  <div>
                    <label className="mb-1 block text-[11.5px] font-medium text-muted-foreground">
                      Category
                    </label>
                    <select
                      value={ticketTopic}
                      onChange={(e) => setTicketTopic(e.target.value)}
                      className="w-full rounded-lg border border-border bg-card px-3 py-2 text-[12.5px] outline-none"
                    >
                      <option value="Data Discrepancy / Incorrect Figure">
                        Data Discrepancy / Incorrect Figure
                      </option>
                      <option value="Calculation Formula Review">
                        Calculation Formula Review
                      </option>
                      <option value="Missing Instrument or Series">
                        Missing Instrument or Series
                      </option>
                      <option value="General Desk Inquiry">General Desk Inquiry</option>
                    </select>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="mb-1 block text-[11.5px] font-medium text-muted-foreground">
                        Your Name (Optional)
                      </label>
                      <input
                        type="text"
                        value={ticketName}
                        onChange={(e) => setTicketName(e.target.value)}
                        placeholder="e.g. Jane Doe"
                        className="w-full rounded-lg border border-border bg-card px-3 py-1.5 text-[12.5px] outline-none"
                      />
                    </div>
                    <div>
                      <label className="mb-1 block text-[11.5px] font-medium text-muted-foreground">
                        Contact Email
                      </label>
                      <input
                        type="email"
                        value={ticketEmail}
                        onChange={(e) => setTicketEmail(e.target.value)}
                        placeholder="name@institution.com"
                        className="w-full rounded-lg border border-border bg-card px-3 py-1.5 text-[12.5px] outline-none"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="mb-1 block text-[11.5px] font-medium text-muted-foreground">
                      Instrument / Ticker (Optional)
                    </label>
                    <input
                      type="text"
                      value={ticketInstrument}
                      onChange={(e) => setTicketInstrument(e.target.value)}
                      placeholder="e.g. UKT 4.25% 2034"
                      className="w-full rounded-lg border border-border bg-card px-3 py-1.5 text-[12.5px] outline-none"
                    />
                  </div>

                  <div>
                    <label className="mb-1 block text-[11.5px] font-medium text-muted-foreground">
                      Message & Description
                    </label>
                    <textarea
                      rows={4}
                      value={ticketDesc}
                      onChange={(e) => setTicketDesc(e.target.value)}
                      placeholder="Describe the discrepancy, cite the as-of time, or explain what you observed..."
                      className="w-full resize-y rounded-lg border border-border bg-card px-3 py-1.5 text-[12.5px] leading-relaxed outline-none"
                    />
                    {ticketError && (
                      <p className="mt-1 text-[11.5px] text-destructive">{ticketError}</p>
                    )}
                  </div>

                  <button
                    type="submit"
                    disabled={submittingTicket}
                    className="mt-1 flex items-center justify-center gap-1.5 rounded-lg bg-primary py-2 text-[12.5px] font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 cursor-pointer"
                  >
                    <Send className="h-3.5 w-3.5" />
                    <span>{submittingTicket ? 'Recording in Ledger…' : 'Submit Ticket'}</span>
                  </button>

                  <div className="mt-2 text-center text-[11px] text-muted-foreground">
                    Or dispatch directly via email:{' '}
                    <a href={`mailto:${SUPPORT_EMAIL}`} className="text-primary hover:underline">
                      {SUPPORT_EMAIL}
                    </a>
                  </div>
                </form>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
