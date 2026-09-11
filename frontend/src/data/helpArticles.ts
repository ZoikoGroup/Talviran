/**
 * Help centre content.
 *
 * Written from the specification estate rather than invented: PRD-001 §11
 * (what Talvrin may and may not answer), EVID-001 (evidence and provenance),
 * DATA-002 (reconciliation and conflict states), RIGHTS-001 (sources, export),
 * AI-001 (the model only explains pre-computed evidence) and FIN-001
 * (deterministic calculations).
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
  | 'What Talvrin will not do'
  | 'Organising research'
  | 'Account'

export const CATEGORIES: Category[] = [
  'Getting started',
  'Sources and evidence',
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
      'talvrin-go is tuned for fast answers to everyday lookups and conventions. talvrin-pro works through deeper evidence chains and multi-step calculations, and takes longer.',
      'Both are held to the same evidence rules. Choosing a different model changes how much work goes into the answer, never whether a figure needs a source.',
      'You can switch models from the pill in the composer at any point, including mid-conversation. Earlier replies keep the model that produced them, shown next to the Talvrin name.',
    ],
  },

  {
    id: 'sources',
    category: 'Sources and evidence',
    question: 'Where does Talvrin’s information come from?',
    answer: [
      'Only from approved sources. For a government bond that means the debt management office or central bank; for a listed company, the exchange it trades on and the company’s own filings; for rules and conventions, the regulator or the market’s own published methodology.',
      'Blogs, forums, news commentary and analyst opinion are not sources. They cannot become facts in Talvrin, which is why the product cannot tell you why a price moved on a given day — that explanation lives in commentary, not in the record.',
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
    id: 'conflict',
    category: 'Sources and evidence',
    question: 'Why does it sometimes say a figure is unavailable or in conflict?',
    answer: [
      'When two sources disagree and no accepted value can be resolved between them, Talvrin shows that conflict explicitly instead of quietly picking one.',
      'It is deliberate. Choosing a number arbitrarily would look more polished and be less trustworthy — you would have no way to know a disagreement existed.',
    ],
  },

  {
    id: 'no-advice',
    category: 'What Talvrin will not do',
    question: 'Why won’t Talvrin tell me whether to buy something?',
    answer: [
      'Talvrin has no buy, sell or hold output — not a cautious one, not a hedged one. There is no response type, API field, alert action or button for it anywhere in the product.',
      'Partly this is regulatory: making personal recommendations about investments is a regulated activity in most jurisdictions. Mostly it is the point of the product. Talvrin’s job is to get you to the evidence quickly and show its working, so the judgement stays yours and is defensible.',
      'If you ask anyway, it will recognise what you meant and route you to the facts, calculations and comparisons that bear on the question.',
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
    id: 'chats-projects',
    category: 'Organising research',
    question: 'How do chats and projects work?',
    answer: [
      'Each question starts a chat, and chats are listed in the sidebar grouped by when you started them — today, yesterday, and so on.',
      'Projects group related chats: a curve you are tracking, an issuer, a client mandate. Create one from the Projects tab, then either start a chat inside it or move an existing chat in — drag it onto the project, or use the ⋯ menu on the chat.',
      'Every chat and project can be renamed or deleted from that same ⋯ menu.',
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
      'Your chats, projects and settings are stored so the product has continuity between sessions. They are not turned into behavioural marketing profiles, are not used to train models, and are not used to infer what kind of investor you are.',
      'In the current prototype this state lives in your own browser and never leaves your device.',
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
    id: 'prototype',
    category: 'Account',
    question: 'Is this the finished product?',
    answer: [
      'No. This build is a working interface on placeholder content. There is no live market data, answers are canned examples, and sign-in does not check credentials against anything.',
      'Do not rely on any figure you see in the current build for a real decision.',
    ],
  },
]
