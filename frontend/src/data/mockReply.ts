/**
 * Placeholder reply logic for the UI prototype.
 *
 * There is no backend wired up yet. This exists purely so the interface can be
 * demonstrated end-to-end. When the real API lands (see docs/API-001), this file
 * is replaced by a call to `POST /api/v1/research`.
 *
 * Two pieces of real product behaviour are modelled here:
 *  - the recommendation-safe guardrail (PRD-001 §11 / POL-001)
 *  - the shape of a grounded answer: prose + typed facts + evidence citations
 *    (EVID-001), where every material number carries a source.
 */

export type Freshness = 'CURRENT' | 'DELAYED' | 'STALE' | 'SOURCE'
export type CiteKind = 'doc' | 'book' | 'link'

export interface Citation {
  label: string
  meta?: string
  pill: Freshness
  kind: CiteKind
}

export interface FactTable {
  title: string
  rows: [string, string][]
}

export interface Reply {
  text: string
  facts: FactTable | null
  citations: Citation[]
  note: string | null
}

export interface ChatMessage extends Partial<Reply> {
  role: 'user' | 'assistant'
  text: string
  /** Which model answered — stamped at send time, shown in the transcript. */
  model?: string
}

const ADVICE_PATTERNS = [
  /should i (buy|sell|invest|hold)/i,
  /\b(is|are) (it|this|these|that) a good (buy|investment|idea)\b/i,
  /what should i (buy|invest|pick)/i,
  /\b(best|top|worst) (bond|gilt|treasury|pick|investment)s?\b/i,
  /\b(price target|fair value|rating|recommend)\b/i,
  /worth (buying|investing)/i,
]

const isAdvice = (t: string) => ADVICE_PATTERNS.some((re) => re.test(t))
const mentionsGilt = (t: string) => /\bgilt|treasury gilt|2036\b/i.test(t)
const mentionsAccrued = (t: string) =>
  /accrued|day count|convention|clean|dirty|act\/act/i.test(t)

/* ---------- canned payloads ---------- */

const ADVICE_REPLY: Reply = {
  text:
    'I can’t tell you whether to buy, sell or hold. Talvrin never produces investment ' +
    'recommendations, price targets, rankings or suitability conclusions — by design.\n\n' +
    'What I can give you is the evidence to decide for yourself:\n\n' +
    '•  The instrument’s terms and source-linked facts\n' +
    '•  A reproducible yield and cash-flow calculation\n' +
    '•  A side-by-side comparison against an instrument you pick\n' +
    '•  An objective alert on a threshold you set\n\n' +
    'Which would help?',
  facts: null,
  citations: [],
  note:
    'Redirected by the recommendation-safe perimeter. No response type for buy/sell/hold ' +
    'exists in the platform (PRD-001 §11, POL-001).',
}

const GILT_REPLY: Reply = {
  text:
    'Here are the canonical terms for the 4¼% Treasury Gilt 2036, as accepted by the ' +
    'platform. Each value below resolves to a source observation — open Evidence to ' +
    'trace any of them.',
  facts: {
    title: 'Instrument facts',
    rows: [
      ['Instrument', '4¼% Treasury Gilt 2036'],
      ['ISIN', 'GB00BDX8CX86'],
      ['Coupon', '4.250% semi-annual'],
      ['Maturity', '07 Jun 2036'],
      ['Day count', 'ACT/ACT (ICMA)'],
      ['Ex-dividend', '7 business days'],
      ['Currency', 'GBP'],
    ],
  },
  citations: [
    { label: 'UK DMO — Gilts in Issue', meta: 'Published 08 Sep 2026 · 06:00 BST', pill: 'CURRENT', kind: 'doc' },
    { label: 'UK DMO — Gilt Formulae and Examples, 4th ed.', meta: 'Pinned methodology · 18 Dec 2024', pill: 'SOURCE', kind: 'book' },
    { label: 'Accepted fact set · knowledge-time 2026-09-08T16:30Z', meta: '7 facts · reconciled, no conflicts', pill: 'CURRENT', kind: 'link' },
  ],
  note: null,
}

const ACCRUED_REPLY: Reply = {
  text:
    'Accrued interest is the coupon a bond has earned but not yet paid, from the last ' +
    'coupon date up to settlement. The buyer pays it to the seller on top of the clean ' +
    'price.\n\n' +
    '**Clean price** quotes the bond excluding accrued interest — this is how gilts and ' +
    'Treasuries are quoted.\n' +
    '**Dirty price** is what actually settles: clean price + accrued interest.\n\n' +
    'For gilts the accrual uses ACT/ACT (ICMA), and the ex-dividend convention means a ' +
    'buyer inside the ex-dividend window is not entitled to the next coupon — accrued ' +
    'interest then goes negative.',
  facts: null,
  citations: [
    { label: 'UK DMO — Gilt Formulae and Examples, 4th ed. §2', meta: 'Accrued interest & ex-dividend · 18 Dec 2024', pill: 'SOURCE', kind: 'book' },
  ],
  note:
    'Explanation only — no calculation was performed. Run the calculator for a figure ' +
    'tied to a specific settlement date.',
}

const DEFAULT_REPLY = (q: string): Reply => ({
  text:
    `You asked: “${q}”\n\n` +
    'This is a front-end prototype — the backend is not connected yet, so this is a ' +
    'placeholder response.\n\n' +
    'Once the evidence layer is live, answers here will be assembled only from accepted ' +
    'facts and deterministic calculations, with every material number resolving to a ' +
    'citation like the one below.',
  facts: null,
  citations: [
    { label: 'Placeholder evidence reference', meta: 'No backend connected', pill: 'SOURCE', kind: 'link' },
  ],
  note: null,
})

export function buildReply(userText: string): Reply {
  if (isAdvice(userText)) return ADVICE_REPLY
  if (mentionsAccrued(userText)) return ACCRUED_REPLY
  if (mentionsGilt(userText)) return GILT_REPLY
  return DEFAULT_REPLY(userText)
}
