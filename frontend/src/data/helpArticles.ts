/**
 * Help centre content.
 *
 * Written from the specification estate: PRD-001 §11 (scope of answers),
 * EVID-001 (evidence and provenance), DATA-002 (reconciliation and conflict states),
 * RIGHTS-001 (sources, export), AI-001 (model explains pre-assembled evidence),
 * FIN-001 (deterministic calculations), MON-001 (autonomous monitoring daemon),
 * and COMM-001 (commercial billing and organization pods).
 */

export interface Article {
  id: string
  category: Category
  question: string
  /** Paragraphs. Kept as prose so the page stays readable, not a spec dump. */
  answer: string[]
}

export type Category =
  | 'Getting started'
  | 'Sources and evidence'
  | 'Monitoring & Alerts'
  | 'Teams & Organizations'
  | 'What Talvrin will not do'
  | 'Organising research'
  | 'Commercial & Account'

export const CATEGORIES: Category[] = [
  'Getting started',
  'Sources and evidence',
  'Monitoring & Alerts',
  'Teams & Organizations',
  'What Talvrin will not do',
  'Organising research',
  'Commercial & Account',
]

export const ARTICLES: Article[] = [
  {
    id: 'what-is',
    category: 'Getting started',
    question: 'What is Talvrin?',
    answer: [
      'Talvrin is an institutional research, monitoring, and evidence terminal for public markets and corporate securities. You ask a question naturally, but unlike generic LLMs that synthesize from web blogs, Talvrin operates strictly against official primary sources: statutory exchange filings, central bank registries, debt management offices, and verified bitemporal fact tables.',
      'Every response comes back as source-grounded facts and reproducible calculations, with every material figure traceable directly to the underlying filing or regulatory notice.',
    ],
  },
  {
    id: 'ask',
    category: 'Getting started',
    question: 'What can I ask?',
    answer: [
      'Talvrin answers a comprehensive set of institutional questions: explaining an instrument’s terms, financial multiples, or market conventions; summarizing regulatory filings and central bank minutes with line-item citations; decomposing the exact formula and inputs behind bond and equity metrics; running cross-sectional multi-asset comparisons; and exporting compliance-ready PDF research dossiers.',
      'Questions seeking speculative price targets, personal investment advice, or buy/sell/hold ratings are strictly refused by the fail-closed Policy Decision Point (PDP).',
    ],
  },
  {
    id: 'answer-parts',
    category: 'Getting started',
    question: 'What is included in an answer?',
    answer: [
      'An answer includes up to five synchronized elements: a concise explanatory prose summary, a structured table of typed facts, clickable citation badges linking to primary filings, an expandable Evidence Drawer showing raw data payloads, and an Institutional Action Toolbar allowing 1-click PDF dossier export or markdown copying.',
      'The prose is generated last from pre-assembled evidence. The platform structurally forbids AI from inventing a figure and then seeking post-hoc justification.',
    ],
  },
  {
    id: 'models',
    category: 'Getting started',
    question: 'What is the difference between talvrin-go and talvrin-pro?',
    answer: [
      'talvrin-go (powered by Groq Llama 3.3 70B) is optimized for microsecond-latency responses to everyday queries: trading multiples, spot bond yields, coupon schedules, and definition lookups.',
      'talvrin-pro (powered by Gemini 2.5) executes deep multi-source synthesis, complex financial statement reconciliations, cross-border macroeconomic comparisons, and mathematical bond curve decompositions.',
      'Both models adhere strictly to the identical zero-hallucination evidence doctrine. Switching models adjusts analytical depth and speed, never audit rigor.',
    ],
  },

  {
    id: 'sources',
    category: 'Sources and evidence',
    question: 'Where does Talvrin’s information come from?',
    answer: [
      'Exclusively from approved, authoritative primary sources: for sovereign debt, the UK Debt Management Office (DMO) and Bank of England; for listed equities and IPOs, official exchange registries (BSE, NSE India) and regulatory disclosures (SEC EDGAR); for foreign exchange, the European Central Bank (ECB); and for international macroeconomics, DBnomics (IMF, World Bank, OECD).',
      'Unverified forums, social media rumors, and speculative news commentary are completely excluded from the evidence corpus.',
    ],
  },
  {
    id: 'citations',
    category: 'Sources and evidence',
    question: 'How do citations work?',
    answer: [
      'Every factual claim or metric is tagged with a clickable numeric citation badge ([1], [2]). Clicking or hovering over a badge exposes the primary source authority, document title, exact excerpt span, and as-of timestamp.',
      'Where a direct statutory link exists (such as an SEC 10-K or UK DMO bulletin), a direct link button opens the original document in a new tab.',
    ],
  },
  {
    id: 'bitemporal',
    category: 'Sources and evidence',
    question: 'What is bitemporality and why does it matter?',
    answer: [
      'In financial markets, when an event happened in the real world (valid time) often differs from when it was reported or recorded (knowledge time).',
      'Talvrin records both dimensions for every fact using PostgreSQL GiST range constraints. This mathematical guarantee prevents conflicting historical revisions, ensuring you can audit what the platform knew at any exact historical millisecond.',
    ],
  },

  {
    id: 'monitoring-daemon',
    category: 'Monitoring & Alerts',
    question: 'How does the Real-Time Monitoring Daemon work?',
    answer: [
      'Unlike tools that only check prices when a user refreshes the browser, Talvrin runs an autonomous background evaluator daemon loop (scripts/run_monitoring_worker.py --loop).',
      'Every 15 seconds, the daemon sweeps all ARMED rules across all accounts, applies strict multi-tenant Row-Level Security (RLS), tests observed quotes against threshold predicates (CROSSES_ABOVE / CROSSES_BELOW), records heartbeats to the deadman supervisor, and triggers immediate dispatches.',
    ],
  },
  {
    id: 'monitoring-shortcuts',
    category: 'Monitoring & Alerts',
    question: 'How do I arm an alert quickly?',
    answer: [
      'You can arm an alert in 1 click directly from any Watchlist table row, from the Global Screener instant search results, or from the Markets page. Simply click the "Alert" button next to any instrument.',
      'The Set Alert modal opens pre-populated with the asset’s current price, allowing you to define your threshold and delivery preferences in seconds.',
    ],
  },
  {
    id: 'monitoring-channels',
    category: 'Monitoring & Alerts',
    question: 'How will I receive notifications when a rule fires?',
    answer: [
      'Alerts are delivered through two synchronized channels: (1) Immediate in-app notification badges on the terminal header and monitoring feed, and (2) Transactional emails dispatched via Resend from alerts@app.talvrin.com with asset breach summaries and audit timestamps.',
    ],
  },

  {
    id: 'team-seats',
    category: 'Teams & Organizations',
    question: 'How do team memberships and seat quotas work?',
    answer: [
      'Organizations on the Teams or Enterprise tier receive multi-seat workspaces. Account owners (Admins) can invite colleagues by email, allocate seats, and track quota consumption in real time.',
      'All team members draw from pooled organizational quota buckets (e.g. 125 active monitoring rules, 400 research runs per month).',
    ],
  },
  {
    id: 'team-roles',
    category: 'Teams & Organizations',
    question: 'What roles are available for team members?',
    answer: [
      'Talvrin provides three granular roles: Admin (governance, billing, member invites, seat changes, and member removal), Analyst (full research, model switching, rule creation, watchlist management, and dossier export), and Viewer (read-only exploration of shared watchlists and past research).',
    ],
  },
  {
    id: 'team-invites',
    category: 'Teams & Organizations',
    question: 'How do colleague onboarding invitations work?',
    answer: [
      'When an admin invites a colleague, a secure 7-day token is generated and delivered via an official branded Resend email. The recipient clicks the link to open /join, completes signup or signin with Supabase Auth, and is bound directly to the organization account with zero account bleed or cross-tenant risk.',
    ],
  },

  {
    id: 'no-advice',
    category: 'What Talvrin will not do',
    question: 'Why won’t Talvrin tell me whether to buy or sell an asset?',
    answer: [
      'Talvrin has no buy, sell, or hold outputs. There is no API field, UI badge, or model prompt that produces trading advice.',
      'Providing personal recommendations is a regulated activity. More importantly, Talvrin is built to give institutional analysts audit-grade facts and calculations so the investment judgment remains yours and is 100% defensible to auditors, compliance officers, and investment committees.',
    ],
  },
  {
    id: 'no-ranking',
    category: 'What Talvrin will not do',
    question: 'Can I get a list of "top pick" stocks?',
    answer: [
      'No. Talvrin does not rank assets by subjective merit, because ranking securities by attractiveness is a recommendation disguised as a table.',
      'You can benchmark and compare any set of instruments in the Comparison Engine on objective metrics (P/E, ROIC, EV/EBITDA, Net Debt), but the sorting and filtering criteria remain under your control.',
    ],
  },
  {
    id: 'no-execution',
    category: 'What Talvrin will not do',
    question: 'Can I execute trades directly through Talvrin?',
    answer: [
      'No. Talvrin is purely an evidence, research, and monitoring terminal. It contains no broker integrations, execution venues, or order routing paths.',
    ],
  },

  {
    id: 'dossier-export',
    category: 'Organising research',
    question: 'How do I export an institutional research dossier?',
    answer: [
      'Beneath any assistant message in the research workspace, click "Export Dossier (PDF)".',
      'This generates an A4 print-optimized research dossier containing the complete analysis, executive findings, citation verification matrix, and an automated cryptographic SHA-256 evidence integrity hash.',
      'You can also click "Copy" to copy the entire response with markdown citation links directly to your clipboard.',
    ],
  },
  {
    id: 'compare-tool',
    category: 'Organising research',
    question: 'How does the Asset & Evidence Comparison Engine work?',
    answer: [
      'Navigate to Compare in the sidebar (/compare). Start with a clean empty slate and search for up to 6 custom instruments across global equities, IPOs, or sovereign debt.',
      'The system builds an automatic cross-sectional valuation matrix and statutory filing audit trail that you can export as Markdown or PDF.',
    ],
  },
  {
    id: 'commercial-billing',
    category: 'Commercial & Account',
    question: 'How do subscription tiers and billing cancellation work?',
    answer: [
      'Talvrin offers Starter, Professional, Teams, and Enterprise tiers with transparent limits on monitoring rules, research runs, and dossier exports.',
      'You can upgrade anytime via Stripe Checkout. If you cancel an active subscription, Talvrin honors cancel_at_period_end: your paid tier entitlements remain active until the end of your billing cycle, after which it safely downgrades with zero sudden access loss.',
      'All past invoices and Stripe payment receipts are accessible in Settings > Invoices & Billing History with downloadable PDF tax receipts.',
    ],
  },
  {
    id: 'security-rls',
    category: 'Commercial & Account',
    question: 'How is multi-tenant security and data isolation enforced?',
    answer: [
      'Every query, rule evaluation, watchlist item, and invitation is guarded by PostgreSQL Row-Level Security (RLS) bound strictly to the caller’s app.account_id.',
      'Direct table queries without matching account context return zero rows, guaranteeing zero Insecure Direct Object Reference (IDOR) vulnerabilities across corporate tenants.',
    ],
  },
]
