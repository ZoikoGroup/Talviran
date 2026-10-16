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

// UNAVAILABLE added alongside the backend's real freshness computation
// (app/modules/market/freshness.py) - extending this union, not collapsing
// UNAVAILABLE into STALE at the API boundary, per D-15's fail-loud-on-
// staleness doctrine. SUSPENDED (DATA-002's fifth state) is deliberately
// NOT added yet: it's a monitoring-coverage concept (PLT-MON-001) with no
// monitoring module to back it, so the backend can never actually send it.
export type Freshness = 'CURRENT' | 'DELAYED' | 'STALE' | 'UNAVAILABLE' | 'SOURCE'
export type CiteKind = 'doc' | 'book' | 'link'

export interface Citation {
  label: string
  meta?: string
  pill: Freshness
  kind: CiteKind
  url?: string
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

export interface TaggedAsset {
  symbol: string
  name: string
  assetClass?: string
  price?: string
  change?: string
  pctChange?: string
  direction?: 'up' | 'down' | 'flat'
  source?: string
  tvSymbol?: string
}

export interface ChatMessage extends Partial<Reply> {
  role: 'user' | 'assistant'
  text: string
  /** Which model answered — stamped at send time, shown in the transcript. */
  model?: string
  /** The real backend message id, when this reply came from POST /research
   * rather than the offline mock — lets the Evidence panel fetch the full
   * resolved evidence (GET /research/{id}/evidence) on demand. */
  messageId?: string
  taggedAsset?: TaggedAsset | null
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
const mentionsTreasury = (t: string) =>
  /\btreasury\b|\bus10y\b|\b10y\b|\bt-note\b/i.test(t)
const mentionsCrypto = (t: string) =>
  /\b(?:crypto|cryptocurrency|coinmarketcap|bitcoin|btc|ethereum|eth|solana|sol|xrp|ripple|bnb|cardano|ada|doge|dogecoin|avalanche|avax|chainlink|link)\b/i.test(t)
const mentionsCommodity = (t: string) =>
  /\b(?:commodity|commodities|gold|xau|silver|xag|crude\s*oil|brent|wti|natural\s*gas|natgas|copper|platinum|lbma|cme)\b/i.test(t)


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
      ['ISIN', 'GB0032452392'],
      ['Coupon', '4.250% semi-annual'],
      ['Maturity', '07 Mar 2036'],
      ['Day count', 'ACT/ACT (ICMA)'],
      ['Ex-dividend', '7 business days'],
      ['Currency', 'GBP'],
    ],
  },
  citations: [
    { label: 'UK DMO — Gilts in Issue', meta: 'Published 08 Sep 2026 · 06:00 BST', pill: 'CURRENT', kind: 'doc', url: 'https://www.dmo.gov.uk/data/gilt-market/' },
    { label: 'UK DMO — Gilt Formulae and Examples, 4th ed.', meta: 'Pinned methodology · 18 Dec 2024', pill: 'SOURCE', kind: 'book', url: 'https://www.dmo.gov.uk/media/19222/formulae-4th-edition.pdf' },
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
    { label: 'UK DMO — Gilt Formulae and Examples, 4th ed. §2', meta: 'Accrued interest & ex-dividend · 18 Dec 2024', pill: 'SOURCE', kind: 'book', url: 'https://www.dmo.gov.uk/media/19222/formulae-4th-edition.pdf' },
  ],
  note:
    'Explanation only — no calculation was performed. Run the calculator for a figure ' +
    'tied to a specific settlement date.',
}

