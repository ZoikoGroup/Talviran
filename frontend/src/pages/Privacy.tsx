import { AlertTriangle } from 'lucide-react'
import PageLayout, {
  Bullets,
  RuleTable,
  Section,
  type TocEntry,
} from '@/components/layouts/PageLayout'

/**
 * Privacy page.
 *
 * Every statement here is drawn from SEC-001 (Security, Privacy & Access
 * Control) — §4 classification, §15 cryptography, §24.1 log safety, §27
 * privacy engineering, §28 retention/deletion, §29 residency, §30 vendors.
 *
 * What is deliberately NOT here: lawful basis, statutory data-subject rights,
 * the controller's legal identity, a sub-processor list, transfer mechanisms
 * and a complaints route. SEC-001 is an engineering specification and contains
 * none of those — inventing them would be fabricating legal commitments. The
 * notice at the top of the page says so plainly, and POL-001 requires
 * customer-facing copy to be a versioned, approved artefact in any case.
 */
const TOC: TocEntry[] = [
  { id: 'principles', label: 'Principles we build to' },
  { id: 'by-default', label: 'Your research' },
  { id: 'classification', label: 'Data classification' },
  { id: 'retention', label: 'Retention and deletion' },
  { id: 'residency', label: 'Where data lives' },
  { id: 'protection', label: 'How it is protected' },
  { id: 'vendors', label: 'Third parties' },
  { id: 'incidents', label: 'If something goes wrong' },
  { id: 'contact', label: 'Contact' },
]

