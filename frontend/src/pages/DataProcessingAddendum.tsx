import { AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import PageLayout, { Bullets, RuleTable, Section, type TocEntry } from '@/components/layouts/PageLayout'

/**
 * Data Processing Addendum page.
 *
 * A DPA is normally an executed exhibit to a signed enterprise agreement,
 * not a one-way public policy page - this describes the processing
 * safeguards this product's architecture actually implements (FORCE ROW
 * LEVEL SECURITY + per-request SET LOCAL account/principal context,
 * envelope encryption of research content, the audit event log, SECURITY
 * DEFINER functions as the only way a cross-account process touches
 * account-scoped data), so an enterprise customer's security review has a
 * real, verifiable starting point. It deliberately does not commit to a
 * specific incident-notification clock, a subprocessor list, or an
 * international-transfer mechanism, because none of those have been
 * operationally verified yet - inventing a number here would be exactly
 * the problem the project's own legal review flagged.
 */
const TOC: TocEntry[] = [
  { id: 'scope', label: 'Scope and roles' },
  { id: 'instructions', label: 'Processing instructions' },
  { id: 'access', label: 'Confidentiality and access' },
  { id: 'security', label: 'Security measures' },
  { id: 'subprocessors', label: 'Subprocessors' },
  { id: 'transfers', label: 'International transfers' },
  { id: 'ai', label: 'AI processing boundary' },
  { id: 'rights', label: 'Assistance with individual rights' },
  { id: 'incidents', label: 'Security incidents' },
  { id: 'deletion', label: 'Return and deletion' },
  { id: 'contact', label: 'Contact' },
]

export default function DataProcessingAddendum() {
  return (
    <PageLayout
      title="Data Processing Addendum"
      meta="The processing safeguards this platform actually implements — not yet an executable contract exhibit"
      toc={TOC}
    >
      <div className="mb-9 flex gap-3 rounded-xl border border-delayed/40 bg-delayed/10 px-4 py-3.5">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-delayed" />
        <div className="text-[13.5px] leading-relaxed">
          <p className="font-medium text-foreground">
            Draft — not yet an executable contract exhibit.
          </p>
          <p className="mt-1 text-muted-foreground">
            This page describes processing safeguards that exist in the
            product today. It does not yet contain a signed subprocessor
            list, an international-transfer mechanism (SCCs / UK IDTA), or
            committed incident-notification and deletion timeframes — those
            require legal and operational sign-off this page does not
            substitute for, and no specific number is promised here until it
            has been verified against the live system.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-8">
        <Section id="scope" heading="Scope and roles">
          <p>
            This addendum is intended to apply where Talvrin processes
            personal data on an enterprise customer's behalf as a processor.
            For an individual account, ordinary processing is covered by{' '}
            <Link to="/privacy" className="text-foreground underline underline-offset-2 hover:no-underline">
              Privacy
            </Link>{' '}
            instead. A specific controller/processor role split for a given
            enterprise workspace is set out in the applicable signed order,
            not assumed here.
          </p>
        </Section>

        <Section id="instructions" heading="Processing instructions">
          <p>
            Customer data is processed only to provide, secure and support the
            service — not sold, not used to enrich an unrelated profile, and
            not used to train a general-purpose model. The research and
            account data you provide stays scoped to your own account;
            nothing in the platform converts it into model training material
            or a behavioural profile as a matter of course.
          </p>
        </Section>

        <Section id="access" heading="Confidentiality and access">
          <p>
            Tenant isolation is enforced in the database itself, not only in
            the interface. Every account-scoped table is protected by
            row-level security with no bypass for the application's own
            database role, and each request explicitly sets which account and
            principal it is acting as before it can read or write anything —
            hiding a row in the UI is never treated as an access control here.
          </p>
          <Bullets
            items={[
              'A process that needs to touch data across accounts — like propagating a correction to multiple customers’ saved research — does so only through a narrowly scoped function built for that one purpose, not a general-purpose bypass.',
              'Credentials, session tokens and similar secrets are never written to logs.',
              'Support and administrative access to account content is not unrestricted by default.',
            ]}
          />
        </Section>

        <Section id="security" heading="Security measures">
          <RuleTable
            rows={[
              ['In transit', 'TLS 1.2 or higher, preferring TLS 1.3 where supported.'],
              ['At rest', 'Managed encryption for databases, object storage, backups and logs; research conversation content is additionally envelope-encrypted per account.'],
              ['Sessions', 'Secure, HttpOnly, SameSite-protected cookies; no privileged session material in browser storage.'],
              ['Isolation', 'Enforced by database row-level security, not by interface-level hiding.'],
            ]}
          />
          <p>
            A specific certification or audit report is not claimed here
            unless it has actually been obtained — see the notice above.
          </p>
        </Section>

        <Section id="subprocessors" heading="Subprocessors">
          <p>
            A versioned, disclosed subprocessor list is not yet published.
            Until one exists, no subprocessor change-notice commitment can be
            made that this page could actually honour — publishing one
            prematurely would be exactly the kind of unverified promise this
            page is built to avoid.
          </p>
        </Section>

        <Section id="transfers" heading="International transfers">
          <p>
            A specific international-transfer mechanism (EU Standard
            Contractual Clauses, UK IDTA or equivalent) is not yet executed.
            Talvrin runs as regional cells, and moving data between regions is
            treated as a residency and rights decision, not an incidental
            side effect of infrastructure — but the specific transfer
            instrument for a given enterprise customer is set out in that
            customer's signed agreement, not asserted generally here.
          </p>
        </Section>

        <Section id="ai" heading="AI processing boundary">
          <p>
            AI-assisted features process account data only where enabled and
            only through the platform's own AI Gateway — the single
            sanctioned path to any model provider. See{' '}
            <Link to="/ai-terms" className="text-foreground underline underline-offset-2 hover:no-underline">
              AI Terms of Use
            </Link>{' '}
            for how that routing is gated and why it fails closed rather than
            falling through to an unapproved provider.
          </p>
        </Section>

        <Section id="rights" heading="Assistance with individual rights">
          <p>
            Where an enterprise customer needs to respond to a data subject's
            access, correction or deletion request concerning data it
            controls, Talvrin intends to provide the account-location, export
            and deletion evidence needed to do so. Talvrin does not respond
            directly to a request about customer-controlled data unless
            authorised or legally required to.
          </p>
        </Section>

        <Section id="incidents" heading="Security incidents">
          <p>
            A specific contractual notification clock (for example, a fixed
            number of hours) is not committed to on this page until it has
            been validated against an actual incident drill — see the notice
            above. The platform's incident process is to detect and classify,
            contain, preserve evidence, remediate the root cause and assess
            which accounts are affected before any notification goes out.
          </p>
        </Section>

        <Section id="deletion" heading="Return and deletion">
          <p>
            A deletion request is tracked as a job recording which stores it
            must reach, any legal holds, and the backup markers it has
            written — so deletion can be evidenced, not just assumed. A
            specific deletion timeframe is not promised here until it has been
            verified against the real data map and backup lifecycle.
          </p>
        </Section>

        <Section id="contact" heading="Contact">
          <p>
            Questions about this addendum or a request for the current status
            of an enterprise agreement can be raised through{' '}
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
