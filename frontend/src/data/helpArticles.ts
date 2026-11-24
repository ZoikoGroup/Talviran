/**
 * Help centre content.
 *
 * Written from the specification estate rather than invented: PRD-001 §11
 * (what Talvrin may and may not answer), EVID-001 (evidence and provenance),
 * DATA-002 (reconciliation and conflict states), RIGHTS-001 (sources, export),
 * AI-001 (the model only explains pre-computed evidence), FIN-001
 * (deterministic calculations), MON-001 (rule-based monitoring) and the
 * commercial module's own real plan/quota definitions.
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
  | 'Account'

export const CATEGORIES: Category[] = [
  'Getting started',
  'Sources and evidence',
  'Monitoring & Alerts',
  'Teams & Organizations',
  'What Talvrin will not do',
  'Organising research',
  'Account',
]

export const ARTICLES: Article[] = [
  {
    id: 'what-is',
    category: 'Getting started',
    question: 'What is Talvrin?',
    answer: [
      'Talvrin is a research and monitoring workspace for public markets. You ask a question the way you would ask any assistant, but instead of searching the open web it draws on official and authoritative sources — exchanges, regulators, central banks and issuer filings.',
      'The answer comes back as source-linked facts and reproducible calculations, with every material figure traceable to the document it came from.',
    ],
  },
  {
    id: 'ask',
    category: 'Getting started',
    question: 'What can I ask?',
    answer: [
      'Talvrin answers a defined set of question types: explaining an instrument term, source fact or market convention; summarising approved source material with citations; explaining the inputs and formula behind a calculation; comparing instruments on metrics you choose; explaining what objective event occurred; and helping you find a particular source or document.',
      'Questions outside those families are not answered — see “Why won’t Talvrin tell me whether to buy something?”.',
    ],
  },
  {
    id: 'answer-parts',
    category: 'Getting started',
    question: 'What is in an answer?',
    answer: [
      'An answer has up to four parts: a short explanation in prose, a table of typed facts where the question calls for one, an Evidence panel listing the sources behind it, and sometimes a note explaining a limitation — for example that an explanation was given but no calculation was performed.',
      'The prose is written last, from evidence that was already assembled. The model never invents a figure and then looks for support.',
    ],
  },
  {
    id: 'models',
    category: 'Getting started',
    question: 'What is the difference between talvrin-go and talvrin-pro?',
    answer: [
      'Use talvrin-go for focused questions and quick lookups. Use talvrin-pro for research that combines multiple sources or requires more detailed analysis and takes longer to run.',
      'Both use the same evidence and access rules. Choosing an engine changes how much work goes into the answer — never whether a figure needs a source, and never which data you are entitled to see.',
      'You can switch engines from the pill in the composer at any point, including mid-conversation. Earlier replies keep the engine that produced them, shown next to the Talvrin name. We do not promise a fixed response time for either engine; actual speed depends on the question.',
    ],
  },

  {
    id: 'sources',
    category: 'Sources and evidence',
    question: 'Where does Talvrin’s information come from?',
    answer: [
      'Only from approved sources. For a government bond that means the debt management office or central bank; for a listed company, the exchange it trades on and the company’s own filings; for foreign exchange and international macroeconomics, named rate-setting and statistical authorities; for rules and conventions, the regulator or the market’s own published methodology.',
      'Blogs, forums, news commentary and analyst opinion are not sources. They cannot become facts in Talvrin, which is why the product cannot tell you why a price moved on a given day — that explanation lives in commentary, not in the record.',
    ],
  },
  {
    id: 'citations',
    category: 'Sources and evidence',
    question: 'How do citations work?',
    answer: [
      'Every factual claim or metric carries a numbered citation. Opening it shows the source document or dataset, the exact passage or observation it came from, and the as-of time.',
      'Where the source is a public filing or bulletin with a stable URL, the citation links directly to it.',
    ],
  },
  {
    id: 'evidence-panel',
    category: 'Sources and evidence',
    question: 'What does the Evidence panel show?',
    answer: [
      'It lists every source behind the answer above it — the document or dataset, when it was published, and a freshness label. Opening it lets you go to the original.',
      'If an answer shows a number and you cannot find that number in the Evidence panel, that is a bug worth reporting.',
    ],
  },
  {
    id: 'freshness',
    category: 'Sources and evidence',
    question: 'What do the freshness labels mean?',
    answer: [
      'Current means the source is within its expected update window. Delayed means it is older than expected but still usable — check the as-of time before relying on it. Stale means the source has not updated when it should have, and the figure should be treated with caution.',
      'Source marks reference material such as a methodology document, where age is not a defect: a pinned convention from 2024 is still authoritative.',
    ],
  },
  {
    id: 'fact-vs-calc',
    category: 'Sources and evidence',
    question: 'What is the difference between a fact and a calculation?',
    answer: [
      'A fact is something a source stated — a coupon rate, a maturity date, a closing price. A calculation is something Talvrin worked out from facts, such as accrued interest or a yield.',
      'The two are shown differently on purpose, because they fail differently. A wrong fact means the source was wrong or was read wrongly; a wrong calculation means the method or its inputs were wrong. Calculations are deterministic and reproducible — the same inputs always produce the same result, and the inputs and formula are shown.',
    ],
  },
  {
    id: 'bitemporal',
    category: 'Sources and evidence',
    question: 'What is bitemporality and why does it matter?',
    answer: [
      'In financial markets, when something became true in the world (valid time) is often different from when the platform learned about it (knowledge time).',
      'Talvrin records both for every accepted fact, enforced by a database-level constraint that rejects two overlapping versions of the same fact. That is what lets a correction update the current view without silently rewriting what an earlier answer said at the time.',
    ],
  },
  {
    id: 'conflict',
    category: 'Sources and evidence',
    question: 'Why does it sometimes say a figure is unavailable or in conflict?',
    answer: [
      'When two sources disagree and no accepted value can be resolved between them, Talvrin shows that conflict explicitly instead of quietly picking one.',
      'It is deliberate. Choosing a number arbitrarily would look more polished and be less trustworthy — you would have no way to know a disagreement existed.',
    ],
  },

  {
    id: 'monitoring-shortcuts',
    category: 'Monitoring & Alerts',
    question: 'How do I arm an alert?',
    answer: [
      'Click "Alert" next to an instrument — from a Watchlist row, the Markets screener, or an asset you have open — and the Set Alert panel opens pre-filled with its current price.',
      'Choose a direction (rises above / falls below) and a threshold. An alert only becomes continuously monitored server-side when the instrument maps to a metric the monitoring engine actually watches; the panel tells you plainly if an alert is a local reminder instead.',
    ],
  },
  {
    id: 'monitoring-channels',
    category: 'Monitoring & Alerts',
    question: 'How will I receive a notification when a rule fires?',
    answer: [
      'In-app, always — a fired alert shows up in Alerts > Trigger History as soon as you are back in the product.',
      'By email, only if you opted into that channel when arming the alert and the environment has a mail transport configured — sent to the address you provided, not a separate marketing list.',
    ],
  },
  {
    id: 'monitoring-daemon',
    category: 'Monitoring & Alerts',
    question: 'Does Talvrin check my alerts even when I am not looking at the app?',
    answer: [
      'Armed rules are evaluated by a background worker process on a short recurring sweep, independent of whether your browser tab is open — not just when you happen to refresh the page.',
      'A separate process watches that worker’s own heartbeat, on the documented principle that an evaluator cannot be trusted to report its own death.',
    ],
  },

  {
    id: 'team-seats',
    category: 'Teams & Organizations',
    question: 'How do team seats and quotas work?',
    answer: [
      'Teams and Enterprise plans support more than one named seat on a single organization account. An administrator invites colleagues and allocates seats up to the plan’s limit.',
      'Quotas (watchlists, monitoring rules, research runs, exports) are pooled across the organization’s seats, not granted separately to each member.',
    ],
  },
  {
    id: 'team-roles',
    category: 'Teams & Organizations',
    question: 'What roles are available for team members?',
    answer: [
      'Admin: billing, member invitations, seat changes and member removal, in addition to full research access. Analyst: full research, monitoring and watchlist access, without billing or membership controls. Viewer: read-only access to shared research and watchlists.',
    ],
  },
  {
    id: 'team-invites',
    category: 'Teams & Organizations',
    question: 'How do colleague invitations work?',
    answer: [
      'An administrator invites a colleague by email from Settings > Team & Organization. The recipient follows the link to create or sign in to their own account, and is attached only to the inviting organization — never to any other tenant’s data.',
    ],
  },

  {
    id: 'no-advice',
    category: 'What Talvrin will not do',
    question: 'Why won’t Talvrin tell me whether to buy or sell an asset?',
    answer: [
      'Talvrin helps you research public markets and inspect the evidence behind the results. It does not provide personalized investment advice or buy, sell or hold recommendations — there is no response type, API field, alert action or button for one anywhere in the product.',
      'Review the sources, assumptions and limitations behind an answer, and make your own decision. If you ask for a recommendation anyway, Talvrin recognizes what you meant and routes you to the facts, calculations and comparisons that bear on the question instead.',
    ],
  },
  {
    id: 'no-ranking',
    category: 'What Talvrin will not do',
    question: 'Can I get a list of the best performing stocks?',
    answer: [
      'Not one Talvrin ranks for you. There is no “top pick”, “best” or platform-authored ranking by merit, because ordering instruments by attractiveness is a recommendation wearing a table’s clothing.',
      'You can compare instruments on metrics you choose, and sort by an objective figure such as yield or maturity. The distinction is who decided the ordering criterion — you, not the platform.',
    ],
  },
  {
    id: 'no-execution',
    category: 'What Talvrin will not do',
    question: 'Can I trade through Talvrin?',
    answer: [
      'No. There is no execution path, no broker link and no order flow. Talvrin is a research platform and is not a broker, dealer or execution venue.',
    ],
  },

  {
    id: 'chats',
    category: 'Organising research',
    question: 'How do chats work?',
    answer: [
      'Each question starts a chat, and chats are listed in the sidebar grouped by when you started them — today, yesterday, and so on.',
      'Every chat can be renamed or deleted from the ⋯ menu beside its name in the sidebar.',
    ],
  },
  {
    id: 'compare-tool',
    category: 'Organising research',
    question: 'How does the Compare page work?',
    answer: [
      'Open Compare in the sidebar and search for up to six instruments across equities, sovereign debt and other covered asset classes.',
      'The page lines them up on the metrics you choose, so you can see them side by side rather than one at a time.',
    ],
  },
  {
    id: 'export',
    category: 'Organising research',
    question: 'Can I export or share what I find?',
    answer: [
      'Within limits set by the source licence, not by us. Viewing a figure on screen and extracting it are different permissions, so exports are allowed per field, capped by record count, and carry the attribution the source requires.',
      'Public sharing links are switched off by default for licensed content, and attribution must survive into exports and screenshots. Where an export is restricted, the restriction comes from the data provider’s licence.',
    ],
  },
  {
    id: 'attachments',
    category: 'Organising research',
    question: 'Can I upload my own documents?',
    answer: [
      'The composer accepts files and images through the + button. In the current build attachments are held alongside your message but are not yet sent anywhere or read — document intelligence is not connected.',
    ],
  },

  {
    id: 'account-data',
    category: 'Account',
    question: 'What happens to my research history?',
    answer: [
      'Your chats, projects and settings are stored on the server against your account, not just in this browser, so they follow you between devices and sessions. They are not turned into behavioral marketing profiles, are not used to train models, and are not used to infer what kind of investor you are.',
      'Research content is encrypted at rest per account. Signing in on a new device loads your existing chats and projects from the server rather than starting empty.',
    ],
  },
  {
    id: 'theme',
    category: 'Account',
    question: 'How do I change the theme?',
    answer: [
      'Open Settings from the gear beside your name in the sidebar, then choose Dark or Light under Appearance. The choice is remembered on that device.',
    ],
  },
  {
    id: 'commercial-billing',
    category: 'Account',
    question: 'How do subscription tiers and cancellation work?',
    answer: [
      'Talvrin offers Explorer (free), Research, Professional, Teams and Enterprise tiers, each with its own limits on watchlists, monitoring rules, research runs and exports — shown in Settings > Billing against your actual current usage.',
      'Upgrades go through Stripe Checkout where Stripe is configured for the environment. Cancelling an active subscription keeps your paid entitlements through the end of the current billing period rather than cutting access off immediately.',
    ],
  },
  {
    id: 'security-rls',
    category: 'Account',
    question: 'How is one organization’s data kept separate from another’s?',
    answer: [
      'Every row that belongs to an account — rules, alerts, watchlists, invitations — is scoped to that account at the database level via PostgreSQL row-level security, not only by application code checking who is asking.',
      'A query running under the wrong account’s context simply returns no rows for data it is not scoped to, rather than relying on every call site remembering to filter correctly.',
    ],
  },
  {
    id: 'prototype',
    category: 'Account',
    question: 'Is this the finished product?',
    answer: [
      'No, but it is not a disconnected demo either. Talvrin runs on real connectors — UK DMO gilts, the Bank of England yield curve, Frankfurter FX rates, DBnomics macro series and Twelve Data equities — reconciled into the platform’s own record, and sign-in is checked by a real authentication provider.',
      'Coverage is still bounded by which sources are connected. Where a figure or capability is not available, the product says so rather than guessing.',
    ],
  },
]
