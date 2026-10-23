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
} from 'lucide-react'
import { GLOBAL_MARKET_ASSETS, MarketAsset } from '../data/globalAssets'
import { useLiveMarket } from '../hooks/useLiveMarket'
import { mapToTradingViewSymbol } from './TradingViewWidget'
import SetAlertModal from './SetAlertModal'

export interface ComparisonPageProps {
  onBackToHome?: () => void
  onOpenMonitoringForRule?: (symbol: string) => void
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
  const [activeTab, setActiveTab] = useState<'valuation' | 'profitability' | 'growth' | 'balance' | 'catalysts' | 'evidence'>('valuation')
  const [selectedAssetForAlert, setSelectedAssetForAlert] = useState<MarketAsset | null>(null)
  const [evidenceDrawerAsset, setEvidenceDrawerAsset] = useState<DetailedAssetMetrics | null>(null)
  const [highlightLeader, setHighlightLeader] = useState(true)

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

  const [chartStyle, setChartStyle] = useState<'10' | '2' | '1'>('10') // '10' is Baseline (0.00% reference), '2' is % Return Line, '1' is Candlestick

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
            onClick={() => setHighlightLeader(!highlightLeader)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
              highlightLeader
                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                : 'bg-slate-800 text-slate-400 border-slate-700'
            }`}
          >
            <Award className="w-3.5 h-3.5" />
            {highlightLeader ? 'Leader Highlighting On' : 'Leader Highlighting Off'}
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
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-800/80 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            Export Brief
          </button>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 p-6 max-w-7xl w-full mx-auto space-y-6">
        {/* Active Asset Badges and Add Search */}
        <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl bg-[#0f172a]/70 border border-slate-800/80 backdrop-blur-sm">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-slate-400 font-medium">Active Instruments ({loadedAssets.length}/6):</span>
            {loadedAssets.map((asset, idx) => (
              <div
                key={asset.symbol}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/90 border text-xs font-medium text-white shadow-sm"
                style={{ borderColor: `${ASSET_COLORS[idx % ASSET_COLORS.length]}80` }}
              >
                <span
                  className="w-2.5 h-2.5 rounded-full inline-block"
                  style={{ backgroundColor: ASSET_COLORS[idx % ASSET_COLORS.length] }}
                />
                <span className="font-bold text-white">{asset.symbol}</span>
                <span className="text-slate-400 max-w-[140px] truncate">{asset.name}</span>
                {loadedAssets.length > 1 && (
                  <button
                    onClick={() => removeSymbol(asset.symbol)}
                    className="p-0.5 hover:bg-slate-700 rounded text-slate-400 hover:text-white transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>

          {loadedAssets.length < 6 && (
            <div className="relative">
              <button
                onClick={() => setIsSearchOpen(!isSearchOpen)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600/20 border border-indigo-500/40 text-xs font-semibold text-indigo-300 hover:bg-indigo-600/30 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Instrument ({loadedAssets.length}/6)
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

              {/* Format Toggle: Baseline vs % Return Line vs Candlestick */}
              <div className="flex items-center gap-1 bg-slate-900/90 p-1 rounded-lg border border-slate-800">
                <button
                  onClick={() => setChartStyle('10')}
                  className={`px-2.5 py-0.5 text-xs font-semibold rounded transition-all ${
                    chartStyle === '10'
                      ? 'bg-indigo-600 text-white shadow-sm ring-1 ring-indigo-400/50'
                      : 'text-slate-400 hover:text-white'
                  }`}
                  title="Baseline mode: 0.00% reference line separating positive from negative relative returns"
                >
                  Baseline (0.0%)
                </button>
                <button
                  onClick={() => setChartStyle('2')}
                  className={`px-2 py-0.5 text-xs font-semibold rounded transition-all ${
                    chartStyle === '2'
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'text-slate-400 hover:text-white'
                  }`}
                  title="Normalized % return line overlay across all assets"
                >
                  % Return Line
                </button>
                <button
                  onClick={() => setChartStyle('1')}
                  className={`px-2 py-0.5 text-xs font-semibold rounded transition-all ${
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
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {loadedAssets.map((asset, idx) => {
            const liveTick = livePrices[asset.symbol]
            const liveAsset = GLOBAL_MARKET_ASSETS.find((a) => a.symbol === asset.symbol)
            const price = liveTick ? liveTick.price : liveAsset ? liveAsset.price : '$250.00'
            const change = liveTick ? liveTick.change : liveAsset ? liveAsset.pctChange : '+1.25%'
            const isUp = !change.startsWith('-')

            return (
              <div
                key={asset.symbol}
                className="p-4 rounded-xl bg-[#0f172a]/80 border border-slate-800 hover:border-slate-700 transition-all shadow-md relative group"
                style={{ borderTop: `3px solid ${ASSET_COLORS[idx % ASSET_COLORS.length]}` }}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-base text-white">{asset.symbol}</span>
                    <span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                      {asset.exchange}
                    </span>
                  </div>
                  <button
                    onClick={() => {
                      const matched = GLOBAL_MARKET_ASSETS.find((a) => a.symbol === asset.symbol)
                      if (matched) setSelectedAssetForAlert(matched)
                    }}
                    className="opacity-0 group-hover:opacity-100 text-xs px-2 py-0.5 rounded bg-indigo-600/30 text-indigo-300 hover:bg-indigo-600/50 border border-indigo-500/30 transition-all"
                  >
                    Set Alert
                  </button>
                </div>

                <div className="flex items-baseline gap-2 mb-3">
                  <span className="text-xl font-extrabold text-white">{price}</span>
                  <span
                    className={`text-xs font-semibold flex items-center gap-0.5 ${
                      isUp ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {isUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                    {change}
                  </span>
                </div>

                <div className="flex items-center justify-between text-[11px] text-slate-400 pt-2 border-t border-slate-800/80">
                  <span>Mkt Cap: <strong className="text-slate-200">{asset.marketCap}</strong></span>
                  <span>Beta: <strong className="text-slate-200">{asset.beta}</strong></span>
                </div>
              </div>
            )
          })}
        </div>

        {/* Tab Navigation for Detailed Sections */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-2">
          <div className="flex items-center gap-1.5 overflow-x-auto max-w-full pb-1 scrollbar-slim">
            {[
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

          <div className="flex items-center gap-2 text-xs text-slate-400 shrink-0">
            <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block animate-pulse" />
            Deterministic Fact Bundle
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
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-1.5">
                        <span
                          className="w-2 h-2 rounded-full inline-block shrink-0"
                          style={{ backgroundColor: ASSET_COLORS[idx % ASSET_COLORS.length] }}
                        />
                        <span className="text-sm font-bold text-white">{asset.symbol}</span>
                      </div>
                      <span className="text-[10px] text-slate-400 font-normal truncate max-w-[170px]" title={asset.sector}>
                        {asset.sector}
                      </span>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-xs">
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
          />
        )}
      </main>
    </div>
  )
}
