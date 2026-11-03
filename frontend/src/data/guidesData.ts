/**
 * Comprehensive Institutional Guides & Documentation Data for Talvrin
 * Rooted in the engineering doctrines: PRD-001, EVID-001, DATA-002, FIN-001, AI-001, SEC-001, MON-001, COMM-001
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
  category:
    | 'Fundamentals'
    | 'How to Use Talvrin'
    | 'Platform Surfaces'
    | 'Cookbook'
    | 'Markets & Calculations'
    | 'Governance & Integrity'
    | 'Enterprise & Collaboration'
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
    readTimeMinutes: 8,
    summary:
      'A complete end-to-end practical manual for analysts: signing in, initiating research, verifying citations, exporting compliance dossiers, arming monitoring rules, and building comparative models.',
    sections: [
      {
        id: 'user-journey-compose',
        title: 'Starting a Research Session & Dual Inference Engines',
        badge: 'Core Workflow',
        content: [
          'When you open Talvrin, you arrive at the Research Workspace. Unlike generic probabilistic chatbots that hallucinate numbers, every response in Talvrin is mathematically deterministic and grounded strictly in verified source evidence.',
          'Type an inquiry regarding an equity, IPO, sovereign yield curve, monetary policy committee decision, or cross-market benchmark comparison into the composer.',
          'Use the Model Switcher pill in the composer to select between talvrin-go and talvrin-pro depending on the analytical depth required.',
        ],
        keyPoints: [
          'talvrin-go (Groq Llama 3.3 70B): Microsecond-latency execution for rapid convention lookups, spot yield fixings, trading multiples, and instrument alias resolutions.',
          'talvrin-pro (Gemini 2.5 Flash / Pro): Deep multi-source evidence synthesis, cross-sectional balance sheet audits, SEC filing reconciliation, and mathematical pricing decompositions.',
          'Instrument Tagging: Tag specific tickers (e.g. AAPL, JPL, HYUNDAI) or curves to restrict retrieval strictly to authoritative entity disclosures.',
        ],
      },
      {
        id: 'inspecting-evidence',
        title: 'Inspecting Evidence, Citations & Facts',
        badge: 'Audit Transparency',
        content: [
          'Every single figure rendered in Talvrin is hyper-auditable. When an answer completes, you will see three distinct elements that guarantee verifiable truth:',
        ],
        keyPoints: [
          'Interactive Fact Table: Displays accepted canonical metrics with exact units, timestamps, and confidence states.',
          'Citation Badges ([1], [2]): Click any citation badge to view the exact excerpt, source institution, document name, and as-of timestamp.',
          'Evidence Drawer: Open the Evidence panel at the bottom of any message to inspect the full list of underlying SourceObservations, raw API payloads, and calculation inputs.',
          'Direct Source Links: Click verified authority pills (e.g. SEC EDGAR, UK DMO, BSE/NSE) to open original filings directly.',
        ],
      },
      {
        id: 'exporting-dossiers',
        title: 'Institutional Research Dossier & PDF Export',
        badge: 'Statutory Export',
        content: [
          'Transform any research finding into an audit-grade, compliance-ready investment memorandum with 1 click.',
          'Located in the action toolbar beneath every assistant message, users can export complete research packs or copy formatted text with source spans.',
        ],
        keyPoints: [
          '1-Click Export Dossier (PDF): Generates a print-optimized, compliance-grade memorandum in A4 format with corporate branding, classification badges, and citation tables.',
          'Cryptographic SHA-256 Hash: Automatically stamps a deterministic evidence fingerprint (e.g. TAL-DOS-7F3A9C12) guaranteeing that figures have not been altered.',
          'Copy with Citations: Copies the entire structured memorandum to your clipboard with clean markdown headers and source citations.',
          'Monthly Quota Tracking: Respects account tier entitlements (Starter: 2/mo, Professional: 25/mo, Teams: 125/mo, Enterprise: 350/mo).',
        ],
      },
      {
        id: 'setting-alerts-step-by-step',
        title: 'Arming Real-Time Price Alerts & Daemon Monitoring',
        badge: 'Monitoring Engine',
        content: [
          'Talvrin features continuous autonomous background monitoring powered by a standing daemon loop so you never miss critical market threshold shifts.',
        ],
        keyPoints: [
          '1-Click Table Row Shortcuts: Arm alerts instantly from Watchlist rows, Global Screener search cards, or Market asset tables without opening chart modals.',
          'Threshold Conditions: Choose between CROSSES_ABOVE or CROSSES_BELOW against live quotes, yields, or spreads.',
          'Multi-Tenant Isolation: Every rule is scoped strictly to your account under PostgreSQL Row-Level Security (RLS).',
          'Autonomous Sweeper Daemon: The background evaluator runs every 15 seconds, checks price observations, records heartbeats, and fires notifications.',
          'Immediate Resend Delivery: Triggered alerts dispatch branded emails directly to your verified inbox (ALERTS_FROM_EMAIL) with asset breach summaries.',
        ],
      },
      {
        id: 'running-comparisons',
        title: 'Running Multi-Asset Structural Comparisons',
        badge: 'Cross-Sectional Matrix',
        content: [
          'Use the Comparison Engine (/compare) to benchmark equities, sovereign bonds, and currencies side-by-side:',
        ],
        keyPoints: [
          'Empty-State Onboarding: Defaults to a clean slate, allowing you to search and pick up to 6 custom instruments.',
          'Session Persistence: Compares are held in sessionStorage so temporary workspaces automatically reset once you leave.',
          'Comprehensive Matrix: Benchmarks Market Cap, P/E (TTM/NTM), EV/EBITDA, ROIC, Gross/Net Margins, YoY Growth, Beta, and Yields.',
          'Export Memoranda: Export comparative analyses as Markdown tables or print-optimized PDF briefs with statutory audit trails.',
        ],
      },
      {
        id: 'keyboard-shortcuts',
        title: 'Keyboard Shortcuts & Fast Navigation',
        content: [
          'Accelerate your institutional analysis with built-in desktop hotkeys:',
        ],
        keyPoints: [
          'Ctrl / Cmd + K: Open global instant search across all global assets, issuers, and past research.',
          'Ctrl / Cmd + B: Toggle sidebar expansion between collapsed icon rail and full expanded navigation.',
          'Enter: Send prompt (Shift + Enter for multi-line drafting).',
          'Esc: Instantly dismiss modal dialogs, search overlays, and open chart panels.',
        ],
      },
    ],
  },
  {
    id: 'getting-started',
    title: '2. The Talvrin Doctrine & Architecture',
    slug: 'doctrine-architecture',
    category: 'Fundamentals',
    readTimeMinutes: 6,
    summary:
      'The immutable engineering principles separating Talvrin from generic LLMs: three truth classes, bitemporal facts, and fail-closed policy.',
    sections: [
      {
        id: 'doctrine-three-classes',
        title: 'Three Separate Truth Classes',
        badge: 'Core Architecture',
        content: [
          'Talvrin enforces an absolute architectural separation between raw observation, canonical truth, and mathematical computation. The generative AI model is structurally forbidden from writing to or altering any of these layers.',
          'Instead of asking an LLM to remember financial values, Talvrin retrieves or computes verified evidence first, and uses AI exclusively to explain pre-assembled evidence to the analyst.',
        ],
        keyPoints: [
          '1. SourceObservation: The raw, immutable payload exactly as transmitted by the provider (SEC EDGAR, UK DMO, Bank of England, ECB, NSE/BSE). Contains transport metadata and SHA-256 checksums.',
          '2. AcceptedFact: Reconciled canonical truth. Produced strictly via deterministic ingestion pipelines (reconcile_and_publish), never by heuristic AI.',
          '3. CalculationResult: Deterministic, golden-tested financial math executed via approved specification algorithms (FIN-001).',
          'EvidenceBundle: An immutable cryptographic bundle tying together every fact, calculation, and document span behind an answer.',
        ],
      },
      {
        id: 'bitemporal-integrity',
        title: 'Bitemporal Fact Records (GiST Non-Overlap)',
        badge: 'GiST Exclusion',
        content: [
          'Every accepted market fact carries two independent time coordinates in PostgreSQL:',
          '• Valid Range (valid_range): The real-world timeframe during which the fact was true.',
          '• Knowledge Range (knowledge_range): The timeframe during which the Talvrin platform recognized the fact.',
          'A GiST exclusion constraint on PostgreSQL physically prohibits two overlapping versions of the same fact from coexisting, guaranteeing zero data collisions and 100% bitemporal auditability.',
        ],
      },
      {
        id: 'fail-closed-pdp',
        title: 'Fail-Closed Policy Decision Point (PDP)',
        badge: 'Policy Perimeter',
        content: [
          'Talvrin enforces regulatory compliance at the code level (policy.pdp), not merely via fragile LLM prompt guidelines.',
          'Any request that solicits investment recommendations, subjective price targets, buy/sell/hold ratings, or market speculation is rejected server-side against an exhaustive AllowedOutputType enum.',
        ],
        caution:
          'Talvrin will never speculate or provide suitability advice. If a question cannot be grounded in factual evidence, it is rejected by the PDP perimeter.',
      },
    ],
  },
  {
    id: 'platform-surfaces',
    title: '3. Platform Surfaces & Navigational Tour',
    slug: 'platform-surfaces',
    category: 'Platform Surfaces',
    readTimeMinutes: 7,
    summary:
      'Mastering the seven interconnected modules: Home Dashboard, Research Chat, Markets Screener, Watchlists, Comparison Engine, Monitoring Daemon, and Organization Settings.',
    sections: [
      {
        id: 'surface-home',
        title: 'Home Dashboard (Command Center)',
        content: [
          'The Home Dashboard provides immediate situational awareness across global asset classes, active monitoring alerts, and pinned watchlists.',
          'Key components include real-time market indices, benchmark gilt yields, active alert feeds, instant asset search, and quick-launch research queries.',
        ],
        keyPoints: [
          'Live Sparklines: Instant visual trends for key sovereign yields, equities, and FX pairs.',
          'Instant Screener Search: Filter matching assets with 1-click Evidence research and Set Alert triggers.',
          'Active Alerts Feed: Real-time trigger notifications from configured monitoring rules.',
          'Contextual Deep-Linking: Clicking any asset opens its institutional market page or initiates a targeted research session.',
        ],
      },
      {
        id: 'surface-research',
        title: 'Source-Grounded Research Workspace',
        content: [
          'The primary conversational interface for querying facts, decomposing bond mathematics, and cross-referencing regulatory texts.',
          'Each reply renders with an interactive facts table, model attribution pill, citation drawer, source provenance cards, and 1-click PDF dossier export.',
        ],
        keyPoints: [
          'Dual Reasoning Engines: Seamlessly toggle between talvrin-go (Groq fast inference) and talvrin-pro (Gemini 2.5 deep research).',
          'Citation Chips: Hover or click on numerical citations to inspect the exact source observation and timestamp.',
          'Dossier Export Toolbar: 1-click PDF download with unique Dossier ID and cryptographic SHA-256 fingerprint.',
          'Evidence Drawer: Expandable audit panel displaying every underlying accepted fact and calculation result.',
        ],
      },
      {
        id: 'surface-markets',
        title: 'Markets & Asset Screener',
        content: [
          'Institutional directory across Indian Equities & IPOs, US Large-Cap Tech, UK Gilts, US Treasuries, FX Pairs, and Macroeconomic series.',
          'Features interactive TradingView chart widgets, native canvas charts with candlestick/area modes, depth details, issuer profiles, and direct 1-click alert buttons.',
        ],
        keyPoints: [
          'Indian IPO & Equities Hub: Real-time post-listing quotes for Jio Platforms (₹1,436.00), Hyundai Motor India (₹2,028.00), Swiggy (₹179.20), NTPC Green (₹82.80), and Pre-IPO DRHP pipelines (NSE-IPO, PhonePe).',
          'Global Equities & Debt: Comprehensive coverage of Apple, Microsoft, Nvidia, UK Gilt Benchmark, US 10Y Treasuries, and ECB Euro FX series.',
        ],
      },
      {
        id: 'surface-watchlists',
        title: 'Watchlists & Portfolio Tracking',
        content: [
          'Create and organize custom observation portfolios across asset classes with live quote feeds, sparklines, and fast alert management.',
        ],
        keyPoints: [
          '1-Click Alert Shortcuts: Arm price alerts on any watchlist asset directly from the row without opening modal charts.',
          'CSV Export: Export complete portfolio holdings and latest quotes for institutional spreadsheets.',
          'Tier Limit Controls: Respects watchlist quotas based on your subscription tier.',
        ],
      },
      {
        id: 'surface-compare',
        title: 'Multi-Asset Comparison Engine (/compare)',
        content: [
          'Side-by-side structural comparison of up to 6 instruments or macro series.',
          'Enables instant cross-sectional multiple comparisons, valuation benchmarks, margin divergence, and balance sheet strength evaluation.',
        ],
      },
      {
        id: 'surface-monitoring',
        title: 'Monitoring & Alerting System (MON-001)',
        badge: 'Liveness Guaranteed',
        content: [
          'Institutional monitoring treated as a first-class product surface powered by an autonomous standing worker daemon.',
          'Rules evaluate on deterministic cadences with two independent safety mechanisms: coverage tracking (verifying each specific rule runs) and the dead-man watcher (verifying the evaluator process is alive).',
        ],
        keyPoints: [
          'Standing Worker Daemon: Continuously sweeps all ARMED rules across all tenant accounts under transaction-scoped PostgreSQL RLS.',
          'Deadman Supervisor: Independent watchdog verifies heartbeat records in monitoring.evaluator_heartbeat to detect process crashes.',
          'Resend Transactional Email: Automatically sends branded breach alerts to user emails without requiring manual intervention.',
        ],
      },
      {
        id: 'surface-settings',
        title: 'Settings, Team Members & Commercial Billing',
        content: [
          'Comprehensive workspace settings covering profile management, multi-seat team management, subscription tiers, and payment receipts.',
        ],
        keyPoints: [
          'Team Management (Teams Tier): Invite colleagues by email with roles (Admin, Analyst, Viewer), manage allocated seat quotas, and revoke invitations.',
          'Public Colleague Onboarding (/join): 7-day tokenized invite links allow colleagues to accept invites and bind to the tenant account automatically.',
          'Commercial Billing & Stripe Autopay: Self-serve plan upgrades, cancel-at-period-end autopay termination, and invoice history table with PDF receipts.',
          'Zero-IDOR Security: All settings and team modification endpoints enforce strict PostgreSQL RLS and caller tenant isolation.',
        ],
      },
    ],
  },
  {
    id: 'team-and-collaboration',
    title: '4. Team Management, Seats & Colleague Onboarding',
    slug: 'team-management',
    category: 'Enterprise & Collaboration',
    readTimeMinutes: 5,
    summary:
      'How multi-seat team organizations, RBAC permissions, and colleague invitation links operate under strict PostgreSQL Row-Level Security.',
    sections: [
      {
        id: 'team-roles-and-seats',
        title: 'Role-Based Access Control (RBAC) & Seat Quotas',
        badge: 'Teams & Enterprise',
        content: [
          'Talvrin supports collaborative team organizations. Account owners can allocate seats and assign distinct roles to team members:',
        ],
        keyPoints: [
          'Admin: Full workspace governance, invitation issuance, seat management, billing configuration, and member removal.',
          'Analyst: Full research capabilities, rule creation, watchlist management, and dossier exports.',
          'Viewer: Read-only access to organization research history, shared watchlists, and live market screens.',
          'Pooled Quota Sharing: Team members draw from the organization’s high-tier quotas (e.g. 125 rules, 400 research runs/mo).',
        ],
      },
      {
        id: 'inviting-colleagues',
        title: 'Issuing Invitations & 7-Day Token Lifecycles',
        content: [
          'To invite a colleague, navigate to Settings > Team & Organization. Enter their business email and select their initial role.',
          'An official branded invitation email is dispatched via Resend using the TAL-EML-EN-ORG_INVITE template with an embedded secure link.',
        ],
        keyPoints: [
          '7-Day Token Expiration: Invitation tokens are cryptographically generated and expire automatically after 7 days.',
          'Pre-Registration Validation: Tokens are validated server-side, preventing expired or revoked tokens from being redeemed.',
          'Instant Seat Meter Updates: The seat usage meter updates dynamically to prevent over-allocation beyond purchased seat limits.',
        ],
      },
      {
        id: 'colleague-join-flow',
        title: 'Public Colleague Onboarding (/join)',
        content: [
          'When a colleague clicks the invitation link, they are directed to the unauthenticated onboarding page at /join?token=...',
        ],
        keyPoints: [
          'Automatic Tenant Binding: Registers credentials with Supabase Auth and binds the user directly to the inviter’s Account as a Principal.',
          'Zero Account Bleed: RLS guarantees the newly joined user has access strictly to their team workspace without cross-tenant bleed.',
          'Seamless Sign-In: The onboarding engine automatically logs the user into the terminal upon completion.',
        ],
      },
    ],
  },
  {
    id: 'query-cookbook',
    title: '5. Query Cookbook: What You Can Ask',
    slug: 'query-cookbook',
    category: 'Cookbook',
    readTimeMinutes: 6,
    summary:
      'A reference library of high-impact research prompts across equities, IPOs, sovereign debt, and macroeconomics with 1-click testing in the workspace.',
    sections: [
      {
        id: 'cookbook-equities-ipo',
        title: 'Equities, IPOs & Corporate Valuation',
        badge: 'Corporate Finance',
        content: [
          'Extract audited financials, post-listing IPO valuations, and capital allocation metrics directly from SEC EDGAR and official exchange registries:',
        ],
        exampleQueries: [
          {
            title: 'Jio Platforms (JPL) Post-Listing Valuation',
            query:
              'Provide fundamental valuation multiples, subscriber growth metrics, and market capitalization for Jio Platforms Limited (NSE: JPL).',
            model: 'talvrin-pro',
            description: 'Analyzes post-listing trading multiples and operating revenue.',
            outputType: 'PROSE + FACTS_TABLE + DOSSIER_EXPORT',
          },
          {
            title: 'Hyundai Motor India IPO Multiple Analysis',
            query:
              'Compare Hyundai Motor India (NSE: HYUNDAI) trailing P/E and operating margin against Maruti Suzuki and Tata Motors.',
            model: 'talvrin-pro',
            description: 'Generates a cross-sectional multiple comparison with authoritative filings.',
            outputType: 'FACTS_TABLE + COMPARISON',
          },
          {
            title: 'Apple Inc. Capital Return & Free Cash Flow',
            query:
              'What was Apple’s total share buyback expenditure and Free Cash Flow in their latest Form 10-K filing?',
            model: 'talvrin-go',
            description: 'Extracts exact figures from SEC EDGAR with source citations.',
            outputType: 'FACTS_TABLE + CITATIONS',
          },
        ],
      },
      {
        id: 'cookbook-fixed-income',
        title: 'Fixed Income & Sovereign Debt',
        content: [
          'Extract precise bond terms, calculate pricing metrics, and analyze yield curve dynamics with verified UK DMO and BoE data:',
        ],
        exampleQueries: [
          {
            title: 'Gilt Spread Differential (10Y vs 2Y)',
            query:
              'Compare UK 10Y gilt yield vs 2Y gilt yield spread over the last 6 months with BoE benchmark dates',
            model: 'talvrin-pro',
            description:
              'Retrieves accepted sovereign yield curves and computes historical spread differentials.',
            outputType: 'PROSE + FACTS_TABLE + CALCULATION',
          },
          {
            title: 'Modified Duration & Convexity Breakdown',
            query:
              'Explain the modified duration and convexity formula for UKT 4.25% 2034 with actual coupon and yield inputs',
            model: 'talvrin-pro',
            description:
              'Executes approved golden-corpus bond pricing calculations with full variable audit.',
            outputType: 'CALCULATION_RESULT',
          },
          {
            title: 'Gilt Redemption & Coupon Terms',
            query:
              'What are the exact maturity date, coupon payment dates, and ISIN for UK Treasury 0.25% 2025?',
            model: 'talvrin-go',
            description: 'Fetches verified DMO instrument reference terms and alias records.',
            outputType: 'FACTS_TABLE',
          },
        ],
      },
      {
        id: 'cookbook-macro-fx',
        title: 'Macroeconomics, Policy Rates & FX',
        content: [
          'Examine central bank decisions, international macroeconomic indicators, and currency reference rates:',
        ],
        exampleQueries: [
          {
            title: 'BoE Monetary Policy Committee Vote Split',
            query:
              'What was the Bank of England Monetary Policy Committee decision on 2024-08-01 and the voting split?',
            model: 'talvrin-go',
            description: 'Fetches verified central bank minutes and accepted policy rate facts.',
            outputType: 'SOURCE_SUMMARY',
          },
          {
            title: 'ECB Daily FX Reference Series',
            query:
              'Show daily GBP/EUR and GBP/USD fixing rates for the past 30 days from ECB reference data',
            model: 'talvrin-go',
            description: 'Queries Frankfurter / ECB daily market observations.',
            outputType: 'FACTS_TABLE',
          },
          {
            title: 'Global Macro Comparison via DBnomics',
            query:
              'Compare UK CPI inflation rate against Eurozone HICP annual rate for the latest 4 quarters',
            model: 'talvrin-pro',
            description:
              'Retrieves multi-provider macro time series with clear agency attribution.',
            outputType: 'FACTS_TABLE + CHART',
          },
        ],
      },
      {
        id: 'cookbook-refused',
        title: 'Refused Queries & How to Reformulate',
        badge: 'Compliance Boundary',
        content: [
          'Talvrin refuses queries seeking investment advice or speculative price targets. Reframe your questions to focus on verified facts and historical precedents:',
        ],
        keyPoints: [
          '❌ Refused: "Is now a good time to buy UK Gilts?"',
          '✅ Reformulated: "What is the historical spread between 10Y UK Gilts and 10Y US Treasuries over the last 12 months?"',
          '❌ Refused: "Predict the closing price of Barclays shares next month."',
          '✅ Reformulated: "What was Barclays\' Common Equity Tier 1 (CET1) ratio reported in their most recent quarterly disclosure?"',
        ],
      },
    ],
  },
  {
    id: 'market-data-freshness',
    title: '6. Ingestion Feeds & Freshness Auditing',
    slug: 'feeds-freshness',
    category: 'Markets & Calculations',
    readTimeMinutes: 5,
    summary: 'The structural lifecycle of market feeds, connector protocols, and freshness states.',
    sections: [
      {
        id: 'connector-protocol',
        title: 'Connector Architecture (DATA-002)',
        content: [
          'All connectors follow an identical, strictly validated protocol: discover → acquire → verify_transport → identify_schema → parse → checkpoint → health.',
          'Connectors are forbidden from performing identity resolution or publishing accepted facts directly. They normalize raw data into SourceObservations, which are then processed by a metric-specific reconciliation policy.',
        ],
        keyPoints: [
          'UK DMO: Gilt operational notices, tap auctions, and redemption values.',
          'Bank of England: Official bank rates and continuous yield curves (nominal & real).',
          'Frankfurter (ECB): European Central Bank daily foreign exchange fixings.',
          'DBnomics: Global macro datasets (IMF, World Bank, OECD, ONS).',
          'Twelve Data & Exchange Feeds: Global equities, Indian IPOs, and intraday price feeds.',
        ],
      },
      {
        id: 'freshness-indicators',
        title: 'Freshness States & Meaning',
        badge: 'Audit Transparency',
        content: [
          'Every metric possesses a registered FreshnessProfile. An observation is assigned one of four statuses upon evaluation:',
        ],
        keyPoints: [
          'Current (Green): Received and verified within its expected update window.',
          'Delayed (Amber): Older than standard cadence, but within safe tolerance limits.',
          'Stale (Red): Missed expected update cycles; flagged to warn against operational reliance.',
          'Source / Pinned (Blue): Static authoritative reference material (e.g., regulatory methodology or bond prospectus) where age does not represent decay.',
        ],
      },
    ],
  },
  {
    id: 'calculation-specs-gate',
    title: '7. Deterministic Math & Golden Corpus',
    slug: 'deterministic-math',
    category: 'Governance & Integrity',
    readTimeMinutes: 5,
    summary:
      'How calculation specifications (FIN-001) are approved via dual independent implementation and golden test fixtures.',
    sections: [
      {
        id: 'golden-corpus-gate',
        title: 'The Golden Corpus Gate',
        badge: 'Dual-Implementation',
        content: [
          'In Talvrin, financial mathematics cannot be written ad-hoc. All formulas (dirty price, clean price, yield-to-maturity, Macauley/modified duration, convexity, and spreads) require an approved calculation_specification.',
          'Before any specification can move from DRAFT to APPROVED, it must pass the golden corpus gate: two separate, independent code implementations must compute identical values across a rigorous fixture of institutional market instruments.',
        ],
        keyPoints: [
          'Dual Independent Implementation: Guaranteed absence of single-developer bias or subtle numerical drift.',
          'Golden Test Fixtures: Real-world benchmark scenarios vetted against institutional terminal baselines.',
          'Asynchronous Compute Queue: Heavy calculation workloads operate through background queues with FOR UPDATE SKIP LOCKED guarantees, avoiding request timeouts.',
        ],
      },
      {
        id: 'supported-formulas',
        title: 'Standard Calculation Specifications',
        content: [
          'Approved calculation engines active in the platform include:',
        ],
        keyPoints: [
          'Bond Dirty & Clean Pricing: Accrued interest calculations using actual/actual ICMA day-count conventions.',
          'Yield to Maturity (YTM): Newton-Raphson polynomial root-finding for semi-annual and annual sovereign coupons.',
          'Modified Duration & Macauley Duration: First-derivative price sensitivity with respect to yield changes.',
          'Bond Convexity: Second-derivative curvature modeling for non-linear interest rate shocks.',
          'Benchmark Spreads: Spot and interpolated spread differentials over risk-free benchmark curves.',
        ],
      },
    ],
  },
]
