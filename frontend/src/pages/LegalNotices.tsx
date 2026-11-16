import { AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import PageLayout, { Section, type TocEntry } from '@/components/layouts/PageLayout'

/**
 * Legal Notices & Disclosures page.
 *
 * Deliberately does not state a registered company name, registration
 * number, or a specific headquarters/service-of-process address - those are
 * exactly the corporate facts Privacy.tsx already declines to invent, and
 * the project's own legal-readiness review (TAL-LGL-ASSURE-001, F01)
 * flags corporate identity as unreconciled. This page gives the honest
 * minimum (operated by Zoiko Group, as CLAUDE.md states) and points to
 * Contact rather than fabricating the rest.
 */
const TOC: TocEntry[] = [
  { id: 'about', label: 'About these notices' },
  { id: 'entity', label: 'Talvrin and Zoiko Group' },
  { id: 'boundary', label: 'Service description and boundary' },
  { id: 'no-advice', label: 'No investment, legal or tax advice' },
  { id: 'provenance', label: 'Source provenance and corrections' },
  { id: 'gilts', label: 'UK gilts and sovereign-debt notices' },
  { id: 'ai', label: 'AI-assisted research' },
  { id: 'ip', label: 'Copyright, trademarks and third-party notices' },
  { id: 'content', label: 'Customer content and tenant boundaries' },
  { id: 'external', label: 'External sites' },
  { id: 'corrections', label: 'Reporting an error or infringement' },
  { id: 'contact', label: 'Contact and official notices' },
]

export default function LegalNotices() {
  return (
    <PageLayout
      title="Legal Notices & Disclosures"
      meta="Corporate presentation, source attribution and legal boundaries"
      toc={TOC}
    >
      <div className="mb-9 flex gap-3 rounded-xl border border-delayed/40 bg-delayed/10 px-4 py-3.5">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-delayed" />
        <div className="text-[13.5px] leading-relaxed">
          <p className="font-medium text-foreground">
            Draft — corporate identity details are not yet finalized here.
          </p>
          <p className="mt-1 text-muted-foreground">
            This page does not yet state a registered company name,
            registration number, or a verified service-of-process address —
            those require corporate and legal confirmation this page does not
            invent. Until published, use Contact for anything that would
            otherwise need one of those facts.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-8">
        <Section id="about" heading="About these notices">
          <p>
            These notices explain Talvrin's corporate presentation, the nature
            and limitations of its research, and important source and
            intellectual-property information. They sit alongside, and do not
            replace,{' '}
            <Link to="/terms" className="text-foreground underline underline-offset-2 hover:no-underline">
              Terms and Conditions
            </Link>
            ,{' '}
            <Link to="/data-terms" className="text-foreground underline underline-offset-2 hover:no-underline">
              Data &amp; Market Information Terms
            </Link>{' '}
            or{' '}
            <Link to="/privacy" className="text-foreground underline underline-offset-2 hover:no-underline">
              Privacy
            </Link>
            .
          </p>
        </Section>

        <Section id="entity" heading="Talvrin and Zoiko Group">
          <p>
            Talvrin is a product of Zoiko Group. A full legal-entity
            disclosure — exact registered name, formation jurisdiction and a
            verified registration identifier — is not published here yet; see
            the notice above. Do not infer a company number or registered
            office from this page.
          </p>
        </Section>

        <Section id="boundary" heading="Service description and boundary">
          <p>
            Talvrin is a source-linked research and monitoring platform for
            public markets. Depending on your plan, it may show issuer
            information, historical data, sovereign-debt analytics,
            calculations, source links, saved research, monitoring and
            AI-assisted explanations. It is not a brokerage, exchange, trading
            venue, custodian, or discretionary asset manager, and nothing in
            it executes a transaction.
          </p>
        </Section>

        <Section id="no-advice" heading="No investment, legal or tax advice">
          <p>
            Talvrin's research, calculations and AI-assisted explanations are
            for information and independent research. They are not
            personalised investment, legal, tax or accounting advice, and are
            not an assessment of suitability for a transaction. See{' '}
            <Link to="/disclaimers" className="text-foreground underline underline-offset-2 hover:no-underline">
              Disclaimers
            </Link>{' '}
            for the product's full position on this.
          </p>
        </Section>

        <Section id="provenance" heading="Source provenance and corrections">
          <p>
            Information may originate from issuers, government departments,
            exchanges and data vendors, and can be delayed, corrected or
            inconsistent across sources. Talvrin's data model keeps raw
            observations, reconciled accepted facts and calculated results as
            three separate, traceable classes, so a correction is shown as a
            correction rather than silently overwriting history.
          </p>
        </Section>

        <Section id="gilts" heading="UK gilts and sovereign-debt notices">
          <p>
            See{' '}
            <Link to="/data-terms" className="text-foreground underline underline-offset-2 hover:no-underline">
              Data &amp; Market Information Terms
            </Link>{' '}
            for the current, specific position on UK gilt and sovereign-debt
            pricing rights, including the noncommercial basis on which
            FTSE-Tradeweb reference prices are currently used.
          </p>
        </Section>

        <Section id="ai" heading="AI-assisted research">
          <p>
            Where a response is AI-assisted, it is labelled as such. AI output
            can paraphrase incorrectly, omit context or misstate a figure — it
            does not replace the underlying source record or a verified
            calculation. See{' '}
            <Link to="/ai-terms" className="text-foreground underline underline-offset-2 hover:no-underline">
              AI Terms of Use
            </Link>
            .
          </p>
        </Section>

        <Section id="ip" heading="Copyright, trademarks and third-party notices">
          <p>
            Talvrin's own software, interfaces and authored descriptions are
            reserved to the extent the law provides. Rights in third-party
            market data, official documents and supplier materials remain
            with their respective owners; their appearance in Talvrin does not
            imply endorsement or a redistribution grant. A complete
            third-party and open-source software notices register is not yet
            published — its absence is not evidence that no attribution is
            owed, and any required notice remains binding regardless.
          </p>
        </Section>

        <Section id="content" heading="Customer content and tenant boundaries">
          <p>
            Your uploaded documents, research notes and saved queries stay
            scoped to your own account, enforced at the database level, and
            displaying a source citation or an exported chart does not expose
            another account's content or credentials.
          </p>
        </Section>

        <Section id="external" heading="External sites">
          <p>
            Links to government agencies, licensors, regulators and other
            sites are provided for reference. Their content, uptime and
            privacy practices are controlled by that third party, not
            Talvrin, and a link does not imply endorsement or affiliation.
          </p>
        </Section>

        <Section id="corrections" heading="Reporting an error or infringement">
          <p>
            If you believe a Talvrin page contains a factual error, an
            incorrect attribution, or a misuse of your intellectual property,
            tell us the specific page and the issue through{' '}
            <Link to="/contact" className="text-foreground underline underline-offset-2 hover:no-underline">
              Contact
            </Link>
            . A dedicated statutory takedown-notice channel (for example, a
            registered DMCA agent) is not represented as available until it
            has actually been set up and verified.
          </p>
        </Section>

        <Section id="contact" heading="Contact and official notices">
          <p>
            Ordinary correspondence can be sent through{' '}
            <Link to="/contact" className="text-foreground underline underline-offset-2 hover:no-underline">
              Contact
            </Link>
            . A specific address for formal service of legal process is not
            published here — use Contact to reach us until one is confirmed.
          </p>
        </Section>
      </div>
    </PageLayout>
  )
}
