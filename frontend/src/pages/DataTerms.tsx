import { AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import PageLayout, { RuleTable, Section, type TocEntry } from '@/components/layouts/PageLayout'

/**
 * Data & Market Information Terms page.
 *
 * Grounded in RIGHTS-001 (rights.evaluate_action independently gates
 * retrieve/store/embed/display per action) and DATA-001/002 (the
 * SourceObservation -> AcceptedFact -> CalculationResult truth-class
 * separation, bitemporal valid/knowledge ranges, and the real connector
 * list: UK DMO gilts, Bank of England yield curve, Frankfurter FX,
 * DBnomics macro, Twelve Data equities). The UK gilts restriction below
 * states the actual, current operating posture (noncommercial/evaluation
 * use only), not a hypothetical - this platform does not hold a commercial
 * licence for FTSE-Tradeweb gilt reference prices today.
 */
const TOC: TocEntry[] = [
  { id: 'scope', label: 'Scope' },
  { id: 'no-ownership', label: 'No implied ownership' },
  { id: 'permitted-use', label: 'Permitted research use' },
  { id: 'freshness', label: 'Timing, freshness and corrections' },
  { id: 'derived', label: 'Derived and calculated data' },
  { id: 'gilts', label: 'UK gilts and sovereign-debt pricing' },
  { id: 'ai-use', label: 'Use as AI input' },
  { id: 'export', label: 'Export and redistribution' },
  { id: 'identity', label: 'Identity resolution' },
  { id: 'contact', label: 'Contact' },
]

export default function DataTerms() {
  return (
    <PageLayout
      title="Data & Market Information Terms"
      meta="How licensed market data is actually gated in this product — from RIGHTS-001 and DATA-001/002"
      toc={TOC}
    >
      <div className="mb-9 flex gap-3 rounded-xl border border-delayed/40 bg-delayed/10 px-4 py-3.5">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-delayed" />
        <div className="text-[13.5px] leading-relaxed">
          <p className="font-medium text-foreground">
            Draft — not yet a binding contract.
          </p>
          <p className="mt-1 text-muted-foreground">
            This page describes how the platform is engineered to gate market
            data by source and action. It does not yet contain a signed
            per-source rights matrix, a commercial redistribution licence, or
            jurisdiction-specific restrictions beyond what is stated below —
            those require the underlying vendor agreements this page does not
            substitute for.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-8">
        <Section id="scope" heading="Scope">
          <p>
            These terms apply to prices, yields, reference values, calculated
            measures and source metadata made available in Talvrin ("Market
            Information"). They supplement{' '}
            <Link to="/terms" className="text-foreground underline underline-offset-2 hover:no-underline">
              Terms and Conditions
            </Link>
            . Your access to a given dataset depends on your account, plan and
            the entitlement attached to that specific source — access is
            evaluated per action (view, store, embed, export), not granted
            wholesale once you can see a screen.
          </p>
        </Section>

        <Section id="no-ownership" heading="No implied ownership or universal licence">
          <p>
            Viewing a figure in Talvrin does not transfer ownership or a
            general licence in the underlying source dataset. A fact being
            publicly observable — a government department publishing a yield,
            an exchange publishing a price — does not by itself authorise
            commercial reuse, redistribution or model training on it.
          </p>
        </Section>

        <Section id="permitted-use" heading="Permitted research use">
          <p>
            Subject to your account entitlement, you may view and interact
            with available Market Information for your own research. A
            licence to use the platform is not a licence to redistribute the
            underlying data outside it.
          </p>
        </Section>

        <Section id="freshness" heading="Timing, freshness and corrections">
          <p>
            Every fact in Talvrin carries both a validity period (when it was
            true in the world) and a knowledge period (when the platform came
            to believe it) — so a correction never silently overwrites
            history. Freshness is tracked per metric, not assumed: an
            unregistered metric fails closed rather than silently being shown
            as current. Where a fact is later corrected, the prior value and
            the correction are both preserved, and anything built on the
            corrected fact — a saved answer, an alert — is flagged for
            reassessment rather than left silently stale.
          </p>
        </Section>

        <Section id="derived" heading="Derived and calculated data">
          <p>
            A calculated value — a model-implied price derived from a yield
            curve, a duration, a comparison — is tracked as its own kind of
            record, separate from the raw accepted fact it was computed from,
            and carries the version of the method used to produce it. A
            calculation only computes under a method that has passed a
            golden-test and dual-implementation review; nothing computes under
            an unreviewed method.
          </p>
        </Section>

        <Section id="gilts" heading="UK gilts and sovereign-debt pricing">
          <p>
            Talvrin's UK gilt reference prices are sourced from the Bank of
            England's published yield curve and DMO reference data. The UK
            Debt Management Office makes FTSE-Tradeweb end-of-day reference
            prices freely available on a delayed basis for noncommercial use;
            commercial use requires separate rights from that provider.
            Talvrin currently operates on that noncommercial basis and does
            not hold a commercial redistribution licence for those prices —
            this is the platform's actual current position, not a
            placeholder, and it is why some gilt pricing shown is a model
            output derived from the public curve rather than a direct
            commercial quote.
          </p>
        </Section>

        <Section id="ai-use" heading="Use as AI input">
          <p>
            Using Market Information as input to an AI-composed answer is
            governed by the same rights check as display or export — see{' '}
            <Link to="/ai-terms" className="text-foreground underline underline-offset-2 hover:no-underline">
              AI Terms of Use
            </Link>
            . A source whose licence doesn't permit a given use is not
            silently included because a prompt asked for it.
          </p>
        </Section>

        <Section id="export" heading="Export and redistribution">
          <RuleTable
            rows={[
              ['Viewing on screen', 'Permitted within your account entitlements.'],
              ['CSV / export', 'Subject to field-level permission and your plan; evaluated and audited per export, not granted by default.'],
              ['Public links / redistribution', 'Denied by default for licensed source content unless specifically approved.'],
              ['API / automated access', 'Requires a separate entitlement and the source’s own redistribution permission.'],
            ]}
          />
        </Section>

        <Section id="identity" heading="Identity resolution">
          <p>
            Matching a data point to an instrument is deterministic only — an
            exact ISIN or ticker match, never a fuzzy guess. An observation
            that cannot be matched to a known instrument is skipped and
            logged, not silently attached to the closest-looking one.
          </p>
        </Section>

        <Section id="contact" heading="Contact">
          <p>
            Questions about data access, an incorrect source attribution, or a
            licensing concern can be raised through{' '}
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