export default function Privacy() {
  return (
    <PageLayout
      title="Privacy"
      meta="How Talvrin handles your data · Engineering commitments from SEC-001"
      toc={TOC}
    >
      <div className="mb-9 flex gap-3 rounded-xl border border-delayed/40 bg-delayed/10 px-4 py-3.5">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-delayed" />
        <div className="text-[13.5px] leading-relaxed">
          <p className="font-medium text-foreground">
            Draft — not yet a legally operative privacy policy.
          </p>
          <p className="mt-1 text-muted-foreground">
            This page describes the data-handling controls Talvrin is engineered
            to, taken from the internal security specification. It does not yet
            state the controller's legal identity, lawful bases for processing,
            your statutory rights, international transfer mechanisms, a
            sub-processor list, or how to complain to a supervisory authority.
            Those must be drafted and approved by legal counsel before launch.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-8">
        <Section id="principles" heading="The principles we build to">
          <p>
            Privacy is handled as an engineering requirement rather than a
            policy statement bolted on afterwards. These rules are binding on
            the platform's design.
          </p>
          <RuleTable
            rows={[
              ['Data minimisation', 'Collect only product-required user and account data.'],
              ['Purpose limitation', 'Use data only for declared, approved product and security purposes.'],
              ['Separation', 'Keep identity and account data separate from licensed market and evidence content where practical.'],
              ['Access transparency', 'Privileged access to user data is auditable.'],
              ['Deletion', 'A deletion workflow runs across primary and derived stores, subject to legal and contractual retention.'],
              ['Export and access', 'Privacy request workflows are distinct from market-data export rights.'],
              ['Model use', 'No silent user-data model training and no suitability profiling.'],
            ]}
          />
        </Section>

        <Section id="by-default" heading="What we do not do with your research">
          <p>
            Your research history, watchlists and monitoring rules exist so the
            product has continuity between sessions. They are{' '}
            <strong className="font-medium text-foreground">
              not automatically converted into behavioural marketing profiles
            </strong>
            , and they are not used to train models or to infer what sort of
            investor you are.
          </p>
          <p>
            That second point is a product constraint as much as a privacy one:
            Talvrin does not produce suitability conclusions or investment
            advice, so it has no reason to build a profile of your risk appetite.
          </p>
        </Section>

        <Section id="classification" heading="How your data is classified">
          <p>
            Every piece of data carries a sensitivity class that determines how
            it may be stored, logged and accessed. Derived objects inherit the
            highest applicable class unless an approved transformation lowers it.
          </p>
          <RuleTable
            rows={[
              ['S0 — Public', 'Approved public information. Integrity is still required.'],
              ['S1 — Internal', 'Non-public operational and configuration information.'],
              ['S2 — Confidential', 'User and account data, licensed source metadata and content, internal product data.'],
              ['S3 — Restricted', 'Credentials, secrets, security artefacts, sensitive personal data, privileged audit records.'],
            ]}
          />
          <p>
            Logs and traces must not promote confidential or restricted payloads
            into unrestricted observability systems.
          </p>
        </Section>

        <Section id="retention" heading="Retention, deletion and erasure">
          <RuleTable
            rows={[
              ['User account data', 'Retained per product and legal policy; deleted or anonymised when no longer required.'],
              ['Security logs', 'Kept long enough for detection and forensics, with unnecessary personal data minimised.'],
              ['Audit records', 'Retained per governance and legal policy; may require immutable metadata.'],
              ['Licensed market data', 'Source-specific retention and purge rules under the data-rights specification.'],
              ['Evidence artefacts', 'Governed by storage class and the rights attached to the source.'],
              ['Backups', 'Deletions age out through documented backup retention; restores re-apply deletion markers where needed.'],
            ]}
          />
          <p>
            A deletion request is tracked as a job that records the stores it
            must reach, any legal holds, vendor and source constraints, and the
            backup markers it has written — so deletion can be evidenced rather
            than assumed.
          </p>
        </Section>

        <Section id="residency" heading="Where your data lives">
          <p>
            Talvrin runs as regional cells. Your account state is stored and
            processed in a permitted region, encrypted with keys scoped to that
            region.
          </p>
          <Bullets
            items={[
              'Moving data between regions requires a residency, policy and rights classification — it is never incidental.',
              'Backups remain within approved geographies.',
              'Workforce access can be constrained by geography where required.',
              'Third-party providers are assessed for where they process data, independently of where we run.',
              'Disaster recovery does not authorise uncontrolled cross-border replication. If no pre-approved recovery region exists, failover is a policy decision, not an automatic one.',
            ]}
          />
        </Section>

        <Section id="protection" heading="How your data is protected">
          <Bullets
            items={[
              'TLS 1.2 or higher in transit, preferring TLS 1.3 where supported.',
              'Managed encryption at rest for databases, object storage, backups, logs and queues, under a provider-managed KMS or HSM-backed key hierarchy.',
              'Browser sessions use secure, HttpOnly, SameSite-protected cookies. Privileged session material is not stored in browser localStorage.',
              'Passwords, multi-factor secrets, session tokens and private keys are never written to logs, and personal data in logs is masked or minimised.',
              'Tenant isolation is enforced in the database itself, not by the interface — hiding something in the UI is never treated as an access control.',
            ]}
          />
        </Section>

        <Section id="vendors" heading="Third parties and providers">
          <p>
            Providers are reviewed in proportion to the data and access they
            require, and are held to contractual security and privacy
            obligations. We maintain an inventory of providers recording the
            owner, data class, regions and credentials involved, with
            least-privilege access and key rotation. Offboarding a provider
            removes their access and triggers a data purge where relevant, and a
            material incident at a provider enters Talvrin's own incident
            process.
          </p>
        </Section>

        <Section id="incidents" heading="If something goes wrong">
          <p>
            Security incidents follow a defined process: detect and classify,
            contain, preserve evidence, eradicate the root cause and rotate
            affected credentials, recover from a known-good state, then assess
            which users, accounts, jurisdictions and source obligations are
            affected. Where applicable, the legal, privacy and regulatory
            notification process is executed, and the root cause is converted
            into a permanent engineering control.
          </p>
        </Section>

        <Section id="contact" heading="Contact">
          <p>
            A privacy contact route, the identity of the data controller and a
            data-protection contact will be published here once the approved
            policy is in place. Until then, reach us through your usual Zoiko
            Group contact.
          </p>
        </Section>
      </div>
    </PageLayout>
  )
}