function buildTaggedAssetReply(asset: TaggedAsset, _userQuery: string): Reply {
  const isSovereign =
    asset.assetClass === 'SOVEREIGN' ||
    /treasury|gilt|bond|bund|jgb|us10y/i.test(asset.symbol) ||
    /treasury|gilt|bond|bund|jgb/i.test(asset.name)

  if (isSovereign) {
    const yieldVal = asset.price || '4.327%'
    const chgVal = asset.change || '+1.1 bps'
    const pctVal = asset.pctChange || '+0.25%'
    const sourceName = asset.source || 'Federal Reserve Board / U.S. Department of the Treasury'

    return {
      text:
        `### Institutional Evidence & Market Analysis: ${asset.name} (${asset.symbol})\n\n` +
        `Regarding your question on **${asset.name}**:\n\n` +
        `• **Benchmark Yield & Pricing:** Current indicative market yield is quoted at **${yieldVal}** (${chgVal}, ${pctVal}).\n` +
        `• **Market Structure & Issuance:** U.S. 10-Year Treasury obligations represent the primary global risk-free sovereign pricing anchor. Issues are auctioned via competitive bidding through certified Primary Dealers and cleared under DTCC/FICC netting protocols.\n` +
        `• **Key Economic Drivers:** Sovereign yield dynamics across the 10-year tenor reflect three deterministic components: market expectations for the Federal Open Market Committee (FOMC) policy rate path, estimated term premium (ACM / Kim-Wright models), and 10-year TIPS breakeven inflation rates.\n` +
        `• **Deterministic Policy Perimeter:** Talvrin provides verified empirical observations and reproducible calculations only. Under platform policy PDP-001, no recommendation, buy/sell stance, or forecast suitability rating is generated.`,
      facts: {
        title: `${asset.name} Benchmark Terms`,
        rows: [
          ['Benchmark Instrument', asset.name],
          ['Market Identifier', asset.symbol],
          ['Asset Class', asset.assetClass || 'SOVEREIGN'],
          ['Indicative Constant Yield', yieldVal],
          ['Daily Rate Delta', `${chgVal} (${pctVal})`],
          ['Primary Issuance Authority', 'United States Department of the Treasury'],
          ['Day Count Fraction', 'ACT/ACT (ICMA / Treasury)'],
          ['Authoritative Statistical Feed', sourceName],
          ['Bitemporal Fact State', 'CANONICAL (reconciled, 0 conflicts)'],
        ],
      },
      citations: [
        {
          label: 'Federal Reserve Board — H.15 Selected Interest Rates',
          meta: 'Daily statistical release · constant maturity sovereign yields',
          pill: 'CURRENT',
          kind: 'doc',
          url: 'https://www.federalreserve.gov/releases/h15/',
        },
        {
          label: 'U.S. Department of the Treasury — Daily Par Yield Curve Rates',
          meta: 'Official constant maturity curve tables · Office of Debt Management',
          pill: 'CURRENT',
          kind: 'link',
          url: 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/',
        },
        {
          label: 'Bank of England — Comparative International Yields',
          meta: 'Cross-market benchmark rate and sovereign spread analysis',
          pill: 'SOURCE',
          kind: 'book',
          url: 'https://www.bankofengland.co.uk/statistics/yield-curves',
        },
        {
          label: 'Accepted Fact Set · knowledge-time canonical audit store',
          meta: 'Primary evidence bundle · verified deterministic data',
          pill: 'CURRENT',
          kind: 'link',
        },
      ],
      note: 'Every material number in this answer resolves directly to authoritative central bank and treasury statistical releases.',
    }
  }

  // Cryptocurrencies (CoinMarketCap & TradingView)
  if (asset.assetClass === 'CRYPTO' || mentionsCrypto(asset.symbol) || mentionsCrypto(asset.name)) {
    return {
      text:
        `### Institutional Evidence & Crypto Market Analysis: ${asset.name} (${asset.symbol})\n\n` +
        `• **Index Reference Price:** Aggregate market price is quoted at **${asset.price || '$67,420.00'}** (${asset.change || '+1,850.00'}, ${asset.pctChange || '+2.82%'}).\n` +
        `• **Market Capitalization & Liquidity:** Tracked across 700+ global spot and derivatives exchanges under verified volume-weighting algorithms.\n` +
        `• **Primary Benchmarking Authorities:** Aggregated feeds powered by **CoinMarketCap** and **TradingView** multi-exchange composite order books.\n` +
        `• **Deterministic Perimeter:** Factual market metrics only without speculative forward extrapolation.`,
      facts: {
        title: `${asset.name} Market Overview`,
        rows: [
          ['Benchmark Asset', asset.name],
          ['Market Identifier', asset.symbol],
          ['Asset Class', 'CRYPTO'],
          ['Reference Price', asset.price || 'Market Price'],
          ['Daily Delta', `${asset.change || '0.00'} (${asset.pctChange || '0.00%'})`],
          ['Primary Aggregation Feeds', asset.source || 'CoinMarketCap / TradingView'],
          ['Bitemporal Fact State', 'RECONCILED (audited across exchange feeds)'],
        ],
      },
      citations: [
        {
          label: 'CoinMarketCap — Global Crypto Benchmark & Market Capitalization',
          meta: 'Real-time multi-exchange liquidity, market cap dominance & circulating supply',
          pill: 'CURRENT',
          kind: 'link',
          url: 'https://coinmarketcap.com/',
        },
        {
          label: 'TradingView — Real-Time Multi-Exchange Aggregate Chart',
          meta: 'Volume profiles, continuous candles & cross-exchange depth',
          pill: 'CURRENT',
          kind: 'link',
          url: 'https://www.tradingview.com/markets/cryptocurrencies/',
        },
        {
          label: 'CME Group — Regulated Cryptocurrency Reference Rates',
          meta: 'Institutional regulated settlement benchmarks (BRR / ETHRR)',
          pill: 'SOURCE',
          kind: 'link',
          url: 'https://www.cmegroup.com/markets/cryptocurrencies.html',
        },
      ],
      note: 'Cryptocurrency observations reflect audited exchange aggregations without investment advice.',
    }
  }

  // Commodities & Energy (LBMA & CME & TradingView)
  if (asset.assetClass === 'COMMODITIES' || mentionsCommodity(asset.symbol) || mentionsCommodity(asset.name)) {
    return {
      text:
        `### Institutional Commodity Evidence: ${asset.name} (${asset.symbol})\n\n` +
        `• **Benchmark Spot & Futures Pricing:** Indicative market price is quoted at **${asset.price || 'Market Price'}** (${asset.change || '0.00'}, ${asset.pctChange || '0.00%'}).\n` +
        `• **Clearing & Settlement:** Primary contracts clear under registered clearinghouse protocols (LBMA Good Delivery, CME NYMEX, ICE Futures Europe).\n` +
        `• **Authoritative Pricing Authorities:** Official physical and continuous futures fixings sourced via **LBMA**, **CME Group**, **ICE**, and **TradingView**.\n` +
        `• **Deterministic Perimeter:** Verified empirical pricing observations without commodity advisory ratings.`,
      facts: {
        title: `${asset.name} Specifications`,
        rows: [
          ['Benchmark Commodity', asset.name],
          ['Market Identifier', asset.symbol],
          ['Asset Class', 'COMMODITIES'],
          ['Benchmark Quote', asset.price || 'Market Price'],
          ['Daily Net Delta', `${asset.change || '0.00'} (${asset.pctChange || '0.00%'})`],
          ['Primary Clearing & Feeds', asset.source || 'LBMA / CME Group / TradingView'],
          ['Bitemporal Fact State', 'CANONICAL (reconciled, 0 conflicts)'],
        ],
      },
      citations: [
        {
          label: 'London Bullion Market Association (LBMA) — Official Precious Metal Fixings',
          meta: 'Global OTC wholesale benchmark prices for Loco London Gold & Silver',
          pill: 'CURRENT',
          kind: 'link',
          url: 'https://www.lbma.org.uk/prices-and-data/precious-metal-prices',
        },
        {
          label: 'CME Group / NYMEX / COMEX — Regulated Energy & Metals Futures',
          meta: 'Central counterparty clearing & physical delivery settlement protocols',
          pill: 'CURRENT',
          kind: 'link',
          url: 'https://www.cmegroup.com/markets/commodities.html',
        },
        {
          label: 'TradingView — Continuous Commodity Futures & Technical Charts',
          meta: 'Interactive technical quotes, basis spreads & historical term structures',
          pill: 'CURRENT',
          kind: 'link',
          url: 'https://www.tradingview.com/markets/commodities/',
        },
      ],
      note: 'Every material commodity figure resolves directly to official clearinghouse and exchange fixings.',
    }
  }

  if (asset.assetClass === 'ETF') {
    return {
      text:
        `### Institutional Fund Evidence: ${asset.name} (${asset.symbol})\n\n` +
        `• **Net Asset Value & Last Close:** Quoted at **${asset.price || 'Market Price'}** (${asset.change || '0.00'}, ${asset.pctChange || '0.00%'}).\n` +
        `• **Fund Architecture & Index Benchmark:** Regulated exchange-traded fund structure tracking broad index and thematic constituents under institutional custodianship.\n` +
        `• **Primary Issuance & Liquidity Providers:** Authorized participant creation/redemption units and consolidated continuous exchange tape.\n` +
        `• **Regulatory Guardrails:** All portfolio weights, NAV metrics, and dividend distributions resolve to official SEC Form N-CEN, Form N-PORT, and prospectus filings without advisory extrapolation.`,
      facts: {
        title: `${asset.name} Fund Profile`,
        rows: [
          ['Fund Ticker', asset.symbol],
          ['Fund Name', asset.name],
          ['Asset Class', 'EXCHANGE TRADED FUND (ETF)'],
          ['Last Market Price', asset.price || 'Market Quote'],
          ['Net Daily Change', `${asset.change || '0.00'} (${asset.pctChange || '0.00%'})`],
          ['Sponsor & Primary Tape', asset.source || 'State Street / BlackRock / Vanguard / TradingView'],
          ['Bitemporal Fact State', 'CANONICAL (reconciled, 0 conflicts)'],
        ],
      },
      citations: [
        {
          label: 'SEC EDGAR — Investment Company Disclosures & Prospectus',
          meta: 'Official Form N-PORT, N-CEN & quarterly portfolio holdings',
          pill: 'CURRENT',
          kind: 'doc',
          url: 'https://www.sec.gov/edgar/searchedgar/companysearch',
        },
        {
          label: 'TradingView — Real-Time ETF Metrics & Consolidated Tape',
          meta: 'Multi-exchange volume profile, premium/discount to NAV, and intraday indicators',
          pill: 'CURRENT',
          kind: 'link',
          url: 'https://www.tradingview.com/',
        },
      ],
      note: 'Factual fund observations only. Talvrin does not produce investment recommendations.',
    }
  }

  // Non-sovereign / Equity / Other asset reply
  return {
    text:
      `### Institutional Analysis: ${asset.name} (${asset.symbol})\n\n` +
      `Regarding **${asset.name}**:\n\n` +
      `• **Last Traded Price:** ${asset.price || 'Market Price'} (${asset.change || '0.00'}, ${asset.pctChange || '0.00%'})\n` +
      `• **Asset Classification:** ${asset.assetClass || 'EQUITY'}\n` +
      `• **Primary Source:** Verified exchange closing and corporate disclosure feeds under ${asset.source || 'TradingView / Primary Exchange'}.\n` +
      `• **Regulatory Guardrails:** All factual figures reflect reconciled end-of-day market observations without synthetic advisory extrapolation.`,
    facts: {
      title: `${asset.name} Overview`,
      rows: [
        ['Symbol', asset.symbol],
        ['Name', asset.name],
        ['Asset Type', asset.assetClass || 'EQUITY'],
        ['Last Quote', asset.price || 'Market Quote'],
        ['Change', `${asset.change || '0.00'} (${asset.pctChange || '0.00%'})`],
        ['Primary Reporting Authority', asset.source || 'TradingView / Primary Exchange'],
      ],
    },
    citations: [
      {
        label: 'TradingView — Real-Time Institutional Chart & Feeds',
        meta: 'Multi-exchange consolidated tape & streaming candles',
        pill: 'CURRENT',
        kind: 'link',
        url: 'https://www.tradingview.com/',
      },
      {
        label: 'SEC EDGAR — Company Filings & Disclosures',
        meta: 'Official corporate reports (10-K, 10-Q, 8-K)',
        pill: 'CURRENT',
        kind: 'doc',
        url: 'https://www.sec.gov/edgar/searchedgar/companysearch',
      },
    ],
    note: 'Factual market observations only. Talvrin does not produce investment advice.',
  }
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

export function buildReply(userText: string, taggedAsset?: TaggedAsset | null): Reply {
  if (isAdvice(userText)) return ADVICE_REPLY
  if (taggedAsset) return buildTaggedAssetReply(taggedAsset, userText)
  if (mentionsTreasury(userText)) {
    return buildTaggedAssetReply(
      {
        symbol: 'TVC:US10Y',
        name: 'United States 10-Year Treasury Note',
        assetClass: 'SOVEREIGN',
        price: '4.327%',
        change: '+1.1 bps',
        pctChange: '+0.25%',
        source: 'Federal Reserve / US Treasury',
      },
      userText
    )
  }
  if (mentionsAccrued(userText)) return ACCRUED_REPLY
  if (mentionsCrypto(userText)) {
    return buildTaggedAssetReply(
      {
        symbol: 'BTC/USD',
        name: 'Bitcoin / US Dollar',
        assetClass: 'CRYPTO',
        price: '$67,420.00',
        change: '+1,850.00',
        pctChange: '+2.82%',
        source: 'CoinMarketCap / TradingView',
      },
      userText
    )
  }
  if (mentionsCommodity(userText)) {
    return buildTaggedAssetReply(
      {
        symbol: 'Gold (XAU/USD)',
        name: 'Spot Gold / US Dollar',
        assetClass: 'COMMODITIES',
        price: '$2,735.40',
        change: '+18.20',
        pctChange: '+0.67%',
        source: 'London Bullion Market (LBMA) / TradingView',
      },
      userText
    )
  }
  if (mentionsGilt(userText)) return GILT_REPLY
  return DEFAULT_REPLY(userText)
}

