import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Mail, ExternalLink, LifeBuoy } from 'lucide-react'
import PageLayout, { Section } from '@/components/layouts/PageLayout'
import { Field, SubmitButton } from '@/components/ui/field'
import { CONTACT_TOPICS, SUPPORT_EMAIL, mailtoLink } from '@/data/contact'

export default function Contact() {
  const [name, setName] = useState('')
  const [topic, setTopic] = useState<string>(CONTACT_TOPICS[0])
  const [message, setMessage] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!message.trim()) return setError('Please write a message.')
    setError(null)
    // Hands off to the user's mail client — nothing is sent from the browser.
    window.location.href = mailtoLink(topic, name, message)
  }

  return (
    <PageLayout
      title="Contact us"
      meta="Questions about the product, a figure, or your account"
    >
      <div className="flex flex-col gap-8">
        <Section id="email" heading="Email us">
          <p>
            The quickest route is email. We read everything that arrives here.
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

        <Section id="form" heading="Or write to us here">
          <p>
            This opens the message in your own email app, addressed and titled
            for you — nothing is sent from this page.
          </p>

          <form onSubmit={submit} noValidate className="flex flex-col gap-4">
            <Field
              label="Your name"
              placeholder="Optional"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />

            <div>
              <label
                htmlFor="contact-topic"
                className="mb-1.5 block text-[13px] font-medium"
              >
                Topic
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
              </select>
            </div>

            <div>
              <label
                htmlFor="contact-message"
                className="mb-1.5 block text-[13px] font-medium"
              >
                Message
              </label>
              <textarea
                id="contact-message"
                rows={6}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                aria-invalid={!!error}
                placeholder="What can we help with?"
                className="w-full resize-y rounded-xl border border-border bg-background/60 px-3.5 py-2.5 text-[14px] leading-relaxed outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-ring/70 focus:ring-2 focus:ring-ring/20"
              />
              {error && <p className="mt-1.5 text-[12px] text-destructive">{error}</p>}
            </div>

            <SubmitButton>Open in your email app</SubmitButton>
          </form>
        </Section>

        <Section id="figure" heading="Reporting an incorrect figure">
          <p>
            If a number looks wrong, that matters more to us than most feedback —
            the whole premise is that every figure traces to an official source.
            Include the instrument, the figure as shown, and the page or chat
            where you saw it. If the Evidence panel was open, the source and its
            as-of time are the most useful things you can send.
          </p>
        </Section>

        <Section id="elsewhere" heading="Other routes">
          <p>
            For how the product works, the{' '}
            <Link to="/help" className="text-primary hover:underline">
              Help centre
            </Link>{' '}
            covers most questions. For how we handle data, see{' '}
            <Link to="/privacy" className="text-primary hover:underline">
              Privacy
            </Link>
            , and for what Talvrin will and will not do, see{' '}
            <Link to="/terms" className="text-primary hover:underline">
              Terms
            </Link>
            .
          </p>
          <div className="flex gap-3 rounded-xl border border-border bg-card px-4 py-3.5">
            <LifeBuoy className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
            <p className="text-[13.5px] leading-relaxed">
              A postal address, phone support and published response times will
              be added here before launch. Talvrin is a Zoiko Group platform.
            </p>
          </div>
        </Section>
      </div>
    </PageLayout>
  )
}
