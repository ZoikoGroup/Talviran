/**
 * Placeholder reply logic for the UI prototype.
 *
 * There is no backend wired up yet. This exists purely so the interface can be
 * demonstrated end-to-end. When the real API lands (see docs/API-001), this file
 * is replaced by a call to `POST /api/v1/research`.
 *
 * The one piece of real product behaviour modelled here is the
 * recommendation-safe guardrail from PRD-001 / POL-001: a request for
 * investment advice is redirected to factual evidence rather than answered.
 */

const ADVICE_PATTERNS = [
  /should i (buy|sell|invest|hold)/i,
  /\b(is|are) (it|this|these|that) a good (buy|investment|idea)\b/i,
  /what should i (buy|invest|pick)/i,
  /\b(best|top) (bond|gilt|treasury|pick|investment)s?\b/i,
  /\b(price target|fair value|rating)\b/i,
  /worth (buying|investing)/i,
]

const isAdviceRequest = (text) => ADVICE_PATTERNS.some((re) => re.test(text))

const SAMPLE_CITATIONS = [
  { label: 'UK DMO — Gilt Formulae and Examples (4th ed.)', tag: 'SOURCE' },
  { label: 'Accepted fact · as-of 2026-09-08 16:30 UTC', tag: 'CURRENT' },
]

export function buildReply(userText) {
  if (isAdviceRequest(userText)) {
    return {
      text:
        'I can’t tell you whether to buy, sell or hold — Talvrin never gives ' +
        'investment recommendations, price targets or rankings.\n\n' +
        'What I can do instead is show you the evidence so you can decide for yourself:\n\n' +
        '•  The instrument’s terms and source-linked facts\n' +
        '•  A reproducible yield / cash-flow calculation\n' +
        '•  A side-by-side comparison against another instrument you choose\n' +
        '•  An objective alert for a threshold you set\n\n' +
        'Which of those would help?',
      citations: [],
      note: 'Redirected by the recommendation-safe perimeter (PRD-001 §11).',
    }
  }

  return {
    text:
      `You asked: “${userText}”\n\n` +
      'This is a front-end prototype — the backend is not connected yet, so this ' +
      'is a placeholder response.\n\n' +
      'Once the evidence layer is live, an answer here will be assembled only from ' +
      'accepted facts and deterministic calculations, with every material number ' +
      'resolving to a citation shown below.',
    citations: SAMPLE_CITATIONS,
    note: null,
  }
}
