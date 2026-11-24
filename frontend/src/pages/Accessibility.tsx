import { AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import PageLayout, { Bullets, Section, type TocEntry } from '@/components/layouts/PageLayout'

/**
 * Accessibility Statement page.
 *
 * WCAG 2.2 AA is stated here as the design target this product builds
 * toward, not as a certified conformance outcome - no independent audit
 * record exists to claim the latter, and claiming it without one would be
 * exactly the fabrication this page's own "known limitations" section
 * warns against. The reporting route below is the real, working support
 * ticket flow (Contact.tsx / support.service), not an invented dedicated
 * accessibility mailbox - there isn't one yet, so this page doesn't
 * pretend there is.
 */
const TOC: TocEntry[] = [
  { id: 'standard', label: 'Standard and present status' },
  { id: 'approach', label: 'How we approach it' },
  { id: 'evidence', label: 'Charts, tables and research evidence' },
  { id: 'ai', label: 'AI-assisted features' },
  { id: 'monitoring', label: 'Alerts and monitoring' },
  { id: 'limitations', label: 'Known limitations' },
  { id: 'reporting', label: 'Reporting a barrier' },
  { id: 'related', label: 'Related policies' },
]

export default function Accessibility() {
  return (
    <PageLayout
      title="Accessibility Statement"
      meta="What Talvrin builds toward, and the limits of what's been verified"
      toc={TOC}
    >
      <div className="mb-9 flex gap-3 rounded-xl border border-delayed/40 bg-delayed/10 px-4 py-3.5">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-delayed" />
        <div className="text-[13.5px] leading-relaxed">
          <p className="font-medium text-foreground">
            Draft — WCAG 2.2 AA is a target, not a certified conformance claim.
          </p>
          <p className="mt-1 text-muted-foreground">
            This page describes the standard the product is designed to, and
            points you to a working route for reporting a barrier. It does not
            yet contain a completed, approved issue-by-issue conformance audit
            across every surface — that requires independent testing this page
            does not claim has happened.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-8">
        <Section id="standard" heading="Standard and present status">
          <p>
            Talvrin is designed toward the Web Content Accessibility Guidelines
            (WCAG) 2.2, Level AA. That is the benchmark the product is built
            against — it is not a statement that every page, table and workflow
            has passed a complete, independently verified audit. Where a
            specific limitation is known, it is listed below rather than
            implied to be resolved.
          </p>
        </Section>

        <Section id="approach" heading="How we approach it">
          <p>
            Keyboard and screen-reader access, visible focus, readable contrast
            and responsive layout at narrow widths are treated as ordinary
            product requirements, not an afterthought — the same way a mobile
            layout overflowing its viewport is treated as a defect to fix, not
            a cosmetic nitpick, in this product's own engineering practice.
          </p>
          <Bullets
            items={[
              'Important tasks should be completable by keyboard alone, with a logical focus order and no keyboard traps.',
              'Headings, regions, lists and form labels follow a consistent structure so screen readers can navigate them, not just sighted scrolling.',
              'Text, controls and layout remain usable under browser zoom and at phone width — a control that runs off the edge of a narrow screen is a bug, not an accepted tradeoff.',
              'Motion and auto-updating content respect reduced-motion preferences, and real-time updates do not repeatedly interrupt assistive technology.',
              'Important information is never conveyed by color alone.',
            ]}
          />
        </Section>

        <Section id="evidence" heading="Charts, tables and research evidence">
          <p>
            A chart is a view onto the same underlying fact, not the only way
            to reach it. Where a chart cannot be rendered for an instrument —
            for example, a sovereign yield symbol a chart vendor's embed
            widget genuinely cannot display — the product says so explicitly
            and keeps showing the real, sourced figure and its history in
            text, rather than leaving a blank space or a silently wrong chart.
            Time-aware research distinguishes publication time from the
            effective/reference period, and an original fact from one that has
            since been corrected or superseded.
          </p>
        </Section>

        <Section id="ai" heading="AI-assisted features">
          <p>
            Where an AI-composed answer is shown, it is labelled as AI-assisted
            and its citations point to inspectable evidence, not the other way
            around — the platform's AI Gateway cannot generate a response
            without a grounding evidence bundle in the first place. If the
            Gateway is unavailable, the product falls back to the same
            rule-based answer rather than showing nothing or an unlabeled
            response. See the{' '}
            <Link to="/ai-terms" className="text-foreground underline underline-offset-2 hover:no-underline">
              AI Terms of Use
            </Link>{' '}
            for how that boundary is enforced.
          </p>
        </Section>

        <Section id="monitoring" heading="Alerts and monitoring">
          <p>
            Monitoring rules and alerts are built to explain what changed in
            text, not only through a color or an animated indicator, so the
            same information reaches someone relying on a screen reader as
            someone scanning the page visually.
          </p>
        </Section>

        <Section id="limitations" heading="Known limitations">
          <p>
            Talvrin has not yet published a complete, approved issue-by-issue
            accessibility assessment covering every surface. That absence is
            not evidence that no barriers exist — it means a scoped,
            independent audit has not yet been run and signed off. As specific
            issues are found and verified, they belong listed here with their
            effect and status, not silently fixed without a record.
          </p>
        </Section>

        <Section id="reporting" heading="Reporting a barrier or requesting help">
          <p>
            If you hit an accessibility barrier, tell us which page or task was
            affected, what you were trying to do, and what happened. You do
            not need to disclose a diagnosis or any medical information — just
            describe the problem. Please don't include passwords, account
            tokens or other sensitive material in the message.
          </p>
          <p>
            Use the{' '}
            <Link to="/contact" className="text-foreground underline underline-offset-2 hover:no-underline">
              Contact
            </Link>{' '}
            page — this is a real, working intake, not a placeholder address.
            We don't yet have a separately staffed accessibility channel, so
            this is the honest, current route rather than one we haven't
            actually built.
          </p>
        </Section>

        <Section id="related" heading="Related policies">
          <p>
            See also{' '}
            <Link to="/privacy" className="text-foreground underline underline-offset-2 hover:no-underline">
              Privacy
            </Link>
            ,{' '}
            <Link to="/terms" className="text-foreground underline underline-offset-2 hover:no-underline">
              Terms and Conditions
            </Link>{' '}
            and{' '}
            <Link to="/disclaimers" className="text-foreground underline underline-offset-2 hover:no-underline">
              Disclaimers
            </Link>
            . Accessibility feedback is not the right channel for a security
            vulnerability report or a confidential privacy-rights request —
            use Contact and say which kind of issue it is so it reaches the
            right place.
          </p>
        </Section>
      </div>
    </PageLayout>
  )
}
