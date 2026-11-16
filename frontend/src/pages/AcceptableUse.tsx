import { AlertTriangle, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import PageLayout, { Bullets, Section, type TocEntry } from '@/components/layouts/PageLayout'

/**
 * Acceptable Use Policy page.
 *
 * Grounded in real enforcement mechanisms that already exist in this
 * codebase: deterministic-only identity resolution (pipeline/
 * identity_resolution.py - an observation that can't be matched exactly is
 * skipped and logged, never fuzzy-matched or auto-created), FORCE ROW LEVEL
 * SECURITY tenant isolation, rights.evaluate_action's per-action gating
 * (view/export/API/AI differ), and the commercial module's real per-account
 * usage counters (watchlists, active rules, research runs, exports) that
 * quota enforcement is actually built on. Deliberately excludes a specific
 * enforcement appeals SLA, fixed rate-limit numbers or a dedicated security
 * disclosure channel, none of which have been built or approved yet.
 */
const PROHIBITED = [
  'Sharing credentials, bypassing seat/workspace boundaries, or accessing an account or workspace not assigned to you.',
  'Scraping, bulk automation or bot access in place of a real API entitlement.',
  'Redistributing, reselling or republishing licensed market data outside your account’s entitlement.',
  'Prompt injection or attempts to make an AI feature bypass entitlement checks or take an unauthorized action.',
  'Attempting to access another tenant’s data, prompts or saved research.',
  'Removing or obscuring source attribution, as-of timestamps or correction history from research evidence.',
] as const

const TOC: TocEntry[] = [
  { id: 'scope', label: 'Scope' },
  { id: 'accounts', label: 'Account and workspace boundaries' },
  { id: 'data-use', label: 'Licensed data: viewing is not reuse' },
  { id: 'automation', label: 'Automation and API conduct' },
  { id: 'ai-misuse', label: 'AI misuse' },
  { id: 'integrity', label: 'Research and evidence integrity' },
  { id: 'prohibited', label: 'Prohibited conduct' },
  { id: 'enforcement', label: 'Enforcement' },
  { id: 'contact', label: 'Reporting a concern' },
]

export default function AcceptableUse() {
  return (
    <PageLayout
      title="Acceptable Use Policy"
      meta="What's actually blocked, and how — grounded in the platform's own enforcement code"
      toc={TOC}
    >
      <div className="mb-9 flex gap-3 rounded-xl border border-delayed/40 bg-delayed/10 px-4 py-3.5">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-delayed" />
        <div className="text-[13.5px] leading-relaxed">
          <p className="font-medium text-foreground">
            Draft — not yet a binding policy.
          </p>
          <p className="mt-1 text-muted-foreground">
            This page describes misuse protections that exist in the product
            today. It does not yet contain a fixed enforcement-appeal
            timeframe, a published rate-limit schedule, or a dedicated
            security-vulnerability reporting channel — those require
            operational sign-off this page does not substitute for.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-8">
        <Section id="scope" heading="Scope">
          <p>
            This Policy applies to the Talvrin website, research workspace,
            APIs and any connected service, wherever made available. It
            applies alongside{' '}
            <Link to="/terms" className="text-foreground underline underline-offset-2 hover:no-underline">
              Terms and Conditions
            </Link>
            ,{' '}
            <Link to="/data-terms" className="text-foreground underline underline-offset-2 hover:no-underline">
              Data &amp; Market Information Terms
            </Link>{' '}
            and{' '}
            <Link to="/ai-terms" className="text-foreground underline underline-offset-2 hover:no-underline">
              AI Terms of Use
            </Link>
            . Access to a visible page or endpoint does not by itself
            authorise a use beyond what your account is entitled to.
          </p>
        </Section>

        <Section id="accounts" heading="Account and workspace boundaries">
          <p>
            Access is scoped to your own account and workspace, enforced at
            the database level rather than only in the interface — a request
            acting for one account cannot read another account's data, and an
            administrator of one workspace has no standing access to another.
            Do not share credentials, circumvent seat counts, or attempt
            cross-tenant access.
          </p>
        </Section>

        <Section id="data-use" heading="Licensed data: viewing is not reuse">
          <p>
            A display, export or citation permission does not by itself grant
            a right to republish, redistribute, bulk-extract or use licensed
            market data to train a model. Each action — view, store, export,
            embed, display — is evaluated and authorised separately, not
            granted wholesale because you can see a screen. See{' '}
            <Link to="/data-terms" className="text-foreground underline underline-offset-2 hover:no-underline">
              Data &amp; Market Information Terms
            </Link>{' '}
            for the specific rights position on each source.
          </p>
        </Section>

        <Section id="automation" heading="Automation and API conduct">
          <p>
            Automated scraping of the interface is not a substitute for a real
            API entitlement and is not permitted. Usage against your plan's
            limits — watchlists, active monitoring rules, research runs and
            evidence exports — is measured per account; attempting to defeat
            that measurement by rotating accounts or credentials is a
            violation of this Policy.
          </p>
        </Section>

        <Section id="ai-misuse" heading="AI misuse">
          <p>
            Do not attempt prompt injection, jailbreaks or crafted input
            intended to make an AI feature bypass entitlement checks, reveal
            another tenant's data, or take an action it has no authority to
            take. See{' '}
            <Link to="/ai-terms" className="text-foreground underline underline-offset-2 hover:no-underline">
              AI Terms of Use
            </Link>{' '}
            for what the AI Gateway is actually built to refuse.
          </p>
        </Section>

        <Section id="integrity" heading="Research and evidence integrity">
          <p>
            Do not remove or falsify a source's identity, publication date,
            effective date or correction history from research evidence, or
            present a corrected, superseded or AI-generated statement as an
            original source record. The platform's own bitemporal fact model
            exists specifically so a correction is shown as a correction, not
            quietly substituted for the original.
          </p>
        </Section>

        <Section id="prohibited" heading="Prohibited conduct">
          <ul className="flex flex-col gap-2.5">
            {PROHIBITED.map((t) => (
              <li key={t} className="flex gap-2.5">
                <X className="mt-0.5 h-4 w-4 shrink-0 text-stale" />
                <span>{t}</span>
              </li>
            ))}
          </ul>
        </Section>

        <Section id="enforcement" heading="Enforcement">
          <Bullets
            items={[
              'Where a violation is reasonably believed to have occurred, access to the affected feature or account may be limited, suspended or revoked, proportionate to the severity and risk involved.',
              'An urgent security or legal-risk event may require protective action before ordinary notice.',
              'Legitimate use — including correcting a data error or raising a good-faith complaint — is not treated as a violation.',
            ]}
          />
        </Section>

        <Section id="contact" heading="Reporting a concern">
          <p>
            Report a suspected violation, a compromised account, or a
            non-sensitive policy question through{' '}
            <Link to="/contact" className="text-foreground underline underline-offset-2 hover:no-underline">
              Contact
            </Link>
            . Do not include passwords, authentication secrets or exploit
            details in a general enquiry — a dedicated secure
            vulnerability-reporting channel is not yet published.
          </p>
        </Section>
      </div>
    </PageLayout>
  )
}
