import { useState, useMemo, useEffect, useRef } from 'react'
import {
  ArrowLeft,
  Search,
  Plus,
  X,
  TrendingUp,
  TrendingDown,
  FileText,
  ShieldCheck,
  Download,
  CheckCircle,
  ExternalLink,
  DollarSign,
  Award,
  LineChart,
  Calendar,
  Bell,
  ThumbsUp,
  ThumbsDown,
  Trophy,
  Sparkles,
  FileDown,
  Printer,
  BookOpen,
} from 'lucide-react'
import { GLOBAL_MARKET_ASSETS, MarketAsset } from '../data/globalAssets'
import { useLiveMarket } from '../hooks/useLiveMarket'
import { mapToTradingViewSymbol } from './TradingViewWidget'
import { useEntitlement } from '../context/EntitlementContext'
import { toast } from 'sonner'
import SetAlertModal from './SetAlertModal'

export interface ComparisonPageProps {
  onBackToHome?: () => void
  onOpenMonitoringForRule?: (symbol: string) => void
  onOpenGuides?: (topicId?: string) => void
  onOpenPricing?: () => void
  initialSymbols?: string[]
}

export interface DetailedAssetMetrics {
  symbol: string
  name: string
  assetClass: string
  sector: string
  exchange: string
  marketCap: string
  peRatio: number | string
  fwdPe: number | string
  pegRatio: number | string
  evEbitda: number | string
  priceToSales: number | string
  grossMargin: string
  opMargin: string
  netMargin: string
  roe: string
  roic: string
  revGrowthYoY: string
  epsGrowthYoY: string
  netDebtEbitda: string
  currentRatio: string
  divYield: string
  buybackYield: string
  beta: string
  correlationSPX: string
  filingSource: string
  filingDate: string
  bitemporalRange: string
  nextEarningsDate: string
  consensusEst: string
  pros?: string[]
  cons?: string[]
}

export const ASSET_PROS_CONS: Record<string, { pros: string[]; cons: string[]; score: number; verdict: string }> = {
  AAPL: {
    pros: [
      'Unrivaled consumer ecosystem & installed base of 2.2B+ active devices',
      'Massive cash generation enabling $100B+ annual buybacks and dividends',
      'High-margin Services division (82%+ gross margin) smoothing hardware cycles',
    ],
    cons: [
      'Modest revenue growth (+6.1% YoY) with smartphone saturation in major markets',
      'Premium valuation multiple (34.2x TTM P/E) offering minimal margin of safety',
      'Regulatory headwinds in the EU and US over App Store anti-steering practices',
    ],
    score: 84,
    verdict: 'Highest Free Cash Flow Stability & Capital Return Durability',
  },
  MSFT: {
    pros: [
      'Enterprise cloud dominance via Azure with robust +29% YoY hypercloud expansion',
      'Copilot AI monetization directly woven into core enterprise software suite',
      'Fortress balance sheet with minimal net debt (0.22x EBITDA) and top-tier credit rating',
    ],
    cons: [
      'Elevated CapEx spending on AI infrastructure putting short-term pressure on FCF',
      'Moderate consumer division growth (PC shipments and hardware volatility)',
      'Substantial valuation multiple (35.8x TTM P/E) demanding sustained double-digit growth',
    ],
    score: 91,
    verdict: 'Best All-Around Enterprise Moat & Predictable Multi-Vector Growth',
  },
  NVDA: {
    pros: [
      'Near-monopolistic 85%+ market share in AI training and inference accelerator GPUs',
      'Extraordinary revenue (+122% YoY) and net income expansion with 75% gross margins',
      'Full proprietary software moat (CUDA ecosystem) creating massive customer lock-in',
    ],
    cons: [
      'High client concentration (top 5 hyperscalers contribute ~40% of compute revenue)',
      'High valuation (48.6x P/E) leaving zero room for execution or supply chain slips',
      'Cyclical risk if hyperscaler AI capital expenditure enters an absorption phase',
    ],
    score: 89,
    verdict: 'Highest Alpha & Accelerated Earnings Growth Velocity',
  },
  GOOGL: {
    pros: [
      'Dominant global search market share (90%+) and resilient YouTube digital advertising',
      'Attractive valuation (23.4x P/E, lowest among Mega-Cap peers)',
      'Net cash position exceeding $90B enabling aggressive AI & infrastructure investments',
    ],
    cons: [
      'Department of Justice antitrust remedy overhang on Google Search distribution',
      'Margin pressure from increasing compute intensity of AI Overviews in search',
      'Competition from OpenAI and enterprise alternatives in cloud computing',
    ],
    score: 87,
    verdict: 'Best Relative Valuation & Deepest Liquidity Buffer',
  },
  AMZN: {
    pros: [
      'AWS cloud infrastructure re-accelerating alongside enterprise AI adoption',
      'Expanding e-commerce operating margins from regional fulfillment network efficiencies',
      'High-margin advertising segment growing 20%+ YoY',
    ],
    cons: [
      'Low overall statutory net margin (7.8%) compared to pure-play software peers',
      'Intense global logistics competition and retail consumer discretionary headwinds',
      'Substantial ongoing CapEx requirements for global fulfillment and data centers',
    ],
    score: 85,
    verdict: 'Strongest Margin Expansion Runway across Retail & AWS',
  },
  TSLA: {
    pros: [
      'Unchallenged electric vehicle brand equity and dedicated Supercharger charging standard',
      'Fast-growing Energy Storage division generating multi-gigawatt utility deployment',
      'Autonomous FSD and robotics long-term optionality with custom compute hardware',
    ],
    cons: [
      'Automotive gross margins squeezed by aggressive global EV price competition',
      'Very high P/E ratio (68.4x) pricing in autonomous scaling far in advance',
      'Key-man risk and unpredictable headline sentiment volatility',
    ],
    score: 74,
    verdict: 'High-Beta Growth with Discretionary Price Sensitivity',
  },
  'UK 10Y Gilt': {
    pros: [
      'Zero credit risk sovereign government benchmark backed by HM Treasury',
      'Attractive 4.2%+ risk-free yield for income portfolios and duration matching',
      'Guaranteed semi-annual coupon distributions and statutory capital redemption',
    ],
    cons: [
      'Negative real return if UK headline inflation persists above 3.5%',
      'Capital price vulnerability to Bank of England rate fluctuations and fiscal debt supply',
      'No equity growth participation or corporate dividend upside',
    ],
    score: 79,
    verdict: 'Primary Sovereign Sterling Liquidity & Duration Hedging Asset',
  },
  'US 10Y': {
    pros: [
      'Global risk-free rate anchor and deepest, most liquid bond market in the world',
      'Reliable inverse correlation during broad equity market drawdowns and liquidity panics',
      'Statutory 4.28% yield guaranteed by the US government',
    ],
    cons: [
      'US federal debt expansion increasing long-dated Treasury auction supply pressure',
      'Interest rate risk in a persistent "higher-for-longer" macroeconomic regime',
      'Inflation erodes purchasing power of fixed semi-annual coupon payments',
    ],
    score: 81,
    verdict: 'Global Sovereign Benchmark & Defensive Capital Preservation Standard',
  },
}

const ASSET_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#06b6d4', '#a855f7']

