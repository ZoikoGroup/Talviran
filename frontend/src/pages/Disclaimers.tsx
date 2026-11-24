import PageLayout, { Bullets, Section, type TocEntry } from '@/components/layouts/PageLayout'

/**
 * Disclaimers page.
 *
 * Every statement here already exists, in the same substance, in copy this
 * product already shows live elsewhere (src/data/helpArticles.ts's "What
 * Talvrin will not do" FAQ entries, and Privacy.tsx/Login.tsx's own existing
 * language) - this page consolidates it into one dedicated place rather than
 * asserting anything new. It does not claim a regulatory status, a specific
 * jurisdiction's compliance, or freedom from bias - those are legal
 * conclusions this page is not authorized to make, same boundary Privacy.tsx
 * and Terms.tsx already draw.
 */
const TOC: TocEntry[] = [
  { id: 'not-advice', label: 'Not investment advice' },
  { id: 'not-a-broker', label: 'Not a broker or execution venue' },
  { id: 'no-ranking', label: 'No rankings or recommendations' },
  { id: 'evidence-limits', label: 'Evidence has limits' },
  { id: 'your-decision', label: 'The decision is yours' },
]

export default function Disclaimers() {
  return (
    <PageLayout
      title="Disclaimers"
      meta="What Talvrin is, and is not, built to do"
      toc={TOC}
    >
      <div className="flex flex-col gap-8">
        <Section id="not-advice" heading="Not investment advice">
          <p>
            Talvrin has no buy, sell or hold output — not a cautious one, not a hedged one. There is no response type,
            API field, alert action or button for it anywhere in the product. Nothing Talvrin shows is a personal
            recommendation, and nothing here should be read as one.
          </p>
          <p>
            Talvrin&apos;s job is to get you to the evidence quickly and show its working, so the judgement stays yours
            and is defensible. If you ask it something recommendation-shaped, it will recognise what you meant and
            route you to the facts, calculations and comparisons that bear on the question instead.
          </p>
        </Section>

        <Section id="not-a-broker" heading="Not a broker or execution venue">
          <p>
            There is no execution path, no broker link and no order flow anywhere in this product. Talvrin is a
            research and monitoring platform, not a broker, dealer or execution venue, and using it does not open,
            fund or place an order in any account.
          </p>
        </Section>

        <Section id="no-ranking" heading="No rankings or recommendations">
          <p>
            Talvrin does not rank instruments by attractiveness. There is no &quot;top pick&quot;, &quot;best&quot; or
            platform-authored ordering by merit anywhere in the product — ordering instruments that way is a
            recommendation wearing a table&apos;s clothing. You can compare instruments on metrics you choose, and sort
            by an objective figure such as yield or maturity; the distinction is that you decide the ordering
            criterion, not the platform.
          </p>
        </Section>

        <Section id="evidence-limits" heading="Evidence has limits">
          <Bullets
            items={[
              'A figure is shown only when it traces to a source Talvrin can cite. When it can’t, Talvrin says so rather than estimating.',
              'When two sources disagree and no accepted value can be resolved between them, Talvrin shows that conflict rather than quietly picking one.',
              'Coverage is bounded: an instrument, metric or market Talvrin doesn’t yet connect to is reported as unavailable, not silently substituted with something close.',
              'A reproducible calculation is only as good as the inputs and method behind it — Talvrin publishes both so you can check them, not so the output can be taken on faith.',
            ]}
          />
        </Section>

        <Section id="your-decision" heading="The decision is yours">
          <p>
            Review the sources, assumptions and limitations Talvrin shows you, and make your own decision. Talvrin
            exists to make that review fast and well-evidenced — not to make the decision for you.
          </p>
        </Section>
      </div>
    </PageLayout>
  )
}
