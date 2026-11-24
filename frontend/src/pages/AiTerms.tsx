import { AlertTriangle, Check, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import PageLayout, { Bullets, RuleTable, Section, type TocEntry } from '@/components/layouts/PageLayout'

/**
 * AI Terms of Use page.
 *
 * Grounded in AI-001 / ai_gateway/gateway.py: invoke_model() is the single
 * sanctioned entry point, gated by a kill-switch check and the same PDP
 * every other capability goes through, refuses to render a prompt without a
 * caller-supplied evidence_bundle_id, validates citations against real
 * evidence items before returning a response, and allows exactly one bounded
 * regeneration attempt before giving up - all independently verifiable in
 * this repository's code, not asserted on faith. The "AI is fully
 * removable" line is the module's own docstring, not marketing copy.
 *
 * Deliberately absent: governing law, liability caps, a named list of model
 * subprocessors and their contract terms, and a specific regional-routing
 * commitment - those require the same legal/vendor sign-off Terms.tsx and
 * Privacy.tsx already decline to improvise.
 */
const CANNOT = [
  'Place a trade, move money, or take any other external, irreversible action — there is no agentic capability wired to do this anywhere in the product.',
  'Produce a buy, sell or hold call, a price target, or a ranking of instruments by merit.',
  'Train on your private research, prompts or workspace content as a matter of course.',
  'Answer without a grounding evidence bundle — an AI response with no inspectable source behind it is not a feature gap, it is structurally blocked.',
] as const

const CAN = [
  ['Explain a sourced fact', 'Compose prose around facts and calculations that already exist, with citations.'],
  ['Summarise evidence', 'Summarise approved source material you or the platform retrieved, with citations back to it.'],
  ['Explain a calculation', 'Walk through the inputs, method and result of a calculation already produced deterministically.'],
  ['Discover evidence', 'Help you find an approved source, document or prior fact relevant to your question.'],
] as const

const TOC: TocEntry[] = [
  { id: 'scope', label: 'Scope and incorporation' },
  { id: 'can-cannot', label: 'What it can and cannot do' },
  { id: 'evidence', label: 'Evidence and citations' },
  { id: 'accuracy', label: 'Accuracy and abstention' },
  { id: 'inputs', label: 'Your inputs' },
  { id: 'training', label: 'Model training and retention' },
  { id: 'providers', label: 'Model providers and fail-closed routing' },
  { id: 'removable', label: 'AI is fully removable' },
  { id: 'misuse', label: 'Prohibited use' },
  { id: 'contact', label: 'Contact' },
]

export default function AiTerms() {
  return (
    <PageLayout
      title="AI Terms of Use"
      meta="How Talvrin's AI Gateway is actually built to behave — from AI-001"
      toc={TOC}
    >
      <div className="mb-9 flex gap-3 rounded-xl border border-delayed/40 bg-delayed/10 px-4 py-3.5">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-delayed" />
        <div className="text-[13.5px] leading-relaxed">
          <p className="font-medium text-foreground">
            Draft — not yet a binding contract.
          </p>
          <p className="mt-1 text-muted-foreground">
            This page describes how the AI Gateway is engineered to behave,
            verifiable in this product's own code. It does not yet contain
            governing law, liability allocation, a disclosed list of model
            subprocessors, or a region-by-region data-routing commitment —
            those require legal and vendor sign-off this page does not
            substitute for.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-8">
        <Section id="scope" heading="Scope and incorporation">
          <p>
            These AI Terms cover the optional AI-assisted features available in
            Talvrin's research workspace — composed answers, summaries and
            explanations generated through the platform's AI Gateway. They sit
            alongside, and do not replace,{' '}
            <Link to="/terms" className="text-foreground underline underline-offset-2 hover:no-underline">
              Terms and Conditions
            </Link>
            ,{' '}
            <Link to="/data-terms" className="text-foreground underline underline-offset-2 hover:no-underline">
              Data &amp; Market Information Terms
            </Link>{' '}
            and{' '}
            <Link to="/privacy" className="text-foreground underline underline-offset-2 hover:no-underline">
              Privacy
            </Link>
            . Nothing here grants a right beyond what those pages already
            describe.
          </p>
        </Section>

        <Section id="can-cannot" heading="What it can and cannot do">
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            {CAN.map(([name, desc]) => (
              <div key={name} className="flex gap-3 border-b border-border px-4 py-3 last:border-b-0">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-fresh" />
                <div className="min-w-0">
                  <div className="text-[13.5px] font-medium text-foreground">{name}</div>
                  <div className="mt-0.5 text-[13.5px] leading-relaxed">{desc}</div>
                </div>
              </div>
            ))}
          </div>
          <ul className="flex flex-col gap-2.5">
            {CANNOT.map((t) => (
              <li key={t} className="flex gap-2.5">
                <X className="mt-0.5 h-4 w-4 shrink-0 text-stale" />
                <span>{t}</span>
              </li>
            ))}
          </ul>
        </Section>

        <Section id="evidence" heading="Evidence and citations">
          <p>
            An AI-composed answer is an aid to navigating evidence, not a new
            source itself. Every call to the Gateway requires a grounding
            evidence bundle — the Gateway will not generate text from a bare
            prompt with no inspectable source attached — and every citation in
            a response is validated against real items in that bundle before
            it is returned to you. A citation is a path to inspect the
            underlying fact, not a warranty that the fact is complete, current
            or licensed for every use.
          </p>
        </Section>

        <Section id="accuracy" heading="Accuracy, currency and abstention">
          <p>
            AI output can be wrong, incomplete or poorly contextualised, and
            sources can disagree, be corrected, or become unavailable. Where
            the evidence doesn't support a confident answer, the Gateway is
            designed to validate its own response and discard it if citations
            don't check out — allowing exactly one bounded attempt to
            regenerate before giving up, rather than inventing a plausible but
            ungrounded answer. On validation failure, repeated failure, a
            policy denial or the Gateway being unreachable, the platform falls
            back to its existing rule-based answer; it does not surface a bare
            request failure to you.
          </p>
        </Section>

        <Section id="inputs" heading="Your inputs">
          <Bullets
            items={[
              'Use the minimum necessary information in a research query — do not submit another person’s confidential data, credentials, or material nonpublic information.',
              'An organisation-managed workspace is isolated from other tenants at the database level, not only in the interface — a request routed for one account cannot read another account’s prompts, sources or saved history.',
              'Research conversations are encrypted at rest, per account, the same way the rest of your research content is.',
            ]}
          />
        </Section>

        <Section id="training" heading="Model training and retention">
          <p>
            Your research inputs and AI-composed outputs are processed to
            answer your query and are not used to train general-purpose
            models. The platform's truth classes — raw observations, accepted
            facts and calculation results — are read-only from the AI's
            perspective: the AI Gateway can read and explain them, but it
            cannot write to any of them. Conversation history is retained
            according to your account configuration and is deleted the same
            way the rest of your research content is, under the Privacy
            Policy.
          </p>
        </Section>

        <Section id="providers" heading="Model providers and fail-closed routing">
          <p>
            Every AI request is routed only to a model that has been
            explicitly promoted to production status for its task — proven
            live and reviewed before being trusted, the same governance
            discipline applied to an approved calculation specification. If no
            approved model exists for a task, or the policy check denies the
            request, the request fails closed rather than falling through to
            an unapproved provider.
          </p>
        </Section>

        <Section id="removable" heading="AI is fully removable">
          <p>
            Talvrin's research features work correctly with the AI Gateway
            turned off entirely. AI composes prose around facts and
            calculations that already exist independently of it — it is never
            the only path to an answer, and nothing in the product depends on
            it being available.
          </p>
        </Section>

        <Section id="misuse" heading="Prohibited use">
          <RuleTable
            rows={[
              ['Prompt injection', 'Attempting to override entitlement checks or trigger unauthorised actions via crafted input is not permitted and is treated as abuse.'],
              ['Cross-tenant probing', 'Attempting to retrieve another account’s prompts, sources or history is not permitted.'],
              ['Reconstruction', 'Using repeated prompts to reconstruct licensed source content you are not entitled to view is not permitted.'],
              ['Automation abuse', 'Automated workflows that overload or scrape AI-composed output in place of a proper data entitlement are not permitted.'],
            ]}
          />
        </Section>

        <Section id="contact" heading="Contact">
          <p>
            Questions, reportable errors or concerns about an AI-composed
            answer can be raised through{' '}
            <Link to="/contact" className="text-foreground underline underline-offset-2 hover:no-underline">
              Contact
            </Link>
            .
          </p>
        </Section>
      </div>
    </PageLayout>
  )
}
