/**
 * Comprehensive Institutional Guides & Documentation Data for Talvrin
 * Rooted in the engineering doctrines: PRD-001, EVID-001, DATA-002, FIN-001, AI-001, SEC-001, MON-001
 */

export interface GuideExampleQuery {
  title: string
  query: string
  model: 'talvrin-go' | 'talvrin-pro'
  description: string
  outputType: string
}

export interface GuideSection {
  id: string
  title: string
  badge?: string
  content: string[]
  keyPoints?: string[]
  codeSnippet?: string
  exampleQueries?: GuideExampleQuery[]
  caution?: string
}

export interface GuideTopic {
  id: string
  title: string
  slug: string
  category: 'Fundamentals' | 'How to Use Talvrin' | 'Platform Surfaces' | 'Cookbook' | 'Markets & Calculations' | 'Governance & Integrity'
  summary: string
  readTimeMinutes: number
  sections: GuideSection[]
}

export const GUIDE_TOPICS: GuideTopic[] = [
  {
    id: 'how-to-use',
    title: '1. How to Use Talvrin: Step-by-Step User Manual',
    slug: 'how-to-use',
    category: 'How to Use Talvrin',
    readTimeMinutes: 7,
    summary: 'A complete end-to-end practical manual for analysts: signing in, initiating research, verifying citations, setting monitoring rules, and building comparative models.',
    sections: [
      {
        id: 'user-journey-compose',
        title: 'Starting a Research Session',
        badge: 'Core Workflow',
        content: [
          'When you open Talvrin, you arrive at the Compose Screen. Unlike generic chatbots, every inquiry in Talvrin generates an evidence-grounded answer containing facts, formulas, and verified source spans.',
          'Type an inquiry regarding an instrument, sovereign yield curve, monetary policy decision, or benchmark comparison into the composer.',
          'Use the Model Switcher pill in the composer to select between talvrin-go and talvrin-pro based on the complexity of your request.'
        ],
        keyPoints: [
          'Selecting Your Model: Choose talvrin-go (Groq) for rapid convention lookups and spot metrics; choose talvrin-pro (Gemini) for multi-source evidence synthesis and mathematical decompositions.',
          'Attaching Context & Assets: Tag specific sovereign instruments or tickers to focus retrieval strictly on those entities.'
        ]
      },
      {
        id: 'inspecting-evidence',
        title: 'Inspecting Evidence, Citations & Facts',
        badge: 'Audit Transparency',
        content: [
          'Every figure rendered in Talvrin is hyper-auditable. When an answer completes, you will see three distinct elements:'
        ],
        keyPoints: [
          'Interactive Fact Table: Displays accepted canonical metrics with exact units, timestamps, and confidence states.',
          'Citation Badges ([1], [2]): Click any citation badge to view the exact excerpt, source institution, document name, and as-of timestamp.',
          'Evidence Drawer: Open the Evidence panel at the bottom of any message to inspect the full list of underlying SourceObservations, raw API payloads, and calculation inputs.',
          'Copy & Export: You can copy formatted markdown summaries or export structured fact tables directly to Excel or institutional presentations.'
        ]
      },
      {
        id: 'setting-alerts-step-by-step',
        title: 'Configuring Real-Time Monitoring & Alerts',
        badge: 'Monitoring Engine',
        content: [
          'Talvrin features continuous institutional monitoring so you never miss critical market threshold shifts.'
        ],
        keyPoints: [
          'Step 1: Navigate to the Monitoring tab from the sidebar, or click "Set Alert" on any asset card in Markets or the Dashboard.',
          'Step 2: Choose your metric (e.g., 10Y Benchmark Gilt Yield, 2Y/10Y Spread Differential, BoE Policy Rate).',
          'Step 3: Define your condition (e.g. "Crosses Above 4.50%", "Inverts Below 0 bps", or "Changes by more than 10 bps in 24 hours").',
          'Step 4: Select delivery channels (Immediate In-App Notification and/or Institutional Email Dispatch).',
          'Liveness Assurance: All active rules are monitored by coverage trackers and dead-man watchdogs to guarantee zero silent failures.'
        ]
      },
      {
        id: 'running-comparisons',
        title: 'Comparing Multi-Asset Structures',
        content: [
          'Use the Comparison Engine to benchmark instruments side-by-side:'
        ],
        keyPoints: [
          'Select "Compare" in the sidebar or tag multiple assets in the search modal.',
          'Add up to 4 instruments across sovereign curves, corporate credit, or foreign exchange.',
          'The comparison matrix automatically aligns coupon rates, modified duration, convexity, YTM, and spread to benchmark in an easy-to-read tabular grid.'
        ]
      },
      {
        id: 'keyboard-shortcuts',
        title: 'Keyboard Shortcuts & Navigation Tips',
        content: [
          'Accelerate your institutional workflow with built-in desktop hotkeys:'
        ],
        keyPoints: [
          'Ctrl / Cmd + K: Open global search across all instruments, issuers, and past research.',
          'Ctrl / Cmd + B: Toggle sidebar expansion between collapsed icon rail and full sidebar panel.',
          'Enter: Send prompt (Shift + Enter for multi-line drafting).',
          'Esc: Instantly dismiss modal dialogs, drawers, and active search prompts.'
        ]
      }
    ]
  },
  {
    id: 'getting-started',
    title: '2. The Talvrin Doctrine & Architecture',
    slug: 'doctrine-architecture',
    category: 'Fundamentals',
    readTimeMinutes: 5,
    summary: 'The immutable engineering principles separating Talvrin from generic LLMs: three truth classes, bitemporal facts, and fail-closed policy.',
    sections: [
      {
        id: 'doctrine-three-classes',
        title: 'Three Separate Truth Classes',
        badge: 'Core Architecture',
        content: [
          'Talvrin enforces a strict separation between raw observation, canonical truth, and mathematical computation. The generative AI model is structurally forbidden from writing to any of these layers.',
          'Instead of asking an LLM to remember financial values, Talvrin retrieves or computes verified evidence first, and uses AI exclusively to explain pre-assembled evidence to the analyst.'
        ],
        keyPoints: [
          '1. SourceObservation: The raw, immutable payload exactly as transmitted by the provider (DMO, BoE, ECB, DBnomics, Twelve Data). Contains transport metadata and raw checksums.',
          '2. AcceptedFact: Reconciled canonical truth. Produced strictly via deterministic ingestion pipelines (reconcile_and_publish), never by heuristic AI.',
          '3. CalculationResult: Deterministic, golden-tested financial math executed via approved specification algorithms (FIN-001).',
          'EvidenceBundle: An immutable cryptographic bundle tying together every fact, calculation, and document span behind an answer.'
        ]
      },
      {
        id: 'bitemporal-integrity',
        title: 'Bitemporal Fact Records',
        badge: 'GiST Exclusion',
        content: [
          'Every accepted market fact carries two independent time coordinates in PostgreSQL:',
          '• Valid Range (valid_range): The real-world timeframe during which the fact was true.',
          '• Knowledge Range (knowledge_range): The timeframe during which the Talvrin platform recognized the fact.',
          'A GiST exclusion constraint on the database physically prohibits two overlapping versions of the same fact from coexisting, guaranteeing complete historical auditability.'
        ]
      },
      {
        id: 'fail-closed-pdp',
        title: 'Fail-Closed Policy Decision Point (PDP)',
        badge: 'Policy Perimeter',
        content: [
          'Talvrin enforces compliance at the code level (policy.pdp), not merely via prompt engineering.',
          'Any request that solicits investment recommendations, price targets, buy/sell/hold ratings, or subjective speculation is rejected server-side against an exhaustive AllowedOutputType enum.'
        ],
        caution: 'Talvrin will never speculate or provide suitability advice. If a question cannot be grounded in factual evidence, it is rejected.'
      }
    ]
  },
  {
    id: 'platform-surfaces',
    title: '3. Platform Surfaces & Navigational Tour',
    slug: 'platform-surfaces',
    category: 'Platform Surfaces',
    readTimeMinutes: 6,
    summary: 'Mastering the seven interconnected modules: Home Dashboard, Research Chat, Markets, Watchlists, Comparison Engine, Monitoring, and Settings.',
    sections: [
      {
        id: 'surface-home',
        title: 'Home Dashboard (Command Center)',
        content: [
          'The Home Dashboard provides immediate situational awareness across global asset classes, active monitoring alerts, and pinned watchlists.',
          'Key components include real-time market indices, benchmark gilt yields, active alert feeds, and quick-launch research queries.'
        ],
        keyPoints: [
          'Live Sparklines: Instant visual trends for key sovereign yields and FX pairs.',
          'Active Alerts Feed: Real-time trigger notifications from configured monitoring rules.',
          'Contextual Deep-Linking: Clicking any asset opens its institutional market page or initiates a targeted research session.'
        ]
      },
      {
        id: 'surface-research',
        title: 'Source-Grounded Research Workspace',
        content: [
          'The primary conversational interface for querying facts, decomposing bond mathematics, and cross-referencing regulatory texts.',
          'Each reply renders with an interactive facts table, model attribution pill, citation drawer, and source provenance cards.'
        ],
        keyPoints: [
          'Dual Reasoning Engines: Seamlessly toggle between talvrin-go (Groq fast inference) and talvrin-pro (Gemini 2.5 deep research).',
          'Citation Chips: Hover or click on numerical citations to inspect the exact source observation and timestamp.',
          'Evidence Drawer: Expandable audit panel displaying every underlying accepted fact and calculation result.'
        ]
      },
      {
        id: 'surface-markets',
        title: 'Markets & Asset Intelligence',
        content: [
          'Institutional directory across Gilts, Sovereign Bonds, FX Pairs, Equities, and Macroeconomic series.',
          'Features interactive TradingView chart widgets, depth details, issuer profiles, and direct calculation hooks.'
        ]
      },
      {
        id: 'surface-compare',
        title: 'Multi-Asset Comparison Engine',
        content: [
          'Side-by-side structural comparison of up to 4 instruments or macro series.',
          'Enables instant spread analysis, coupon structure evaluation, yield-to-maturity divergence, and duration sensitivity benchmarking.'
        ]
      },
      {
        id: 'surface-monitoring',
        title: 'Monitoring & Alerting System (MON-001)',
        badge: 'Liveness Guaranteed',
        content: [
          'Institutional monitoring treated as a first-class product surface rather than a background script.',
          'Rules evaluate on deterministic cadences with two independent safety mechanisms: coverage tracking (verifying each specific rule runs) and the dead-man watcher (verifying the evaluator process is alive).'
        ],
        keyPoints: [
          'Threshold Triggers: Set alerts for yield shifts, spread breaches, or fixing deviations.',
          'In-App & Email Delivery: Immediate delivery of trigger events with evidence snapshots.',
          'Coverage Watchdog: Guarantees no silent evaluation failures.'
        ]
      }
    ]
  },
  {
    id: 'query-cookbook',
    title: '4. Query Cookbook: What You Can Ask',
    slug: 'query-cookbook',
    category: 'Cookbook',
    readTimeMinutes: 5,
    summary: 'A reference library of high-impact research prompts with one-click testing in the workspace.',
    sections: [
      {
        id: 'cookbook-fixed-income',
        title: 'Fixed Income & Sovereign Debt',
        content: [
          'Extract precise bond terms, calculate pricing metrics, and analyze yield curve dynamics with verified UK DMO and BoE data:'
        ],
        exampleQueries: [
          {
            title: 'Gilt Spread Differential (10Y vs 2Y)',
            query: 'Compare UK 10Y gilt yield vs 2Y gilt yield spread over the last 6 months with BoE benchmark dates',
            model: 'talvrin-pro',
            description: 'Retrieves accepted sovereign yield curves and computes historical spread differentials.',
            outputType: 'PROSE + FACTS_TABLE + CALCULATION'
          },
          {
            title: 'Modified Duration & Convexity Breakdown',
            query: 'Explain the modified duration and convexity formula for UKT 4.25% 2034 with actual coupon and yield inputs',
            model: 'talvrin-pro',
            description: 'Executes approved golden-corpus bond pricing calculations with full variable audit.',
            outputType: 'CALCULATION_RESULT'
          },
          {
            title: 'Gilt Redemption & Coupon Terms',
            query: 'What are the exact maturity date, coupon payment dates, and ISIN for UK Treasury 0.25% 2025?',
            model: 'talvrin-go',
            description: 'Fetches verified DMO instrument reference terms and alias records.',
            outputType: 'FACTS_TABLE'
          }
        ]
      },
      {
        id: 'cookbook-macro-fx',
        title: 'Macroeconomics, Policy Rates & FX',
        content: [
          'Examine central bank decisions, international macroeconomic indicators, and currency reference rates:'
        ],
        exampleQueries: [
          {
            title: 'BoE Monetary Policy Committee Vote Split',
            query: 'What was the Bank of England Monetary Policy Committee decision on 2024-08-01 and the voting split?',
            model: 'talvrin-go',
            description: 'Fetches verified central bank minutes and accepted policy rate facts.',
            outputType: 'SOURCE_SUMMARY'
          },
          {
            title: 'ECB Daily FX Reference Series',
            query: 'Show daily GBP/EUR and GBP/USD fixing rates for the past 30 days from ECB reference data',
            model: 'talvrin-go',
            description: 'Queries Frankfurter / ECB daily market observations.',
            outputType: 'FACTS_TABLE'
          },
          {
            title: 'Global Macro Comparison via DBnomics',
            query: 'Compare UK CPI inflation rate against Eurozone HICP annual rate for the latest 4 quarters',
            model: 'talvrin-pro',
            description: 'Retrieves multi-provider macro time series with clear agency attribution.',
            outputType: 'FACTS_TABLE + CHART'
          }
        ]
      },
      {
        id: 'cookbook-refused',
        title: 'Refused Queries & How to Reformulate',
        badge: 'Compliance Boundary',
        content: [
          'Talvrin refuses queries seeking investment advice or price targets. Reframe your questions to focus on verified facts and historical precedents:'
        ],
        keyPoints: [
          '❌ Refused: "Is now a good time to buy UK Gilts?"',
          '✅ Reformulated: "What is the historical spread between 10Y UK Gilts and 10Y US Treasuries over the last 12 months?"',
          '❌ Refused: "Predict the closing price of Barclays shares next month."',
          '✅ Reformulated: "What was Barclays\' Common Equity Tier 1 (CET1) ratio reported in their most recent quarterly disclosure?"'
        ]
      }
    ]
  },
  {
    id: 'market-data-freshness',
    title: '5. Ingestion Feeds & Freshness Auditing',
    slug: 'feeds-freshness',
    category: 'Markets & Calculations',
    readTimeMinutes: 4,
    summary: 'The structural lifecycle of market feeds, connector protocols, and freshness states.',
    sections: [
      {
        id: 'connector-protocol',
        title: 'Connector Architecture (DATA-002)',
        content: [
          'All connectors follow an identical, strictly validated protocol: discover → acquire → verify_transport → identify_schema → parse → checkpoint → health.',
          'Connectors are forbidden from performing identity resolution or publishing accepted facts directly. They normalize raw data into SourceObservations, which are then processed by a metric-specific reconciliation policy.'
        ],
        keyPoints: [
          'UK DMO: Gilt operational notices, tap auctions, and redemption values.',
          'Bank of England: Official bank rates and continuous yield curves (nominal & real).',
          'Frankfurter (ECB): European Central Bank daily foreign exchange fixings.',
          'DBnomics: Global macro datasets (IMF, World Bank, OECD, ONS).',
          'Twelve Data: Global equities, intraday prices, and instrument identifiers.'
        ]
      },
      {
        id: 'freshness-indicators',
        title: 'Freshness States & Meaning',
        badge: 'Audit Transparency',
        content: [
          'Every metric possesses a registered FreshnessProfile. An observation is assigned one of four statuses upon evaluation:'
        ],
        keyPoints: [
          'Current (Green): Received and verified within its expected update window.',
          'Delayed (Amber): Older than standard cadence, but within safe tolerance limits.',
          'Stale (Red): Missed expected update cycles; flagged to warn against operational reliance.',
          'Source / Pinned (Blue): Static authoritative reference material (e.g., regulatory methodology or bond prospectus) where age does not represent decay.'
        ]
      }
    ]
  },
  {
    id: 'calculation-specs-gate',
    title: '6. Deterministic Math & Golden Corpus',
    slug: 'deterministic-math',
    category: 'Governance & Integrity',
    readTimeMinutes: 5,
    summary: 'How calculation specifications (FIN-001) are approved via dual independent implementation and golden test fixtures.',
    sections: [
      {
        id: 'golden-corpus-gate',
        title: 'The Golden Corpus Gate',
        badge: 'Dual-Implementation',
        content: [
          'In Talvrin, financial mathematics cannot be written ad-hoc. All formulas (dirty price, clean price, yield-to-maturity, Macauley/modified duration, convexity, and spreads) require an approved calculation_specification.',
          'Before any specification can move from DRAFT to APPROVED, it must pass the golden corpus gate: two separate, independent code implementations must compute identical values across a rigorous fixture of institutional market instruments.'
        ],
        keyPoints: [
          'Dual Independent Implementation: Guaranteed absence of single-developer bias or subtle numerical drift.',
          'Golden Test Fixtures: Real-world benchmark scenarios vetted against institutional terminal baselines.',
          'Asynchronous Compute Queue: Heavy calculation workloads operate through background queues with FOR UPDATE SKIP LOCKED guarantees, avoiding request timeouts.'
        ]
      },
      {
        id: 'supported-formulas',
        title: 'Standard Calculation Specifications',
        content: [
          'Approved calculation engines active in the platform include:'
        ],
        keyPoints: [
          'Bond Dirty & Clean Pricing: Accrued interest calculations using actual/actual ICMA day-count conventions.',
          'Yield to Maturity (YTM): Newton-Raphson polynomial root-finding for semi-annual and annual sovereign coupons.',
          'Modified Duration & Macauley Duration: First-derivative price sensitivity with respect to yield changes.',
          'Bond Convexity: Second-derivative curvature modeling for non-linear interest rate shocks.',
          'Benchmark Spreads: Spot and interpolated spread differentials over risk-free benchmark curves.'
        ]
      }
    ]
  }
]
