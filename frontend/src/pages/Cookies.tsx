import { useState } from 'react'
import { Info } from 'lucide-react'
import PageLayout, { Bullets, Section, type TocEntry } from '@/components/layouts/PageLayout'

/**
 * Cookies page.
 *
 * Unlike Privacy/Terms, every statement here is a verifiable technical fact
 * about what this app's own code actually does (identity/cookies.py), not a
 * legal conclusion - confirmed by searching the whole codebase for every
 * place a cookie gets set: there is exactly one, `talvrin_session`. No
 * analytics, advertising or tracking cookie exists anywhere in this app.
 * That is why there is nothing to "accept" or "reject" below - the one
 * cookie here is required for sign-in to function at all, so there is no
 * optional category to toggle, and this page does not invent one.
 */
const TOC: TocEntry[] = [
  { id: 'what-we-set', label: 'What this app actually sets' },
  { id: 'why', label: 'Why it exists' },
  { id: 'what-we-dont', label: "What we don't use" },
  { id: 'preferences', label: 'Manage preferences' },
]

export default function Cookies() {
  const [showPreferences, setShowPreferences] = useState(false)

  return (
    <PageLayout
      title="Cookies"
      meta="What this app sets, and why — a technical description, not a legal notice"
      toc={TOC}
    >
      <div className="flex flex-col gap-8">
        <Section id="what-we-set" heading="What this app actually sets">
          <p>
            Talvrin sets exactly one cookie: <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[13px]">talvrin_session</code>.
            It is how the app knows you&apos;re signed in between requests.
          </p>
          <Bullets
            items={[
              'HttpOnly — never readable by any script running on the page, including Talvrin’s own.',
              'Secure outside local development — only sent over an encrypted connection.',
              'SameSite=Lax — blocks it being sent on a cross-site request that could forge an action on your behalf, while still working when you arrive from an external link (an emailed password-reset, for instance).',
              'Host-only — not shared with any other site or subdomain unless explicitly configured.',
              'Expires with your session — a fixed absolute lifetime, and an idle timeout that ends it sooner if you stop using the app.',
            ]}
          />
        </Section>

        <Section id="why" heading="Why it exists">
          <p>
            Without it, the app cannot keep you signed in — every page load would ask you to log in again. It is not used
            for advertising, analytics, personalization or measuring anything about how you use the app.
          </p>
        </Section>

        <Section id="what-we-dont" heading="What we don't use">
          <Bullets
            items={[
              'No analytics cookies.',
              'No advertising or retargeting cookies.',
              'No third-party tracking scripts set cookies of their own on this app.',
              'No cookie reads or writes happen from this app’s own frontend code at all — the session cookie is set and read only by the backend, over HTTPS, never via client-side JavaScript.',
            ]}
          />
        </Section>

        <Section id="preferences" heading="Manage cookie preferences">
          <p>
            Because the only cookie this app sets is strictly required for sign-in to work, there is no optional
            category to turn on or off here — turning it off would simply sign you out.
          </p>
          <button
            type="button"
            onClick={() => setShowPreferences(true)}
            className="w-fit rounded-xl border border-border bg-card px-4 py-2.5 text-[13.5px] font-medium transition-colors hover:bg-accent"
          >
            Manage cookie preferences
          </button>
        </Section>
      </div>

      {showPreferences && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="cookie-preferences-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          onClick={() => setShowPreferences(false)}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start gap-3">
              <Info className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
              <div>
                <h3 id="cookie-preferences-title" className="text-[15px] font-semibold">
                  Cookie preferences
                </h3>
                <p className="mt-2 text-[13.5px] leading-relaxed text-muted-foreground">
                  There&apos;s only one cookie on this app, and it&apos;s required to keep you signed in — there&apos;s
                  nothing optional to switch off. If you&apos;d rather not have it, signing out and not logging back in
                  achieves the same thing.
                </p>
              </div>
            </div>
            <div className="mt-5 flex justify-end">
              <button
                type="button"
                onClick={() => setShowPreferences(false)}
                className="rounded-xl bg-primary px-4 py-2 text-[13px] font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </PageLayout>
  )
}
