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
  FileDown,
  Printer,
  BookOpen,
} from 'lucide-react'
import {
  GLOBAL_MARKET_ASSETS,
  MarketAsset,
  UNVERIFIED_SOURCE_LABEL,
  UNVERIFIED_FRESHNESS_LABEL,
  UNVERIFIED_STATUS_LABEL,
} from '../data/globalAssets'
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
}

const ASSET_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#06b6d4', '#a855f7']

// Every field below that a real backend connector doesn't back is set to
// NOT_AVAILABLE, never a plausible-looking invented number - this file
// used to hardcode an entire fake "Institutional SEC / DMO verified
// statutory financial database" (specific P/E, EV/EBITDA, ROE, beta,
// invented SEC filing accession numbers, fake "GiST Deterministic
// Zero-Overlap Verified" bitemporal ranges) for every symbol, shown
// on-screen, in an "evidence" drawer, and in two export formats whose
// own footer claimed "Zero Fabricated Fact Guarantee". None of it was
// real: no calculation spec exists anywhere in this platform for P/E,
// EV/EBITDA or any other equity ratio, for any symbol (confirmed against
// backend/app/modules/calculation/ during the 2026-11-13 UAT gap-analysis
// audit, G03/G05/G14). Source/freshness/provenance now come from the
// same isVerifiedLiveAsset labeling globalAssets.ts already applies
// everywhere else, instead of a separate, parallel fabrication.
const NOT_AVAILABLE = 'Not available'

function toDetailedMetrics(sym: string): DetailedAssetMetrics {
  const asset = GLOBAL_MARKET_ASSETS.find((a) => a.symbol === sym)
  return {
    symbol: sym,
    name: asset ? asset.name : sym,
    assetClass: asset ? asset.assetClass : 'EQUITY',
    sector: NOT_AVAILABLE,
    exchange: NOT_AVAILABLE,
    marketCap: NOT_AVAILABLE,
    peRatio: NOT_AVAILABLE,
    fwdPe: NOT_AVAILABLE,
    pegRatio: NOT_AVAILABLE,
    evEbitda: NOT_AVAILABLE,
    priceToSales: NOT_AVAILABLE,
    grossMargin: NOT_AVAILABLE,
    opMargin: NOT_AVAILABLE,
    netMargin: NOT_AVAILABLE,
    roe: NOT_AVAILABLE,
    roic: NOT_AVAILABLE,
    revGrowthYoY: NOT_AVAILABLE,
    epsGrowthYoY: NOT_AVAILABLE,
    netDebtEbitda: NOT_AVAILABLE,
    currentRatio: NOT_AVAILABLE,
    divYield: NOT_AVAILABLE,
    buybackYield: NOT_AVAILABLE,
    beta: NOT_AVAILABLE,
    correlationSPX: NOT_AVAILABLE,
    filingSource: asset ? asset.source : UNVERIFIED_SOURCE_LABEL,
    filingDate: asset ? asset.freshness : UNVERIFIED_FRESHNESS_LABEL,
    bitemporalRange: asset ? asset.bitemporalStatus : UNVERIFIED_STATUS_LABEL,
    nextEarningsDate: NOT_AVAILABLE,
    consensusEst: NOT_AVAILABLE,
  }
}


