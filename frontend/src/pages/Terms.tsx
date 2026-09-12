import { AlertTriangle, Check, X } from 'lucide-react'
import PageLayout, {
  Bullets,
  RuleTable,
  Section,
  type TocEntry,
} from '@/components/layouts/PageLayout'

/**
 * Terms page.
 *
 * Grounded in PRD-001 §11 (recommendation-safe interaction contract), §12
 * (commercial and tier contract), RIGHTS-001 §15 (export, download, API and
 * redistribution) and §14 (attribution), and POL-001 §14 (execution and
 * dealing adjacency).
 *
 * Deliberately absent: governing law, jurisdiction, limitation of liability,
 * warranty disclaimers, termination, payment and refund terms, indemnities and
 * dispute resolution. None of those exist anywhere in the documentation estate,
 * and a contract is exactly the wrong place to improvise. The notice at the top
 * says so.
 */

const ALLOWED = [
  ['Factual explanation', 'Explain an instrument term, source fact or market convention.'],
  ['Document summary', 'Summarise approved source material, with citations.'],
  ['Calculation explanation', 'Explain the inputs, formula and result of a calculation already produced deterministically.'],
  ['User-directed comparison', 'Describe similarities and differences using metrics you choose.'],
  ['Event explanation', 'Explain what objective event occurred, and the evidence for it.'],
  ['Source discovery', 'Help you locate an approved source, document or piece of evidence.'],
] as const

const PROHIBITED = [
  'Buy, sell or hold calls — there is no such response type, field, alert action or button anywhere in the product.',
  'Price targets or a proprietary fair-value verdict.',
  'Top picks, "best" lists, or any ranking by merit the platform selected.',
  'Model portfolios, asset allocation or rebalancing workflows.',
  'Suitability or risk-tolerance conclusions, including questionnaires used to recommend investments.',
  'Proprietary credit ratings or probability-of-default grades.',
  'Any execution, dealing or broker purchase path.',
] as const

const TOC: TocEntry[] = [
  { id: 'what', label: 'What Talvrin is' },
  { id: 'allowed', label: 'What you can ask' },
  { id: 'prohibited', label: 'What it will never do' },
  { id: 'decisions', label: 'Your decisions' },
  { id: 'data', label: 'Licensed data' },
  { id: 'account', label: 'Your account' },
  { id: 'availability', label: 'Availability' },
  { id: 'jurisdiction', label: 'Where it is available' },
  { id: 'changes', label: 'Changes to these terms' },
]