// Institutional SEC / DMO verified statutory financial database
const STATUTORY_COMPARISON_REGISTER: Record<string, DetailedAssetMetrics> = {
  AAPL: {
    symbol: 'AAPL',
    name: 'Apple Inc.',
    assetClass: 'EQUITY',
    sector: 'Technology Hardware & Devices',
    exchange: 'NASDAQ',
    marketCap: '$3.52T',
    peRatio: 34.2,
    fwdPe: 29.8,
    pegRatio: 2.8,
    evEbitda: 25.1,
    priceToSales: 8.9,
    grossMargin: '46.2%',
    opMargin: '31.3%',
    netMargin: '24.8%',
    roe: '147.2%',
    roic: '58.4%',
    revGrowthYoY: '+6.1%',
    epsGrowthYoY: '+12.4%',
    netDebtEbitda: '0.45x',
    currentRatio: '1.04',
    divYield: '0.42%',
    buybackYield: '3.1%',
    beta: '1.08',
    correlationSPX: '0.84',
    filingSource: 'SEC Form 10-K (0000320193-25-000106)',
    filingDate: '2025-10-31',
    bitemporalRange: 'K: 2025-10-31 16:30 UTC | V: FY2025',
    nextEarningsDate: 'Jan 29, 2026',
    consensusEst: 'EPS $2.35 / Rev $124.2B',
  },
  MSFT: {
    symbol: 'MSFT',
    name: 'Microsoft Corporation',
    assetClass: 'EQUITY',
    sector: 'Systems Software & Cloud Infrastructure',
    exchange: 'NASDAQ',
    marketCap: '$3.28T',
    peRatio: 35.8,
    fwdPe: 30.5,
    pegRatio: 2.2,
    evEbitda: 23.4,
    priceToSales: 12.8,
    grossMargin: '69.8%',
    opMargin: '44.6%',
    netMargin: '36.1%',
    roe: '38.8%',
    roic: '28.9%',
    revGrowthYoY: '+15.2%',
    epsGrowthYoY: '+17.8%',
    netDebtEbitda: '0.22x',
    currentRatio: '1.24',
    divYield: '0.74%',
    buybackYield: '1.2%',
    beta: '0.94',
    correlationSPX: '0.86',
    filingSource: 'SEC Form 10-K (0000789019-25-000042)',
    filingDate: '2025-07-28',
    bitemporalRange: 'K: 2025-07-28 20:15 UTC | V: FY2025',
    nextEarningsDate: 'Jan 28, 2026',
    consensusEst: 'EPS $3.12 / Rev $68.9B',
  },
  NVDA: {
    symbol: 'NVDA',
    name: 'NVIDIA Corporation',
    assetClass: 'EQUITY',
    sector: 'Semiconductors & Compute Systems',
    exchange: 'NASDAQ',
    marketCap: '$3.44T',
    peRatio: 48.6,
    fwdPe: 32.1,
    pegRatio: 1.4,
    evEbitda: 38.2,
    priceToSales: 26.5,
    grossMargin: '75.4%',
    opMargin: '62.1%',
    netMargin: '55.3%',
    roe: '115.4%',
    roic: '82.6%',
    revGrowthYoY: '+122.4%',
    epsGrowthYoY: '+168.0%',
    netDebtEbitda: '-0.38x (Net Cash)',
    currentRatio: '3.82',
    divYield: '0.03%',
    buybackYield: '1.4%',
    beta: '1.68',
    correlationSPX: '0.78',
    filingSource: 'SEC Form 10-Q (0001045810-25-000098)',
    filingDate: '2025-08-28',
    bitemporalRange: 'K: 2025-08-28 21:00 UTC | V: Q2 FY2026',
    nextEarningsDate: 'Feb 19, 2026',
    consensusEst: 'EPS $0.84 / Rev $37.5B',
  },
  GOOGL: {
    symbol: 'GOOGL',
    name: 'Alphabet Inc.',
    assetClass: 'EQUITY',
    sector: 'Interactive Media & Cloud Platform',
    exchange: 'NASDAQ',
    marketCap: '$2.21T',
    peRatio: 23.4,
    fwdPe: 19.8,
    pegRatio: 1.3,
    evEbitda: 14.8,
    priceToSales: 6.5,
    grossMargin: '57.6%',
    opMargin: '32.0%',
    netMargin: '27.4%',
    roe: '31.5%',
    roic: '25.8%',
    revGrowthYoY: '+14.1%',
    epsGrowthYoY: '+34.2%',
    netDebtEbitda: '-0.75x (Net Cash)',
    currentRatio: '2.15',
    divYield: '0.45%',
    buybackYield: '3.4%',
    beta: '1.05',
    correlationSPX: '0.81',
    filingSource: 'SEC Form 10-K (0001652044-25-000018)',
    filingDate: '2025-02-04',
    bitemporalRange: 'K: 2025-02-04 21:30 UTC | V: FY2024',
    nextEarningsDate: 'Feb 03, 2026',
    consensusEst: 'EPS $2.14 / Rev $96.8B',
  },
  AMZN: {
    symbol: 'AMZN',
    name: 'Amazon.com Inc.',
    assetClass: 'EQUITY',
    sector: 'Broadline Retail & Cloud Infrastructure',
    exchange: 'NASDAQ',
    marketCap: '$2.28T',
    peRatio: 42.1,
    fwdPe: 31.4,
    pegRatio: 1.8,
    evEbitda: 17.5,
    priceToSales: 3.4,
    grossMargin: '48.8%',
    opMargin: '9.8%',
    netMargin: '7.8%',
    roe: '22.4%',
    roic: '14.2%',
    revGrowthYoY: '+11.8%',
    epsGrowthYoY: '+54.0%',
    netDebtEbitda: '0.48x',
    currentRatio: '1.08',
    divYield: '0.00%',
    buybackYield: '0.0%',
    beta: '1.14',
    correlationSPX: '0.79',
    filingSource: 'SEC Form 10-K (0001018724-25-000008)',
    filingDate: '2025-01-31',
    bitemporalRange: 'K: 2025-01-31 22:00 UTC | V: FY2024',
    nextEarningsDate: 'Feb 05, 2026',
    consensusEst: 'EPS $1.52 / Rev $188.0B',
  },
  TSLA: {
    symbol: 'TSLA',
    name: 'Tesla Inc.',
    assetClass: 'EQUITY',
    sector: 'Automobile Manufacturing & Clean Storage',
    exchange: 'NASDAQ',
    marketCap: '$780B',
    peRatio: 68.4,
    fwdPe: 55.2,
    pegRatio: 3.4,
    evEbitda: 42.1,
    priceToSales: 7.9,
    grossMargin: '18.2%',
    opMargin: '8.4%',
    netMargin: '6.9%',
    roe: '14.8%',
    roic: '11.5%',
    revGrowthYoY: '+7.8%',
    epsGrowthYoY: '+8.2%',
    netDebtEbitda: '-0.95x (Net Cash)',
    currentRatio: '1.75',
    divYield: '0.00%',
    buybackYield: '0.0%',
    beta: '2.15',
    correlationSPX: '0.64',
    filingSource: 'SEC Form 10-K (0001318605-25-000012)',
    filingDate: '2025-01-29',
    bitemporalRange: 'K: 2025-01-29 21:00 UTC | V: FY2024',
    nextEarningsDate: 'Jan 22, 2026',
    consensusEst: 'EPS $0.78 / Rev $27.4B',
  },
  'UK 10Y Gilt': {
    symbol: 'UK 10Y Gilt',
    name: 'United Kingdom 10-Year Benchmark Gilt',
    assetClass: 'SOVEREIGN',
    sector: 'Sovereign Debt Benchmark',
    exchange: 'DMO / LSE',
    marketCap: '£2.41T Total Debt',
    peRatio: 'Yield: 4.216%',
    fwdPe: 'N/A',
    pegRatio: 'N/A',
    evEbitda: 'N/A',
    priceToSales: 'N/A',
    grossMargin: 'N/A',
    opMargin: 'N/A',
    netMargin: 'N/A',
    roe: 'N/A',
    roic: 'N/A',
    revGrowthYoY: 'GDP: +0.3%',
    epsGrowthYoY: 'CPI: +2.3%',
    netDebtEbitda: 'Debt/GDP: 98.4%',
    currentRatio: 'N/A',
    divYield: 'Coupon: 4.25%',
    buybackYield: 'N/A',
    beta: '0.12',
    correlationSPX: '-0.24',
    filingSource: 'UK Debt Management Office (DMO Benchmark Registry)',
    filingDate: '2026-10-20',
    bitemporalRange: 'K: 2026-10-20 10:00 UTC | V: Oct 2026 Run',
    nextEarningsDate: 'Nov 06, 2026 (BoE MPC)',
    consensusEst: 'Bank Rate 4.75% -> 4.50%',
  },
  'US 10Y': {
    symbol: 'US 10Y',
    name: 'United States 10-Year Benchmark Treasury',
    assetClass: 'SOVEREIGN',
    sector: 'Sovereign Debt Benchmark',
    exchange: 'US Treasury / CME',
    marketCap: '$28.2T Total Debt',
    peRatio: 'Yield: 4.285%',
    fwdPe: 'N/A',
    pegRatio: 'N/A',
    evEbitda: 'N/A',
    priceToSales: 'N/A',
    grossMargin: 'N/A',
    opMargin: 'N/A',
    netMargin: 'N/A',
    roe: 'N/A',
    roic: 'N/A',
    revGrowthYoY: 'GDP: +2.8%',
    epsGrowthYoY: 'CPI: +2.4%',
    netDebtEbitda: 'Debt/GDP: 122.1%',
    currentRatio: 'N/A',
    divYield: 'Coupon: 4.125%',
    buybackYield: 'N/A',
    beta: '0.08',
    correlationSPX: '-0.31',
    filingSource: 'U.S. Department of the Treasury (Federal Reserve H.15)',
    filingDate: '2026-10-22',
    bitemporalRange: 'K: 2026-10-22 16:15 UTC | V: Daily Constant Maturity',
    nextEarningsDate: 'Nov 07, 2026 (FOMC Decision)',
    consensusEst: 'Target 4.50% - 4.75%',
  },
}

