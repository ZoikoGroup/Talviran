import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Mail, ExternalLink, LifeBuoy, CheckCircle2, Send, ShieldAlert } from 'lucide-react'
import PageLayout, { Section } from '@/components/layouts/PageLayout'
import { Field, SubmitButton } from '@/components/ui/field'
import { CONTACT_TOPICS, SUPPORT_EMAIL, mailtoLink } from '@/data/contact'
import { submitSupportTicket, type CreateSupportTicketPayload, type SupportTicketResult } from '@/lib/api'

export default function Contact() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [topic, setTopic] = useState<string>(CONTACT_TOPICS[0])
  const [message, setMessage] = useState('')
  const [instrument, setInstrument] = useState('')
  const [reportedFigure, setReportedFigure] = useState('')
  const [expectedFigure, setExpectedFigure] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [ticketResult, setTicketResult] = useState<SupportTicketResult | null>(null)

  const isFigureTopic = topic.toLowerCase().includes('figure') || topic.toLowerCase().includes('data')

  const submitDirectTicket = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!message.trim()) return setError('Please write a message describing your inquiry or discrepancy.')
    setError(null)
    setSubmitting(true)

    try {
      let category: CreateSupportTicketPayload['category'] = 'general_inquiry'
      let severity: CreateSupportTicketPayload['severity'] = 'standard'

      if (isFigureTopic) {
        category = 'data_discrepancy'
        severity = 'critical_data_error'
      } else if (topic.toLowerCase().includes('calculation')) {
        category = 'calculation_error'
      } else if (topic.toLowerCase().includes('bug')) {
        category = 'platform_glitch'
      }

      const payload: CreateSupportTicketPayload = {
        category,
        severity,
        subject: `${topic}: ${name || 'User'}`,
        description: message.trim(),
        contact_email: email.trim() || undefined,
        instrument_symbol: instrument.trim() || undefined,
        reported_figure: reportedFigure.trim() || undefined,
        expected_figure: expectedFigure.trim() || undefined,
      }

      const res = await submitSupportTicket(payload)
      setTicketResult(res)
    } catch {
      // If offline or unauthenticated fallback to mailto
      window.location.href = mailtoLink(topic, name, message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <PageLayout
      title="Contact & Support Desk"
      meta="Direct institutional desk for product support, account requests, and market data audit reports"
    >
      <div className="flex flex-col gap-8">
        {/* Fast Email Banner */}
        <Section id="email" heading="Direct Desk Email">
          <p>
            For urgent compliance inquiries or partnership requests, our desk monitors incoming dispatches continuously.
          </p>
          <a
            href={`mailto:${SUPPORT_EMAIL}`}
            className="inline-flex items-center gap-2.5 self-start rounded-xl border border-border bg-card px-4 py-3 text-[14px] font-medium text-foreground transition-colors hover:bg-accent"
          >
            <Mail className="h-4 w-4 text-primary" />
            {SUPPORT_EMAIL}
            <ExternalLink className="h-3.5 w-3.5 text-muted-foreground" />
          </a>
        </Section>

        {/* In-App Ticket Dispatch */}
        <Section id="form" heading="Log an Institutional Ticket / Report Discrepancy">
          <p>
            Submissions are permanently recorded in the immutable platform audit ledger and assigned an institutional ticket tracking code.
          </p>

          {ticketResult ? (
            <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-6 text-foreground">
              <div className="flex items-center gap-3">
                <CheckCircle2 className="h-6 w-6 text-emerald-400" />
                <div>
                  <h4 className="text-[16px] font-semibold text-emerald-300">
                    Ticket Logged: {ticketResult.reference_code}
                  </h4>
                  <p className="mt-1 text-[13px] text-muted-foreground">
                    {ticketResult.message}
                  </p>
                </div>
              </div>
              <div className="mt-4 flex gap-3">
                <button
                  onClick={() => {
                    setTicketResult(null)
                    setMessage('')
                    setInstrument('')
                    setReportedFigure('')
                    setExpectedFigure('')
                  }}
                  className="rounded-xl border border-border bg-card px-4 py-2 text-[13px] font-medium transition-colors hover:bg-accent"
                >
                  Log Another Ticket
                </button>
                <Link
                  to="/guides"
                  className="rounded-xl bg-primary px-4 py-2 text-[13px] font-medium text-primary-foreground shadow transition-all hover:bg-primary/90"
                >
                  View Documentation
                </Link>
              </div>
            </div>
          ) : (
            <form onSubmit={submitDirectTicket} noValidate className="flex flex-col gap-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field
                  label="Your Name (Optional)"
                  placeholder="e.g. Jane Doe"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
                <Field
                  label="Contact Email"
                  placeholder="name@institution.com"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>

              <div>
                <label
                  htmlFor="contact-topic"
                  className="mb-1.5 block text-[13px] font-medium"
                >
                  Topic Category
                </label>
                <select
                  id="contact-topic"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  className="w-full rounded-xl border border-border bg-background/60 px-3.5 py-2.5 text-[14px] outline-none transition-colors focus:border-ring/70 focus:ring-2 focus:ring-ring/20"
                >
                  {CONTACT_TOPICS.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                  <option value="Data Discrepancy / Incorrect Figure">
                    Data Discrepancy / Incorrect Figure
                  </option>
                  <option value="Calculation Formula Review">
                    Calculation Formula Review
                  </option>
                  <option value="Missing Instrument or Series">
                    Missing Instrument or Series
                  </option>
                </select>
              </div>

              {/* Data Discrepancy Context Fields */}
              {isFigureTopic && (
                <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
                  <div className="mb-3 flex items-center gap-2 text-[13px] font-semibold text-amber-300">
                    <ShieldAlert className="h-4 w-4" />
                    <span>Data Integrity Report Details</span>
                  </div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <Field
                      label="Instrument / Ticker"
                      placeholder="e.g. UKT 4.25% 2034"
                      value={instrument}
                      onChange={(e) => setInstrument(e.target.value)}
                    />
                    <Field
                      label="Reported Figure"
                      placeholder="e.g. Yield: 4.12%"
                      value={reportedFigure}
                      onChange={(e) => setReportedFigure(e.target.value)}
                    />
                    <Field
                      label="Expected / Benchmark"
                      placeholder="e.g. DMO Close: 4.08%"
                      value={expectedFigure}
                      onChange={(e) => setExpectedFigure(e.target.value)}
                    />
                  </div>
                </div>
              )}

              <div>
                <label
                  htmlFor="contact-message"
                  className="mb-1.5 block text-[13px] font-medium"
                >
                  Message & Detailed Description
                </label>
                <textarea
                  id="contact-message"
                  rows={5}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  aria-invalid={!!error}
                  placeholder="Describe your question, provide URLs/timestamps, or explain what you observed..."
                  className="w-full resize-y rounded-xl border border-border bg-background/60 px-3.5 py-2.5 text-[14px] leading-relaxed outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-ring/70 focus:ring-2 focus:ring-ring/20"
                />
                {error && <p className="mt-1.5 text-[12px] text-destructive">{error}</p>}
              </div>

              <div className="flex items-center gap-3">
                <SubmitButton disabled={submitting}>
                  <Send className="mr-2 h-4 w-4" />
                  {submitting ? 'Submitting to Audit Ledger…' : 'Submit Ticket to Desk'}
                </SubmitButton>
              </div>
            </form>
          )}
        </Section>

        {/* Figure reporting doctrine reminder */}
        <Section id="figure" heading="Reporting an incorrect figure">
          <p>
            If a number looks wrong, that matters more to us than any other feedback. Talvrin&apos;s premise is that every figure traces strictly to an official source.
            Include the instrument, the figure as shown, and the page or chat where you saw it. If the Evidence panel was open, the source observation and its as-of timestamp are the most critical data points.
          </p>
        </Section>

        <Section id="elsewhere" heading="Documentation & Self-Service">
          <p>
            Before submitting a ticket, check our{' '}
            <Link to="/guides" className="text-primary hover:underline font-medium">
              Interactive Guides & Prompting Cookbook
            </Link>{' '}
            and the{' '}
            <Link to="/help" className="text-primary hover:underline font-medium">
              Help Centre FAQ
            </Link>
            .
          </p>
          <div className="flex gap-3 rounded-xl border border-border bg-card px-4 py-3.5">
            <LifeBuoy className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
            <p className="text-[13.5px] leading-relaxed">
              Talvrin is an institutional platform by Zoiko Group. Support SLA for enterprise accounts is 1-hour during market hours.
            </p>
          </div>
        </Section>
      </div>
    </PageLayout>
  )
}