export default function Terms() {
  return (
    <PageLayout
      title="Terms and Conditions"
      meta="How you may use Talvrin · Product commitments from PRD-001, RIGHTS-001 and POL-001"
      toc={TOC}
    >
      <div className="mb-9 flex gap-3 rounded-xl border border-delayed/40 bg-delayed/10 px-4 py-3.5">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-delayed" />
        <div className="text-[13.5px] leading-relaxed">
          <p className="font-medium text-foreground">
            Draft — not yet a binding contract.
          </p>
          <p className="mt-1 text-muted-foreground">
            This page sets out the product's own committed rules on what Talvrin
            will and will not do, and how licensed data may be used. It does not
            yet contain governing law, jurisdiction, limitation of liability,
            warranty disclaimers, termination, payment terms, indemnities or
            dispute resolution. Those must be drafted and approved by legal
            counsel before launch.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-8">
        <Section id="what" heading="What Talvrin is">
          <p>
            Talvrin is a research and monitoring workspace for public markets. It
            gives you source-linked facts, reproducible calculations and
            objective monitoring, so you can reach a defensible view yourself.
          </p>
          <p>
            It is not an adviser, a broker or an execution venue. Nothing in the
            product is a personal recommendation, and no part of it will place,
            arrange or route an order.
          </p>
        </Section>

        <Section id="allowed" heading="What you can ask Talvrin to do">
          <p>
            Responses fall into a defined set of families. Anything outside them
            is not a feature we have yet to build — it is deliberately excluded.
          </p>
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            {ALLOWED.map(([name, desc]) => (
              <div
                key={name}
                className="flex gap-3 border-b border-border px-4 py-3 last:border-b-0"
              >
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-fresh" />
                <div className="min-w-0">
                  <div className="text-[13.5px] font-medium text-foreground">{name}</div>
                  <div className="mt-0.5 text-[13.5px] leading-relaxed">{desc}</div>
                </div>
              </div>
            ))}
          </div>
        </Section>

        <Section id="prohibited" heading="What Talvrin will never do">
          <p>
            These are not disclaimers about output quality. They are absent
            capabilities — there is no response type, API field, alert action or
            call to action for any of them.
          </p>
          <ul className="flex flex-col gap-2.5">
            {PROHIBITED.map((t) => (
              <li key={t} className="flex gap-2.5">
                <X className="mt-0.5 h-4 w-4 shrink-0 text-stale" />
                <span>{t}</span>
              </li>
            ))}
          </ul>
          <p>
            If you ask "should I buy this?", Talvrin will recognise the intent
            only in order to route you toward source facts, calculations,
            contract terms and comparisons you direct. It will not answer the
            question.
          </p>
        </Section>

        <Section id="decisions" heading="Your decisions are your own">
          <p>
            You are responsible for any investment decision you take. Talvrin
            provides evidence and calculations; it does not assess whether
            anything is appropriate for your circumstances, objectives or risk
            tolerance, and it does not hold the information needed to do so.
          </p>
          <p>
            Market data can be delayed, restated or corrected by its source.
            Where a fact is superseded, Talvrin shows the current accepted truth
            and preserves the correction lineage — but you should check the
            as-of state shown alongside any figure before relying on it.
          </p>
        </Section>

        <Section id="data" heading="Licensed data and what you may do with it">
          <p>
            Much of the content in Talvrin is licensed from its source. Your
            right to view something on screen is not the same as a right to
            extract or republish it, and each action is evaluated separately.
          </p>
          <RuleTable
            rows={[
              ['Viewing on screen', 'Permitted within your account and plan entitlements.'],
              ['CSV, XLSX and PDF export', 'Subject to field-level permission, record limits, attribution and your plan. Every export is decided and audited on its own.'],
              ['Printing and sharing', 'Treated as redistribution where the source licence requires it. Attribution and limitations must be preserved.'],
              ['Public links', 'Denied by default for licensed source content unless a specific sharing model has been approved.'],
              ['API access', 'Requires a contractual entitlement, the source’s own API and redistribution permission, metering and rate controls.'],
            ]}
          />
          <p>
            Attribution requirements travel with the data, including into
            exports and screenshots. Removing or obscuring attribution is a
            breach of the source licence, not a cosmetic change.
          </p>
        </Section>

        <Section id="account" heading="Your account">
          <Bullets
            items={[
              'Keep your credentials secure and do not share your account. Access is granted to you, not to your organisation at large, unless you are on an enterprise agreement that says otherwise.',
              'Entitlements are enforced server-side. Attempting to circumvent plan, rights or jurisdiction controls is a breach of these terms.',
              'Automated scraping of the interface is not a substitute for an API entitlement and is not permitted.',
            ]}
          />
        </Section>

        <Section id="availability" heading="Availability">
          <p>
            Talvrin is currently a prototype. It is not connected to live market
            data, the content shown is placeholder material, and no service level
            is offered or implied. Do not rely on anything in the current build
            for a real decision.
          </p>
        </Section>

        <Section id="jurisdiction" heading="Where Talvrin is available">
          <p>
            Capabilities differ by jurisdiction. What the platform may show,
            calculate or say is gated by the rules of the market you are asking
            about and the region you are in, and those checks fail closed — if a
            capability has not been approved for your jurisdiction, it is
            unavailable rather than best-effort.
          </p>
        </Section>

        <Section id="changes" heading="Changes to these terms">
          <p>
            Customer-facing terms are a versioned, approved artefact. When they
            change, the version and effective date will be published here rather
            than altered silently.
          </p>
        </Section>
      </div>
    </PageLayout>
  )
}