export function ComparisonPage({
  onBackToHome,
  onOpenMonitoringForRule,
  onOpenGuides,
  onOpenPricing,
  initialSymbols = [],
}: ComparisonPageProps) {
  // Persist comparison universe and base across reloads in current tab session
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>(() => {
    try {
      const saved = sessionStorage.getItem('talvrin_comparison_symbols')
      if (saved) {
        const parsed = JSON.parse(saved)
        if (Array.isArray(parsed)) return parsed.slice(0, 6)
      }
    } catch {
      // fallback
    }
    return initialSymbols
  })

  const [activeChartSymbol, setActiveChartSymbol] = useState<string>(() => {
    try {
      const saved = sessionStorage.getItem('talvrin_comparison_base')
      if (saved) return saved
    } catch {
      // fallback
    }
    return initialSymbols[0] || ''
  })

  // Clean up legacy localStorage keys if present
  useEffect(() => {
    try {
      localStorage.removeItem('talvrin_comparison_symbols')
      localStorage.removeItem('talvrin_comparison_base')
    } catch {
      // ignore
    }
  }, [])

  // Save changes to sessionStorage
  useEffect(() => {
    try {
      sessionStorage.setItem('talvrin_comparison_symbols', JSON.stringify(selectedSymbols))
    } catch {
      // ignore
    }
  }, [selectedSymbols])

  useEffect(() => {
    try {
      sessionStorage.setItem('talvrin_comparison_base', activeChartSymbol)
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
  const [isExportMenuOpen, setIsExportMenuOpen] = useState(false)

  // Live tick updates from websocket context
  const { livePrices } = useLiveMarket()

  // Real TradingView multi-symbol container
  const tvContainerRef = useRef<HTMLDivElement>(null)

  // Keep activeChartSymbol in sync if symbol removed
  useEffect(() => {
    if (selectedSymbols.length === 0) {
      setActiveChartSymbol('')
    } else if (!selectedSymbols.includes(activeChartSymbol)) {
      setActiveChartSymbol(selectedSymbols[0])
    }
  }, [selectedSymbols, activeChartSymbol])

  const [chartStyle, setChartStyle] = useState<'2' | '10' | '1'>('2') // '2' is % Return Line (all curves full width), '10' is Baseline, '1' is Candlestick

  // Embed verified live TradingView market comparison chart
  useEffect(() => {
    const container = tvContainerRef.current
    if (!container) return

    if (!activeChartSymbol || selectedSymbols.length === 0) {
      container.innerHTML = ''
      return
    }

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
      if (!activeChartSymbol) {
        setActiveChartSymbol(sym)
      }
    }
    setSearchQuery('')
    setIsSearchOpen(false)
  }

  const removeSymbol = (sym: string) => {
    setSelectedSymbols(selectedSymbols.filter((s) => s !== sym))
  }

  // Load metrics for selected assets
  const loadedAssets = useMemo(() => {
    return selectedSymbols.map(toDetailedMetrics)
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

  // Generate clean Markdown brief
  const exportBriefMarkdown = () => {
    const quota = checkLimit('evidence_dossier_exports_per_month')
    if (quota.isExceeded) {
      toast.error(
        `Export limit reached (${quota.current} / ${quota.max}). Upgrade to export unlimited comparisons.`
      )
      if (onOpenPricing) onOpenPricing()
      setIsExportMenuOpen(false)
      return
    }

    const timestamp = new Date().toISOString()

    let md = `# TALVRIN™ Asset Comparison Export\n\n`
    md += `- **Date & Time (UTC):** ${timestamp}\n`
    md += `- **Universe:** ${loadedAssets.map(a => a.symbol).join(', ')}\n`
    md += `- **Anchor Base Asset:** ${activeChartSymbol}\n`
    md += `- **Note:** Fundamental ratios below are not yet computed by Talvrin for any instrument and are shown as Not available rather than invented.\n\n`
    md += `---\n\n`

    md += `## 1. Cross-Sectional Financial Matrix\n\n`
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
    md += `## 2. Source & Verification Status\n\n`
    loadedAssets.forEach(a => {
      md += `- **${a.symbol} (${a.name}):** ${a.filingSource}\n`
      md += `  *Freshness:* ${a.filingDate} &bull; *Bitemporal status:* ${a.bitemporalRange}\n`
    })

    md += `\n---\n*Generated by Talvrin. Not a solicitation or investment recommendation.*\n`

    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `Talvrin_Comparison_${loadedAssets.map(a => a.symbol).join('_')}_${Date.now()}.md`
    link.click()
    URL.revokeObjectURL(url)
    setIsExportMenuOpen(false)
  }

  // Open institutional print-optimized report for 1-click PDF saving
  const exportBriefPDF = () => {
    const quota = checkLimit('evidence_dossier_exports_per_month')
    if (quota.isExceeded) {
      toast.error(
        `Export limit reached (${quota.current} / ${quota.max}). Upgrade to export unlimited comparisons.`
      )
      if (onOpenPricing) onOpenPricing()
      setIsExportMenuOpen(false)
      return
    }

    setIsExportMenuOpen(false)
    const printWindow = window.open('', '_blank')
    if (!printWindow) return

    const htmlContent = `
      <!DOCTYPE html>
      <html>
      <head>
        <title>Talvrin Comparison Export - ${loadedAssets.map(a => a.symbol).join(' vs ')}</title>
        <style>
          @page { size: A4; margin: 16mm; }
          body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #0f172a; margin: 0; padding: 20px; font-size: 11pt; line-height: 1.45; }
          .header { border-bottom: 2px solid #0f172a; padding-bottom: 12px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: flex-end; }
          .title { font-size: 20pt; font-weight: 800; letter-spacing: -0.5px; margin: 0; color: #0f172a; }
          .subtitle { font-size: 9.5pt; color: #475569; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
          .meta { font-size: 8.5pt; color: #64748b; text-align: right; }
          h2 { font-size: 13pt; font-weight: 700; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; margin-top: 24px; color: #1e293b; text-transform: uppercase; letter-spacing: 0.5px; }
          table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 9pt; }
          th, td { border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; }
          th { background: #f8fafc; font-weight: 700; color: #334155; }
          .footer { margin-top: 30px; border-top: 1px solid #e2e8f0; padding-top: 8px; font-size: 8pt; color: #94a3b8; display: flex; justify-content: space-between; }
        </style>
      </head>
      <body>
        <div class="header">
          <div>
            <h1 class="title">TALVRIN™ Comparison Export</h1>
            <div class="subtitle">Not a solicitation or investment recommendation</div>
          </div>
          <div class="meta">
            <div><strong>Date:</strong> ${new Date().toLocaleDateString('en-GB')}</div>
            <div><strong>Universe:</strong> ${loadedAssets.map(a => a.symbol).join(', ')}</div>
          </div>
        </div>
        <p style="font-size: 8.5pt; color: #64748b;">Fundamental ratios below are not yet computed by Talvrin for any instrument and are shown as "Not available" rather than invented.</p>

        <h2>1. Cross-Sectional Vector Comparison</h2>
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

        <h2>2. Source &amp; Verification Status</h2>
        <ul>
          ${loadedAssets.map(a => `
            <li>
              <strong>${a.symbol}:</strong> ${a.filingSource} &bull;
              <em>Freshness:</em> ${a.filingDate} &bull;
              <em>Bitemporal status:</em> ${a.bitemporalRange}
            </li>
          `).join('')}
        </ul>

        <div class="footer">
          <div>Generated by Talvrin</div>
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
              <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                Asset & Evidence Comparison
              </h1>
            </div>
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
              onClick={() => {
                if (loadedAssets.length === 0) {
                  toast.error('Select at least one asset to export comparison.')
                  return
                }
                setIsExportMenuOpen(!isExportMenuOpen)
              }}
              disabled={loadedAssets.length === 0}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border transition-colors ${
                loadedAssets.length === 0
                  ? 'bg-slate-800/60 text-slate-500 border-slate-700/50 cursor-not-allowed opacity-50'
                  : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm border-indigo-500/50'
              }`}
            >
              <Download className="w-3.5 h-3.5" />
              Export
            </button>

            {isExportMenuOpen && (
              <div className="absolute right-0 top-9 w-60 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-2 z-50 space-y-1">
                <button
                  onClick={exportBriefPDF}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-left text-xs rounded-lg hover:bg-slate-800 text-slate-200 transition-colors"
                >
                  <Printer className="w-4 h-4 text-indigo-400" />
                  <div>
                    <div className="font-semibold text-white">Save / Print PDF</div>
                    <div className="text-[10px] text-slate-400">Institutional brief format</div>
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
            {loadedAssets.length === 0 ? (
              <span className="text-xs text-slate-500 italic">No instruments selected</span>
            ) : (
              loadedAssets.map((asset, idx) => (
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
                  <button
                    onClick={() => removeSymbol(asset.symbol)}
                    className="p-0.5 hover:bg-slate-700 rounded text-slate-400 hover:text-white transition-colors ml-1"
                    title={`Remove ${asset.symbol}`}
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))
            )}
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

        {/* Empty State Banner when no instruments selected */}
        {loadedAssets.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-12 text-center rounded-2xl bg-[#0f172a]/70 border border-slate-800 shadow-xl space-y-4 my-8">
            <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
              <LineChart className="w-8 h-8" />
            </div>
            <div className="max-w-md space-y-1.5">
              <h3 className="text-lg font-bold text-white tracking-tight">No Assets Selected</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Add instruments to start comparing live price movements, SEC filings, statutory balance sheets, and cross-sectional valuation multiples.
              </p>
            </div>
            <div className="flex items-center gap-2 pt-2 flex-wrap justify-center">
              <span className="text-xs text-slate-400 font-medium mr-1">Popular:</span>
              {['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'US 10Y'].map((sym) => (
                <button
                  key={sym}
                  onClick={() => addSymbol(sym)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-all hover:border-indigo-500/50"
                >
                  <Plus className="w-3 h-3 text-indigo-400" />
                  {sym}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
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
              { id: 'valuation', label: 'Valuation & Multiples', icon: DollarSign },
              { id: 'profitability', label: 'Profitability & Returns', icon: Award },
              { id: 'growth', label: 'Growth & Cash Flow', icon: TrendingUp },
              { id: 'balance', label: 'Solvency & Leverage', icon: ShieldCheck },
              { id: 'catalysts', label: 'Earnings & Catalysts', icon: Calendar },
              { id: 'evidence', label: 'Source & Verification', icon: FileText },
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
              title="Mark the lowest Trailing P/E among the loaded instruments — a lower multiple is not automatically the better investment, just the lower number"
            >
              <Award className="w-3.5 h-3.5 text-emerald-400" />
              <span>{highlightLeader ? 'Highlight values: ON' : 'Highlight values: OFF'}</span>
            </button>
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
                    <td className="py-3 px-4 text-slate-300 font-medium">Source</td>
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
                    <td className="py-3 px-4 text-slate-300 font-medium">Freshness</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-white font-mono">
                        {a.filingDate}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Bitemporal status</td>
                    {loadedAssets.map((a) => (
                      <td key={a.symbol} className="py-3 px-4 text-slate-300 font-mono text-[11px]">
                        {a.bitemporalRange}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-slate-300 font-medium">Verification status</td>
                    {loadedAssets.map((a) => {
                      const verified = a.bitemporalRange === 'CANONICAL' || a.bitemporalRange === 'RECONCILED'
                      return (
                        <td key={a.symbol} className="py-3 px-4">
                          {verified ? (
                            <span className="inline-flex items-center gap-1 text-[10.5px] font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">
                              <CheckCircle className="w-3 h-3" />
                              Verified
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[10.5px] font-semibold text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-full">
                              Not independently verified
                            </span>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                </>
              )}
            </tbody>
          </table>
        </div>
          </>
        )}

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
                  Source &amp; verification status: {evidenceDrawerAsset.symbol}
                </h3>
              </div>

              <p className="text-xs text-slate-400 mb-4">
                What Talvrin actually knows about the source and freshness of {evidenceDrawerAsset.name}&apos;s data.
              </p>

              <div className="space-y-3 bg-slate-900/90 rounded-xl p-4 border border-slate-800 font-mono text-xs">
                <div>
                  <span className="text-slate-500 block text-[10px] uppercase">Source</span>
                  <span className="text-indigo-300">{evidenceDrawerAsset.filingSource}</span>
                </div>
                <div>
                  <span className="text-slate-500 block text-[10px] uppercase">Freshness</span>
                  <span className="text-slate-200">{evidenceDrawerAsset.filingDate}</span>
                </div>
                <div>
                  <span className="text-slate-500 block text-[10px] uppercase">Bitemporal status</span>
                  <span className={evidenceDrawerAsset.bitemporalRange === 'UNVERIFIED' ? 'text-amber-400' : 'text-emerald-400'}>
                    {evidenceDrawerAsset.bitemporalRange}
                  </span>
                </div>
              </div>

              <div className="mt-5 flex justify-end">
                <button
                  onClick={() => setEvidenceDrawerAsset(null)}
                  className="px-4 py-2 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
                >
                  Close
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