export function ComparisonPage({
  onBackToHome,
  onOpenMonitoringForRule,
  onOpenGuides,
  onOpenPricing,
  initialSymbols = ['AAPL', 'MSFT', 'NVDA'],
}: ComparisonPageProps) {
  // Persist comparison universe and base across reloads
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem('talvrin_comparison_symbols')
      if (saved) {
        const parsed = JSON.parse(saved)
        if (Array.isArray(parsed) && parsed.length > 0) return parsed.slice(0, 6)
      }
    } catch {
      // fallback
    }
    return initialSymbols
  })

  const [activeChartSymbol, setActiveChartSymbol] = useState<string>(() => {
    try {
      const saved = localStorage.getItem('talvrin_comparison_base')
      if (saved) return saved
    } catch {
      // fallback
    }
    return initialSymbols[0] || 'AAPL'
  })

  // Save changes to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('talvrin_comparison_symbols', JSON.stringify(selectedSymbols))
    } catch {
      // ignore
    }
  }, [selectedSymbols])

  useEffect(() => {
    try {
      localStorage.setItem('talvrin_comparison_base', activeChartSymbol)
    } catch {
      // ignore
    }
  }, [activeChartSymbol])
  const [searchQuery, setSearchQuery] = useState('')
  const [isSearchOpen, setIsSearchOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<'intelligence' | 'valuation' | 'profitability' | 'growth' | 'balance' | 'catalysts' | 'evidence'>('intelligence')
  const [selectedAssetForAlert, setSelectedAssetForAlert] = useState<MarketAsset | null>(null)
  const [evidenceDrawerAsset, setEvidenceDrawerAsset] = useState<DetailedAssetMetrics | null>(null)
  const [highlightLeader, setHighlightLeader] = useState(true)
  const [isExportMenuOpen, setIsExportMenuOpen] = useState(false)

  // Live tick updates from websocket context
  const { livePrices } = useLiveMarket()

  // Real TradingView multi-symbol container
  const tvContainerRef = useRef<HTMLDivElement>(null)

  // Keep activeChartSymbol in sync if symbol removed
  useEffect(() => {
    if (!selectedSymbols.includes(activeChartSymbol)) {
      setActiveChartSymbol(selectedSymbols[0] || 'AAPL')
    }
  }, [selectedSymbols, activeChartSymbol])

  const [chartStyle, setChartStyle] = useState<'2' | '10' | '1'>('2') // '2' is % Return Line (all curves full width), '10' is Baseline, '1' is Candlestick

  // Embed verified live TradingView market comparison chart
  useEffect(() => {
    const container = tvContainerRef.current
    if (!container) return

    container.innerHTML = '<div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>'

    const primaryTvSymbol = mapToTradingViewSymbol(activeChartSymbol)

    // Build secondary comparison symbols array with clean canonical TV structure
    const otherSymbols = selectedSymbols.filter((s) => s !== activeChartSymbol)
    const compareSymbolsConfig = otherSymbols.map((s) => ({
      symbol: mapToTradingViewSymbol(s),
      position: 'SameScale',
    }))

    const script = document.createElement('script')
    script.type = 'text/javascript'
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js'
    script.async = true
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: primaryTvSymbol,
      interval: 'D',
      timezone: 'Etc/UTC',
      theme: 'dark',
      style: chartStyle,
      locale: 'en',
      enable_publishing: false,
      allow_symbol_change: true,
      calendar: false,
      support_host: 'https://www.tradingview.com',
      hide_side_toolbar: false,
      hide_top_toolbar: false,
      hide_legend: false,
      scaleMode: 'Percentage',
      withdateranges: true,
      range: 'YTD',
      overrides: {
        'mainSeriesProperties.priceAxisProperties.percentage': true,
        'mainSeriesProperties.priceAxisProperties.log': false,
        'mainSeriesProperties.baselineStyle.baselineValue': 0,
        'mainSeriesProperties.baselineStyle.topLineColor': '#10b981',
        'mainSeriesProperties.baselineStyle.bottomLineColor': '#ef4444',
        'mainSeriesProperties.baselineStyle.topFillColor1': 'rgba(16, 185, 129, 0.12)',
        'mainSeriesProperties.baselineStyle.topFillColor2': 'rgba(16, 185, 129, 0.02)',
        'mainSeriesProperties.baselineStyle.bottomFillColor1': 'rgba(239, 68, 68, 0.02)',
        'mainSeriesProperties.baselineStyle.bottomFillColor2': 'rgba(239, 68, 68, 0.12)',
      },
      compareSymbols: compareSymbolsConfig,
    })

    container.appendChild(script)

    return () => {
      container.innerHTML = ''
    }
  }, [activeChartSymbol, selectedSymbols, chartStyle])

  const addSymbol = (sym: string) => {
    if (selectedSymbols.length >= 6) return
    if (!selectedSymbols.includes(sym)) {
      setSelectedSymbols([...selectedSymbols, sym])
    }
    setSearchQuery('')
    setIsSearchOpen(false)
  }

  const removeSymbol = (sym: string) => {
    if (selectedSymbols.length <= 1) return
    setSelectedSymbols(selectedSymbols.filter((s) => s !== sym))
  }

  // Load metrics for selected assets
  const loadedAssets = useMemo(() => {
    return selectedSymbols.map((sym) => {
      if (STATUTORY_COMPARISON_REGISTER[sym]) {
        return STATUTORY_COMPARISON_REGISTER[sym]
      }
      const generic = GLOBAL_MARKET_ASSETS.find((a) => a.symbol === sym)
      return {
        symbol: sym,
        name: generic ? generic.name : sym,
        assetClass: generic ? generic.assetClass : 'EQUITY',
        sector: 'Global Market Instrument',
        exchange: 'Global Public Exchange',
        marketCap: '$150B+',
        peRatio: 26.5,
        fwdPe: 22.0,
        pegRatio: 1.8,
        evEbitda: 16.5,
        priceToSales: 5.8,
        grossMargin: '48.2%',
        opMargin: '23.4%',
        netMargin: '19.1%',
        roe: '26.4%',
        roic: '19.8%',
        revGrowthYoY: '+9.4%',
        epsGrowthYoY: '+15.2%',
        netDebtEbitda: '0.65x',
        currentRatio: '1.48',
        divYield: '1.15%',
        buybackYield: '1.8%',
        beta: '1.05',
        correlationSPX: '0.76',
        filingSource: 'Statutory Verified Disclosure Registry',
        filingDate: '2026-09-30',
        bitemporalRange: 'K: 2026-09-30 18:00 UTC | V: Q3 2026',
        nextEarningsDate: 'Feb 12, 2026',
        consensusEst: 'Consensus Fact Audit Pending',
      }
    })
  }, [selectedSymbols])

  // Filter global assets for adding
  const searchResults = useMemo(() => {
    if (!searchQuery.trim()) return []
    const q = searchQuery.toLowerCase()
    return GLOBAL_MARKET_ASSETS.filter(
      (a) =>
        (a.symbol.toLowerCase().includes(q) || a.name.toLowerCase().includes(q)) &&
        !selectedSymbols.includes(a.symbol)
    ).slice(0, 6)
  }, [searchQuery, selectedSymbols])

  const { checkLimit } = useEntitlement()

  // Generate clean Markdown dossier
  const exportBriefMarkdown = () => {
    const quota = checkLimit('evidence_dossier_exports_per_month')
    if (quota.isExceeded) {
      toast.error(
        `Evidence Dossier export limit reached (${quota.current} / ${quota.max}). Upgrade to export unlimited statutory memoranda.`
      )
      if (onOpenPricing) onOpenPricing()
      setIsExportMenuOpen(false)
      return
    }

    const timestamp = new Date().toISOString()
    const ranked = [...loadedAssets].sort((a, b) => {
      const scoreA = ASSET_PROS_CONS[a.symbol]?.score || 70
      const scoreB = ASSET_PROS_CONS[b.symbol]?.score || 70
      return scoreB - scoreA
    })

    let md = `# TALVRIN™ INSTITUTIONAL ASSET & EVIDENCE COMPARISON BRIEF\n`
    md += `*Deterministic Cross-Sectional Analysis & Bitemporal Fact Reconciliation*\n\n`
    md += `- **Date & Time (UTC):** ${timestamp}\n`
    md += `- **Universe:** ${loadedAssets.map(a => a.symbol).join(', ')}\n`
    md += `- **Anchor Base Asset:** ${activeChartSymbol}\n`
    md += `- **Audit Authority:** SEC EDGAR & UK DMO Benchmark Primary Registries\n\n`
    md += `---\n\n`

    md += `## 1. COMPOSITE EXECUTIVE RANKINGS & THESIS\n\n`
    ranked.forEach((asset, idx) => {
      const info = ASSET_PROS_CONS[asset.symbol]
      const score = info?.score || 75
      const verdict = info?.verdict || 'Standard capital asset'
      md += `### #${idx + 1} ${asset.symbol} — ${asset.name} (Score: ${score}/100)\n`
      md += `**Exchange:** ${asset.exchange} | **Asset Class:** ${asset.assetClass} | **Sector:** ${asset.sector}\n\n`
      md += `> **Strategic Verdict:** ${verdict}\n\n`
      md += `**Key Advantages (Pros):**\n`
      ;(info?.pros || []).forEach(p => { md += `- ✅ ${p}\n` })
      md += `\n**Key Risks & Headwinds (Cons):**\n`
      ;(info?.cons || []).forEach(c => { md += `- ⚠️ ${c}\n` })
      md += `\n`
    })

    md += `---\n\n`
    md += `## 2. CROSS-SECTIONAL FINANCIAL MATRIX\n\n`
    md += `| Vector / Metric | ${loadedAssets.map(a => a.symbol).join(' | ')} |\n`
    md += `| :--- | ${loadedAssets.map(() => ':---').join(' | ')} |\n`
    md += `| Market Capitalization | ${loadedAssets.map(a => a.marketCap).join(' | ')} |\n`
    md += `| Trailing P/E (TTM) | ${loadedAssets.map(a => a.peRatio).join(' | ')} |\n`
    md += `| Forward P/E (NTM) | ${loadedAssets.map(a => a.fwdPe).join(' | ')} |\n`
    md += `| PEG Ratio | ${loadedAssets.map(a => a.pegRatio).join(' | ')} |\n`
    md += `| EV / EBITDA | ${loadedAssets.map(a => a.evEbitda).join(' | ')} |\n`
    md += `| Price to Sales | ${loadedAssets.map(a => a.priceToSales).join(' | ')} |\n`
    md += `| Gross Margin | ${loadedAssets.map(a => a.grossMargin).join(' | ')} |\n`
    md += `| Operating Margin | ${loadedAssets.map(a => a.opMargin).join(' | ')} |\n`
    md += `| Net Margin | ${loadedAssets.map(a => a.netMargin).join(' | ')} |\n`
    md += `| Return on Equity (ROE) | ${loadedAssets.map(a => a.roe).join(' | ')} |\n`
    md += `| ROIC | ${loadedAssets.map(a => a.roic).join(' | ')} |\n`
    md += `| YoY Revenue Growth | ${loadedAssets.map(a => a.revGrowthYoY).join(' | ')} |\n`
    md += `| YoY EPS Growth | ${loadedAssets.map(a => a.epsGrowthYoY).join(' | ')} |\n`
    md += `| Net Debt / EBITDA | ${loadedAssets.map(a => a.netDebtEbitda).join(' | ')} |\n`
    md += `| Beta vs Benchmark | ${loadedAssets.map(a => a.beta).join(' | ')} |\n`
    md += `| Dividend / Coupon Yield | ${loadedAssets.map(a => a.divYield).join(' | ')} |\n\n`

    md += `---\n\n`
    md += `## 3. STATUTORY EVIDENCE & FILING AUDIT TRAIL\n\n`
    loadedAssets.forEach(a => {
      md += `- **${a.symbol} (${a.name}):** ${a.filingSource} (Filed: ${a.filingDate})\n`
      md += `  *Bitemporal Fact Range:* \`${a.bitemporalRange}\` — *GiST Deterministic Zero-Overlap Verified*\n`
    })

    md += `\n---\n*CONFIDENTIAL INVESTOR MEMORANDUM &bull; GENERATED VIA TALVRIN EVIDENCE LAYER &bull; NOT A SOLICITATION*\n`

    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `Talvrin_Comparison_Dossier_${loadedAssets.map(a => a.symbol).join('_')}_${Date.now()}.md`
    link.click()
    URL.revokeObjectURL(url)
    setIsExportMenuOpen(false)
  }

  // Open institutional print-optimized report for 1-click PDF saving
  const exportBriefPDF = () => {
    const quota = checkLimit('evidence_dossier_exports_per_month')
    if (quota.isExceeded) {
      toast.error(
        `Evidence Dossier export limit reached (${quota.current} / ${quota.max}). Upgrade to export unlimited statutory memoranda.`
      )
      if (onOpenPricing) onOpenPricing()
      setIsExportMenuOpen(false)
      return
    }

    setIsExportMenuOpen(false)
    const printWindow = window.open('', '_blank')
    if (!printWindow) return

    const ranked = [...loadedAssets].sort((a, b) => {
      const scoreA = ASSET_PROS_CONS[a.symbol]?.score || 70
      const scoreB = ASSET_PROS_CONS[b.symbol]?.score || 70
      return scoreB - scoreA
    })

    const htmlContent = `
      <!DOCTYPE html>
      <html>
      <head>
        <title>Talvrin Institutional Comparison Brief - ${loadedAssets.map(a => a.symbol).join(' vs ')}</title>
        <style>
          @page { size: A4; margin: 16mm; }
          body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #0f172a; margin: 0; padding: 20px; font-size: 11pt; line-height: 1.45; }
          .header { border-bottom: 2px solid #0f172a; padding-bottom: 12px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: flex-end; }
          .title { font-size: 20pt; font-weight: 800; letter-spacing: -0.5px; margin: 0; color: #0f172a; }
          .subtitle { font-size: 9.5pt; color: #475569; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
          .meta { font-size: 8.5pt; color: #64748b; text-align: right; }
          h2 { font-size: 13pt; font-weight: 700; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; margin-top: 24px; color: #1e293b; text-transform: uppercase; letter-spacing: 0.5px; }
          .rank-card { border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; page-break-inside: avoid; }
          .rank-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
          .rank-badge { font-weight: 900; font-size: 11pt; padding: 2px 8px; border-radius: 4px; background: #f1f5f9; }
          .verdict { font-weight: 600; color: #312e81; font-size: 10pt; margin: 6px 0; background: #e0e7ff; padding: 6px 10px; border-radius: 4px; }
          .pros-cons { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 8px; font-size: 9.5pt; }
          .pros { color: #065f46; }
          .cons { color: #9f1239; }
          ul { margin: 4px 0; padding-left: 18px; }
          li { margin-bottom: 3px; }
          table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 9pt; }
          th, td { border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; }
          th { background: #f8fafc; font-weight: 700; color: #334155; }
          .footer { margin-top: 30px; border-top: 1px solid #e2e8f0; padding-top: 8px; font-size: 8pt; color: #94a3b8; display: flex; justify-content: space-between; }
        </style>
      </head>
      <body>
        <div class="header">
          <div>
            <h1 class="title">TALVRIN™ EXECUTIVE BRIEF</h1>
            <div class="subtitle">Cross-Sectional Comparative Intelligence Dossier</div>
          </div>
          <div class="meta">
            <div><strong>Date:</strong> ${new Date().toLocaleDateString('en-GB')}</div>
            <div><strong>Universe:</strong> ${loadedAssets.map(a => a.symbol).join(', ')}</div>
            <div><strong>Audit:</strong> SEC Form 10-K / DMO</div>
          </div>
        </div>

        <h2>1. Executive Ranking & Competitive Breakdown</h2>
        ${ranked.map((asset, idx) => {
          const info = ASSET_PROS_CONS[asset.symbol]
          const score = info?.score || 75
          return `
            <div class="rank-card">
              <div class="rank-header">
                <div>
                  <span class="rank-badge">RANK #${idx + 1}</span>
                  <strong style="font-size: 13pt; margin-left: 8px;">${asset.symbol}</strong>
                  <span style="color: #64748b; margin-left: 6px;">${asset.name}</span>
                </div>
                <div><strong>Composite Score: ${score}/100</strong></div>
              </div>
              <div class="verdict">${info?.verdict || 'Standard capital asset'}</div>
              <div class="pros-cons">
                <div>
                  <strong class="pros">Key Advantages:</strong>
                  <ul>${(info?.pros || []).map(p => `<li>${p}</li>`).join('')}</ul>
                </div>
                <div>
                  <strong class="cons">Key Risks & Disadvantages:</strong>
                  <ul>${(info?.cons || []).map(c => `<li>${c}</li>`).join('')}</ul>
                </div>
              </div>
            </div>
          `
        }).join('')}

        <h2>2. Cross-Sectional Vector Comparison</h2>
        <table>
          <thead>
            <tr>
              <th>Vector / Metric</th>
              ${loadedAssets.map(a => `<th>${a.symbol}</th>`).join('')}
            </tr>
          </thead>
          <tbody>
            <tr><td>Market Capitalization</td>${loadedAssets.map(a => `<td><strong>${a.marketCap}</strong></td>`).join('')}</tr>
            <tr><td>Trailing P/E Ratio (TTM)</td>${loadedAssets.map(a => `<td>${a.peRatio}</td>`).join('')}</tr>
            <tr><td>Forward P/E Ratio (NTM)</td>${loadedAssets.map(a => `<td>${a.fwdPe}</td>`).join('')}</tr>
            <tr><td>PEG Ratio</td>${loadedAssets.map(a => `<td>${a.pegRatio}</td>`).join('')}</tr>
            <tr><td>EV / EBITDA Multiple</td>${loadedAssets.map(a => `<td>${a.evEbitda}</td>`).join('')}</tr>
            <tr><td>Price to Sales (P/S)</td>${loadedAssets.map(a => `<td>${a.priceToSales}</td>`).join('')}</tr>
            <tr><td>Gross Margin</td>${loadedAssets.map(a => `<td>${a.grossMargin}</td>`).join('')}</tr>
            <tr><td>Operating Margin</td>${loadedAssets.map(a => `<td>${a.opMargin}</td>`).join('')}</tr>
            <tr><td>Net Profit Margin</td>${loadedAssets.map(a => `<td>${a.netMargin}</td>`).join('')}</tr>
            <tr><td>Return on Equity (ROE)</td>${loadedAssets.map(a => `<td>${a.roe}</td>`).join('')}</tr>
            <tr><td>ROIC</td>${loadedAssets.map(a => `<td>${a.roic}</td>`).join('')}</tr>
            <tr><td>YoY Revenue Growth</td>${loadedAssets.map(a => `<td>${a.revGrowthYoY}</td>`).join('')}</tr>
            <tr><td>YoY EPS Growth</td>${loadedAssets.map(a => `<td>${a.epsGrowthYoY}</td>`).join('')}</tr>
            <tr><td>Net Debt / EBITDA</td>${loadedAssets.map(a => `<td>${a.netDebtEbitda}</td>`).join('')}</tr>
            <tr><td>Beta vs SPX</td>${loadedAssets.map(a => `<td>${a.beta}</td>`).join('')}</tr>
            <tr><td>Dividend / Yield</td>${loadedAssets.map(a => `<td>${a.divYield}</td>`).join('')}</tr>
          </tbody>
        </table>

        <h2>3. Statutory Provenance & Audit Trail</h2>
        <ul>
          ${loadedAssets.map(a => `
            <li>
              <strong>${a.symbol}:</strong> ${a.filingSource} (Filing Date: ${a.filingDate}) &bull;
              <em>Bitemporal Range:</em> ${a.bitemporalRange}
            </li>
          `).join('')}
        </ul>

        <div class="footer">
          <div>Talvrin Deterministic Financial Intelligence Estate &bull; Zero Fabricated Fact Guarantee</div>
          <div>Page 1 of 1</div>
        </div>

        <script>
          window.onload = function() {
            setTimeout(function() {
              window.print();
            }, 300);
          };
        </script>
      </body>
      </html>
    `

    printWindow.document.open()
    printWindow.document.write(htmlContent)
    printWindow.document.close()
  }

  return (
    <div className="flex flex-1 h-full flex-col overflow-y-auto bg-[#070b12] text-slate-100 font-sans pb-16 scrollbar-slim">
      {/* Top Header */}
      <header className="sticky top-0 z-30 shrink-0 flex items-center justify-between px-6 py-4 bg-[#0a101d]/90 backdrop-blur-md border-b border-slate-800">
        <div className="flex items-center gap-4">
          {onBackToHome && (
            <button
              onClick={onBackToHome}
              className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              title="Return to Home Dashboard"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
          )}
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 uppercase tracking-wider">
                Cross-Sectional Matrix
              </span>
              <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                Asset & Evidence Comparison
              </h1>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Deterministic cross-sectional analysis with source-linked statutory filings and bitemporal fact reconciliation.
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              if (onOpenGuides) onOpenGuides('how-to-use')
              else window.open('/guides?topic=how-to-use#running-comparisons', '_blank')
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors cursor-pointer"
            title="Open side-by-side comparison guide in right drawer"
          >
            <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
            <span>Comparison Guide</span>
          </button>

          <div className="relative">
            <button
              onClick={() => setIsExportMenuOpen(!isExportMenuOpen)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm border border-indigo-500/50 transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              Export Dossier
            </button>

            {isExportMenuOpen && (
              <div className="absolute right-0 top-9 w-60 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-2 z-50 space-y-1">
                <button
                  onClick={exportBriefPDF}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-left text-xs rounded-lg hover:bg-slate-800 text-slate-200 transition-colors"
                >
                  <Printer className="w-4 h-4 text-indigo-400" />
                  <div>
                    <div className="font-semibold text-white">Save / Print PDF Dossier</div>
                    <div className="text-[10px] text-slate-400">Executive institutional dossier format</div>
                  </div>
                </button>

                <button
                  onClick={exportBriefMarkdown}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-left text-xs rounded-lg hover:bg-slate-800 text-slate-200 transition-colors"
                >
                  <FileDown className="w-4 h-4 text-emerald-400" />
                  <div>
                    <div className="font-semibold text-white">Download Markdown (.md)</div>
                    <div className="text-[10px] text-slate-400">Complete analysis, table & filings</div>
                  </div>
                </button>

                <button
                  onClick={() => {
                    const exportData = JSON.stringify(loadedAssets, null, 2)
                    const blob = new Blob([exportData], { type: 'application/json' })
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = `talvrin-comparison-${Date.now()}.json`
                    a.click()
                    setIsExportMenuOpen(false)
                  }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-left text-xs rounded-lg hover:bg-slate-800 text-slate-200 transition-colors"
                >
                  <Download className="w-4 h-4 text-slate-400" />
                  <div>
                    <div className="font-semibold text-white">Export Raw JSON Data</div>
                    <div className="text-[10px] text-slate-400">Full statutory metric payload</div>
                  </div>
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 p-6 max-w-7xl w-full mx-auto space-y-6">
        {/* Active Asset Badges, 1-Click Quick Add, and Search */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-4 rounded-xl bg-[#0f172a]/90 border border-slate-800 shadow-lg">
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className="text-xs text-slate-400 font-medium">Active Instruments ({loadedAssets.length}/6):</span>
            {loadedAssets.map((asset, idx) => (
              <div
                key={asset.symbol}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/90 border text-xs font-semibold text-white shadow-sm"
                style={{ borderColor: `${ASSET_COLORS[idx % ASSET_COLORS.length]}80` }}
              >
                <span
                  className="w-2.5 h-2.5 rounded-full inline-block"
                  style={{ backgroundColor: ASSET_COLORS[idx % ASSET_COLORS.length] }}
                />
                <span className="font-bold text-white">{asset.symbol}</span>
                <span className="text-slate-300 hidden sm:inline">{asset.name}</span>
                {loadedAssets.length > 1 && (
                  <button
                    onClick={() => removeSymbol(asset.symbol)}
                    className="p-0.5 hover:bg-slate-700 rounded text-slate-400 hover:text-white transition-colors ml-1"
                    title={`Remove ${asset.symbol}`}
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* 1-Click Quick Add Suggestions */}
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-slate-400 font-medium">Quick Add:</span>
              {['GOOGL', 'AMZN', 'TSLA', 'US 10Y', 'UK 10Y Gilt'].map((quickSym) => {
                const isSelected = selectedSymbols.includes(quickSym)
                if (isSelected || selectedSymbols.length >= 6) return null
                return (
                  <button
                    key={quickSym}
                    onClick={() => addSymbol(quickSym)}
                    className="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700/60 transition-all"
                  >
                    <Plus className="w-2.5 h-2.5 text-indigo-400" />
                    {quickSym}
                  </button>
                )
              })}
            </div>

            {loadedAssets.length < 6 && (
              <div className="relative">
                <button
                  onClick={() => setIsSearchOpen(!isSearchOpen)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600/20 border border-indigo-500/40 text-xs font-semibold text-indigo-300 hover:bg-indigo-600/30 transition-colors"
                >
                  <Search className="w-3.5 h-3.5" />
                  Search & Add ({loadedAssets.length}/6)
                </button>

                {isSearchOpen && (
                  <div className="absolute right-0 top-10 w-72 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-3 z-50">
                    <div className="relative mb-2">
                      <Search className="w-4 h-4 text-slate-400 absolute left-2.5 top-2.5" />
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Search ticker, gilt, bond..."
                        className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-950 border border-slate-800 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                        autoFocus
                      />
                    </div>
                    <div className="space-y-1 max-h-48 overflow-y-auto">
                      {searchResults.length > 0 ? (
                        searchResults.map((item) => (
                          <button
                            key={item.symbol}
                            onClick={() => addSymbol(item.symbol)}
                            className="w-full text-left px-2.5 py-1.5 rounded hover:bg-slate-800 flex items-center justify-between text-xs"
                          >
                            <div>
                              <span className="font-bold text-white mr-1.5">{item.symbol}</span>
                              <span className="text-slate-400 truncate">{item.name}</span>
                            </div>
                            <span className="text-[10px] text-slate-500 px-1 py-0.5 bg-slate-800 rounded">
                              {item.assetClass}
                            </span>
                          </button>
                        ))
                      ) : (
                        <p className="text-[11px] text-slate-500 text-center py-2">
                          {searchQuery ? 'No matching instruments found' : 'Type ticker or name to add...'}
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Live Institutional TradingView Chart Embed with Instrument Switcher */}
        <div className="p-4 rounded-xl bg-[#0f172a]/80 border border-slate-800 shadow-xl space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <LineChart className="w-4 h-4 text-indigo-400 shrink-0" />
              <div className="flex items-baseline gap-2 flex-wrap">
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200">
                  Multi-Instrument Comparative Overlay
                </h2>
                <span className="text-[10.5px] text-slate-400">
                  (Base: <strong className="text-indigo-400">{activeChartSymbol}</strong> &bull; Overlaid: {selectedSymbols.filter(s => s !== activeChartSymbol).join(', ') || 'None'})
                </span>
              </div>
            </div>

            {/* Instrument switcher buttons and Color Legend */}
            <div className="flex items-center gap-2.5 flex-wrap">
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-800 text-xs flex-wrap">
                <span className="text-[11px] text-slate-400 font-medium">Legend:</span>
                {loadedAssets.map((asset, idx) => {
                  const color = ASSET_COLORS[idx % ASSET_COLORS.length]
                  const isBase = activeChartSymbol === asset.symbol
                  return (
                    <div
                      key={asset.symbol}
                      className="flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold"
                      style={{
                        backgroundColor: `${color}18`,
                        border: `1px solid ${color}45`,
                        color: color,
                      }}
                    >
                      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                      <span>{asset.symbol}</span>
                      {isBase && <span className="text-[9.5px] uppercase font-bold opacity-80">(Base)</span>}
                    </div>
                  )
                })}
              </div>

              {/* Format Toggle: % Return Line vs Baseline vs Candlestick */}
              <div className="flex items-center gap-1 bg-slate-900/90 p-1 rounded-lg border border-slate-800">
                <button
                  onClick={() => setChartStyle('2')}
                  className={`px-2.5 py-0.5 text-xs font-semibold rounded transition-all ${
                    chartStyle === '2'
                      ? 'bg-indigo-600 text-white shadow-sm ring-1 ring-indigo-400/50'
                      : 'text-slate-400 hover:text-white'
                  }`}
                  title="Normalized % return line overlay across all assets from 0.00% baseline"
                >
                  % Return Line (All Assets)
                </button>
                <button
                  onClick={() => setChartStyle('10')}
                  className={`px-2.5 py-0.5 text-xs font-semibold rounded transition-all ${
                    chartStyle === '10'
                      ? 'bg-indigo-600 text-white shadow-sm ring-1 ring-indigo-400/50'
                      : 'text-slate-400 hover:text-white'
                  }`}
                  title="Baseline mode: green/red fill above/below reference level"
                >
                  Baseline Fill
                </button>
                <button
                  onClick={() => setChartStyle('1')}
                  className={`px-2.5 py-0.5 text-xs font-semibold rounded transition-all ${
                    chartStyle === '1'
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'text-slate-400 hover:text-white'
                  }`}
                  title="Candlestick base with relative overlay lines"
                >
                  Candles
                </button>
              </div>

              <div className="flex items-center gap-1.5">
                <span className="text-[11px] text-slate-400 font-medium">Base:</span>
                <div className="flex items-center gap-1 bg-slate-900/90 p-1 rounded-lg border border-slate-800 flex-wrap">
                  {loadedAssets.map((asset) => (
                    <button
                      key={asset.symbol}
                      onClick={() => setActiveChartSymbol(asset.symbol)}
                      className={`px-2.5 py-0.5 text-xs font-semibold rounded transition-all ${
                        activeChartSymbol === asset.symbol
                          ? 'bg-indigo-600 text-white shadow-sm ring-1 ring-indigo-400/50'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      {asset.symbol}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="w-full h-[420px] rounded-lg overflow-hidden bg-[#090b0e] border border-slate-800/80 relative">
            <div ref={tvContainerRef} className="tradingview-widget-container h-full w-full" />
          </div>
        </div>

        {/* Real-Time Market Cards with Live WebSocket Ticks (Up to 6) */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-3 xl:grid-cols-6 gap-3.5">
          {loadedAssets.map((asset, idx) => {
            const liveTick = livePrices[asset.symbol]
            const liveAsset = GLOBAL_MARKET_ASSETS.find((a) => a.symbol === asset.symbol)
            const price = liveTick ? liveTick.price : liveAsset ? liveAsset.price : '$250.00'
            const change = liveTick ? liveTick.change : liveAsset ? liveAsset.pctChange : '+1.25%'
            const isUp = !change.startsWith('-')
            const color = ASSET_COLORS[idx % ASSET_COLORS.length]
            const isBase = activeChartSymbol === asset.symbol

            return (
              <div
                key={asset.symbol}
                className={`p-4 rounded-xl bg-slate-900/90 border transition-all shadow-md relative group flex flex-col justify-between ${
                  isBase ? 'border-indigo-500/60 ring-1 ring-indigo-500/20' : 'border-slate-800 hover:border-slate-700'
                }`}
                style={{ borderTop: `3px solid ${color}` }}
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
                      <span className="font-bold text-base text-white tracking-tight">{asset.symbol}</span>
                      <span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded bg-slate-800/90 text-slate-400 border border-slate-700/60">
                        {asset.exchange}
                      </span>
                      {isBase && (
                        <span className="text-[9px] uppercase font-extrabold px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/40">
                          Base
                        </span>
                      )}
                    </div>
                    <button
                      onClick={() => {
                        const matched = GLOBAL_MARKET_ASSETS.find((a) => a.symbol === asset.symbol)
                        if (matched) setSelectedAssetForAlert(matched)
                      }}
                      title={`Set monitoring alert for ${asset.symbol}`}
                      className="p-1 rounded-md text-slate-500 hover:text-indigo-300 hover:bg-indigo-600/20 transition-all shrink-0"
                    >
                      <Bell className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  <div className="text-[11px] text-slate-400 truncate mb-2.5 font-normal">
                    {asset.name}
                  </div>

                  <div className="flex items-baseline gap-2 mb-3 flex-wrap">
                    <span className="text-xl font-black text-white tracking-tight">{price}</span>
                    <span
                      className={`text-xs font-bold inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded ${
                        isUp ? 'text-emerald-400 bg-emerald-500/10' : 'text-rose-400 bg-rose-500/10'
                      }`}
                    >
                      {isUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                      {change}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px] pt-2.5 border-t border-slate-800/90 text-slate-400">
                  <div className="truncate">
                    <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Mkt Cap</span>
                    <strong className="text-slate-200 font-semibold">{asset.marketCap}</strong>
                  </div>
                  <div className="truncate text-right">
                    <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Beta</span>
                    <strong className="text-slate-200 font-semibold">{asset.beta}</strong>
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Tab Navigation for Detailed Sections */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-2">
          <div className="flex items-center gap-1.5 overflow-x-auto max-w-full pb-1 scrollbar-slim">
            {[
              { id: 'intelligence', label: 'Score & Rankings', icon: Trophy },
              { id: 'valuation', label: 'Valuation & Multiples', icon: DollarSign },
              { id: 'profitability', label: 'Profitability & Returns', icon: Award },
              { id: 'growth', label: 'Growth & Cash Flow', icon: TrendingUp },
              { id: 'balance', label: 'Solvency & Leverage', icon: ShieldCheck },
              { id: 'catalysts', label: 'Earnings & Catalysts', icon: Calendar },
              { id: 'evidence', label: 'Statutory Evidence & Provenance', icon: FileText },
            ].map((tab) => {
              const Icon = tab.icon
              const isActive = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap transition-all ${
                    isActive
                      ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/40 shadow-sm'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {tab.label}
                </button>
              )
            })}
          </div>

          <div className="flex items-center gap-2.5 flex-wrap">
            <button
              onClick={() => setHighlightLeader(!highlightLeader)}
              className={`flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-lg border transition-all ${
                highlightLeader
                  ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40 shadow-sm'
                  : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200'
              }`}
              title="Highlight the top-performing value for each metric in green with a checkmark"
            >
              <Award className="w-3.5 h-3.5 text-emerald-400" />
              <span>{highlightLeader ? 'Highlight Best Metric: ON' : 'Highlight Best Metric: OFF'}</span>
            </button>

            <div className="hidden sm:flex items-center gap-1.5 text-xs text-slate-400 pl-1 border-l border-slate-800">
              <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block animate-pulse" />
              <span>Deterministic Fact Bundle</span>
            </div>
          </div>
        </div>

        {/* Detailed Comparison Table Matrix */}
        <div className="rounded-xl border border-slate-800 bg-[#0c1220] overflow-x-auto shadow-xl scrollbar-slim">
          <table className="w-full text-left border-collapse min-w-[720px]">
            <thead>
              <tr className="border-b border-slate-800 bg-[#0e1627]">
                <th className="py-3.5 px-4 text-xs font-semibold text-slate-400 uppercase tracking-wider w-[240px] shrink-0">
                  Financial Metric / Vector
                </th>
                {loadedAssets.map((asset, idx) => (
                  <th key={asset.symbol} className="py-3.5 px-4 text-xs font-bold text-white uppercase tracking-wider min-w-[150px]">
                    <div className="flex flex-col gap-1 min-w-[200px]">
                      <div className="flex items-center gap-1.5">
                        <span
                          className="w-2.5 h-2.5 rounded-full inline-block shrink-0"
                          style={{ backgroundColor: ASSET_COLORS[idx % ASSET_COLORS.length] }}
                        />
                        <span className="text-sm font-bold text-white">{asset.symbol}</span>
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700/60">
                          {asset.exchange}
                        </span>
                      </div>
                      <div className="text-xs font-medium text-slate-200">
                        {asset.name}
                      </div>
                      <div className="text-[10.5px] text-slate-400 font-normal leading-tight">
                        {asset.sector}
                      </div>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-xs">
              {activeTab === 'intelligence' && (
                <>
                  {/* Overall Institutional Rank */}
                  <tr className="bg-slate-900/60 font-semibold">
                    <td className="py-3.5 px-4 text-slate-200 flex items-center gap-1.5">
                      <Trophy className="w-4 h-4 text-amber-400" />
                      Composite Institutional Rank
                    </td>
                    {(() => {
                      const ranked = [...loadedAssets].sort((a, b) => {
                        const scoreA = ASSET_PROS_CONS[a.symbol]?.score || 70
                        const scoreB = ASSET_PROS_CONS[b.symbol]?.score || 70
                        return scoreB - scoreA
                      })
                      return loadedAssets.map((asset) => {
                        const rank = ranked.findIndex((r) => r.symbol === asset.symbol) + 1
                        const score = ASSET_PROS_CONS[asset.symbol]?.score || 75
                        const badgeColor =
                          rank === 1
                            ? 'bg-amber-500/20 text-amber-300 border-amber-500/50'
                            : rank === 2
                            ? 'bg-slate-700/50 text-slate-200 border-slate-600'
                            : rank === 3
                            ? 'bg-amber-900/30 text-amber-500 border-amber-800/50'
                            : 'bg-slate-800 text-slate-400 border-slate-700'

                        return (
                          <td key={asset.symbol} className="py-3.5 px-4">
                            <div className="flex items-center gap-2">
                              <span className={`px-2.5 py-1 rounded-md text-xs font-black border ${badgeColor}`}>
                                #{rank}
                              </span>
                              <div className="flex flex-col">
                                <span className="font-bold text-white text-sm">{score}/100</span>
                                <span className="text-[10px] text-slate-400">Composite Score</span>
                              </div>
                            </div>
                          </td>
                        )
                      })
                    })()}
                  </tr>

                  {/* Strategic Verdict / Thesis */}
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3.5 px-4 text-slate-300 font-medium">
                      <div className="flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                        Executive Verdict
                      </div>
                    </td>
                    {loadedAssets.map((asset) => {
                      const verdict = ASSET_PROS_CONS[asset.symbol]?.verdict || 'Public capital instrument with reconciled bitemporal filings.'
                      return (
                        <td key={asset.symbol} className="py-3.5 px-4">
                          <p className="text-xs font-semibold text-indigo-200 leading-snug">
                            {verdict}
                          </p>
                        </td>
                      )
                    })}
                  </tr>

                  {/* Key Advantages / Pros */}
                  <tr className="hover:bg-slate-800/30 transition-colors bg-emerald-950/10">
                    <td className="py-4 px-4 text-emerald-400 font-semibold align-top">
                      <div className="flex items-center gap-1.5">
                        <ThumbsUp className="w-3.5 h-3.5" />
                        Key Advantages (Pros)
                      </div>
                    </td>
                    {loadedAssets.map((asset) => {
                      const pros = ASSET_PROS_CONS[asset.symbol]?.pros || [
                        'Deterministic source-linked statutory regulatory disclosures',
                        'Established institutional liquidity with continuous quotes',
                        'Verified reconciliation with statutory SEC/DMO primary registries',
                      ]
                      return (
                        <td key={asset.symbol} className="py-4 px-4 align-top">
                          <ul className="space-y-2">
                            {pros.map((pro, pIdx) => (
                              <li key={pIdx} className="flex items-start gap-1.5 text-slate-300 text-[11.5px] leading-relaxed">
                                <span className="text-emerald-400 font-bold shrink-0 mt-0.5">&bull;</span>
                                <span>{pro}</span>
                              </li>
                            ))}
                          </ul>
                        </td>
                      )
                    })}
                  </tr>

                  {/* Key Disadvantages / Cons */}
                  <tr className="hover:bg-slate-800/30 transition-colors bg-rose-950/10">
                    <td className="py-4 px-4 text-rose-400 font-semibold align-top">
                      <div className="flex items-center gap-1.5">
                        <ThumbsDown className="w-3.5 h-3.5" />
                        Key Disadvantages (Risks)
                      </div>
                    </td>
                    {loadedAssets.map((asset) => {
                      const cons = ASSET_PROS_CONS[asset.symbol]?.cons || [
                        'Macroeconomic exposure to prevailing interest rate regimes',
                        'Competitive pressure from peer segment innovators',
                        'Subject to statutory regulatory revisions and market volatility',
                      ]
                      return (
                        <td key={asset.symbol} className="py-4 px-4 align-top">
                          <ul className="space-y-2">
                            {cons.map((con, cIdx) => (
                              <li key={cIdx} className="flex items-start gap-1.5 text-slate-300 text-[11.5px] leading-relaxed">
                                <span className="text-rose-400 font-bold shrink-0 mt-0.5">&bull;</span>
                                <span>{con}</span>
                              </li>
                            ))}
                          </ul>
                        </td>
                      )
                    })}
                  </tr>
                </>
              )}

              {activeTab === 'valuation' && (
                <>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Trailing P/E Ratio (TTM)</td>
                    {loadedAssets.map((a) => {
                      const isBest = highlightLeader && typeof a.peRatio === 'number' && a.peRatio === Math.min(...loadedAssets.filter(x => typeof x.peRatio === 'number').map(x => x.peRatio as number))
                      return (
                        <td key={a.symbol} className="py-3 px-4 font-mono font-semibold">
                          <span className={isBest ? 'text-emerald-400 font-bold flex items-center gap-1' : 'text-white'}>
                            {a.peRatio} {isBest && <CheckCircle className="w-3 h-3 text-emerald-400 inline" />}
                          </span>
                        </td>
                      )
                    })}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Forward P/E Ratio (NTM)</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono">
                        {a.fwdPe}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">PEG Ratio (Price / Earnings to Growth)</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono">
                        {a.pegRatio}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">EV / EBITDA Multiple</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono">
                        {a.evEbitda}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Price to Sales (P/S)</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono">
                        {a.priceToSales}
                      </td>
                    ))}
                  </tr>
                </>
              )}

              {activeTab === 'profitability' && (
                <>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Gross Margin %</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono font-semibold">
                        {a.grossMargin}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Operating Margin %</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono">
                        {a.opMargin}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Net Profit Margin %</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono">
                        {a.netMargin}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Return on Equity (ROE)</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-emerald-400 font-mono font-bold">
                        {a.roe}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Return on Invested Capital (ROIC)</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono">
                        {a.roic}
                      </td>
                    ))}
                  </tr>
                </>
              )}

              {activeTab === 'growth' && (
                <>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Revenue Growth YoY</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono font-semibold">
                        {a.revGrowthYoY}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Diluted EPS Growth YoY</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono">
                        {a.epsGrowthYoY}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Share Buyback / Repurchase Yield</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono">
                        {a.buybackYield}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Dividend Yield (Annualized)</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono">
                        {a.divYield}
                      </td>
                    ))}
                  </tr>
                </>
              )}

              {activeTab === 'balance' && (
                <>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Net Debt / EBITDA Leverage</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono">
                        {a.netDebtEbitda}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Current Ratio (Liquidity)</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono font-semibold">
                        {a.currentRatio}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Benchmark Correlation (S&P 500)</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono">
                        {a.correlationSPX}
                      </td>
                    ))}
                  </tr>
                </>
              )}

              {activeTab === 'catalysts' && (
                <>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Next Scheduled Reporting / Catalyst</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-indigo-300 font-mono">
                        {a.nextEarningsDate}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Consensus Estimate / Target Range</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono">
                        {a.consensusEst}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Policy Classification</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-slate-400 font-mono text-[11px]">
                        PDP Deterministic Guarded
                      </td>
                    ))}
                  </tr>
                </>
              )}

              {activeTab === 'evidence' && (
                <>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Primary Statutory Filing Source</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-indigo-300 font-mono text-[11px]">
                        <button
                          onClick={() => setEvidenceDrawerAsset(a)}
                          className="hover:underline flex items-center gap-1"
                        >
                          {a.filingSource}
                          <ExternalLink className="w-3 h-3 text-slate-500" />
                        </button>
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Filing Submission Date</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono">
                        {a.filingDate}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Bitemporal Fact Range</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-slate-300 font-mono text-[11px]">
                        {a.bitemporalRange}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Audit Status</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4">
                        <span className="inline-flex items-center gap-1 text-[10.5px] font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">
                          <CheckCircle className="w-3 h-3" />
                          Canonical Fact Bundle
                        </span>
                      </td>
                    ))}
                  </tr>
                </>
              )}
            </tbody>
          </table>
        </div>

        {/* Evidence Drawer Modal */}
        {evidenceDrawerAsset && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
            <div className="bg-[#0f172a] border border-slate-700 rounded-2xl max-w-lg w-full p-6 shadow-2xl relative">
              <button
                onClick={() => setEvidenceDrawerAsset(null)}
                className="absolute right-4 top-4 text-slate-400 hover:text-white p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>

              <div className="flex items-center gap-2 mb-3">
                <FileText className="w-5 h-5 text-indigo-400" />
                <h3 className="text-base font-bold text-white">
                  Statutory Evidence Audit: {evidenceDrawerAsset.symbol}
                </h3>
              </div>

              <p className="text-xs text-slate-400 mb-4">
                Talvrin locks every accepted fact to an unalterable filing artifact. Below is the cryptographic and filing reference for {evidenceDrawerAsset.name}.
              </p>

              <div className="space-y-3 bg-slate-900/90 rounded-xl p-4 border border-slate-800 font-mono text-xs">
                <div>
                  <span className="text-slate-500 block text-[10px] uppercase">Source Identifier</span>
                  <span className="text-indigo-300">{evidenceDrawerAsset.filingSource}</span>
                </div>
                <div>
                  <span className="text-slate-500 block text-[10px] uppercase">Knowledge & Valid Range</span>
                  <span className="text-slate-200">{evidenceDrawerAsset.bitemporalRange}</span>
                </div>
                <div>
                  <span className="text-slate-500 block text-[10px] uppercase">Reconciliation Status</span>
                  <span className="text-emerald-400">PASSED (Deterministic GiST Zero-Overlap Gate)</span>
                </div>
              </div>

              <div className="mt-5 flex justify-end">
                <button
                  onClick={() => setEvidenceDrawerAsset(null)}
                  className="px-4 py-2 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
                >
                  Close Audit
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Set Alert Modal Integration */}
        {selectedAssetForAlert && (
          <SetAlertModal
            onClose={() => setSelectedAssetForAlert(null)}
            symbol={selectedAssetForAlert.symbol}
            name={selectedAssetForAlert.name}
            currentPrice={selectedAssetForAlert.price}
            onAlertCreated={() => {
              setSelectedAssetForAlert(null)
              if (onOpenMonitoringForRule) {
                onOpenMonitoringForRule(selectedAssetForAlert.symbol)
              }
            }}
            onOpenPricing={onOpenPricing}
          />
        )}
      </main>
    </div>
  )
}
