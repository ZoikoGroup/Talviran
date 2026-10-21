import { useState } from 'react'
import { createPortal } from 'react-dom'
import {
  X,
  Search,
  Bell,
  ShieldCheck,
  Clock,
  LineChart,
  CandlestickChart,
  ExternalLink,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import InstitutionalChart from '@/components/InstitutionalChart'
import TradingViewWidget, { mapToTradingViewSymbol } from '@/components/TradingViewWidget'
import SetAlertModal from '@/components/SetAlertModal'
import { toast } from 'sonner'
import type { TaggedAsset } from '@/data/mockReply'

interface TradingViewModalProps {
  symbol: string
  name: string
  assetClass: string
  last: string
  change: string
  pctChange: string
  direction: 'up' | 'down' | 'flat'
  source: string
  freshness: string
  bitemporalStatus: string
  onClose: () => void
  onStartResearch: (asset: TaggedAsset, prompt?: string) => void
  onOpenMonitoring: (symbol: string) => void
}

type Timeframe = '1D' | '1W' | '1M' | '3M' | '1Y' | '5Y' | 'ALL'
type ChartMode = 'candles' | 'area'

interface HoverQuote {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export default function TradingViewModal({
  symbol,
  name,
  assetClass,
  last,
  change,
  pctChange,
  direction,
  source,
  freshness,
  bitemporalStatus,
  onClose,
  onStartResearch,
  onOpenMonitoring: _onOpenMonitoring,
}: TradingViewModalProps) {
  const isSovereign = assetClass === 'SOVEREIGN' || symbol.toLowerCase().includes('gilt') || symbol.toLowerCase().includes('treasury') || symbol.toLowerCase().includes('bund') || symbol.toLowerCase().includes('jgb')
  
  const [timeframe, setTimeframe] = useState<Timeframe>('1M')
  const [chartMode, setChartMode] = useState<ChartMode>('candles')
  const [useTradingViewEmbed, setUseTradingViewEmbed] = useState(false)
  const [isMaximized, setIsMaximized] = useState(false)
  const [hoverQuote, setHoverQuote] = useState<HoverQuote | null>(null)
  const [showSetAlert, setShowSetAlert] = useState(false)

  const isUp = direction === 'up'
  const isDown = direction === 'down'
  const tvSymbol = mapToTradingViewSymbol(symbol)

  const handleAskTalvrin = () => {
    // Closes modal and redirects to Talvrin chat with the active product/asset tagged and query populated
    onClose()
    onStartResearch(
      {
        symbol,
        name,
        assetClass,
        price: last,
        change,
        pctChange,
        direction,
        source,
        tvSymbol,
      },
      `Deep fundamentals, valuation, and primary market facts for ${name} (${symbol})`
    )
  }

  return createPortal(
    <div className="fixed inset-0 z-[999] flex items-center justify-center bg-black/85 p-1.5 sm:p-4 backdrop-blur-md animate-in fade-in duration-200">
      <div
        className={cn(
          'relative flex flex-col overflow-hidden rounded-2xl border border-border bg-[#0d0f12] text-foreground shadow-2xl transition-all duration-300',
          isMaximized
            ? 'h-[98vh] w-[99vw] max-w-none'
            : 'h-[94vh] max-h-[880px] min-h-[360px] w-full max-w-7xl'
        )}
      >
        {/* Top Titlebar */}
        <div className="flex shrink-0 items-center justify-between border-b border-border/80 bg-[#12151a] px-3 py-2.5 sm:px-5 sm:py-3 gap-3">
          <div className="flex items-center gap-2 sm:gap-3 min-w-0">
            <div className="flex flex-col min-w-0">
              <div className="flex items-center gap-1.5 sm:gap-2">
                <span className="text-[15px] sm:text-[17px] font-bold tracking-tight text-white truncate">{symbol}</span>
                <span className="rounded-md bg-white/10 px-1.5 sm:px-2 py-0.5 text-[10px] sm:text-[11px] font-medium text-muted-foreground border border-white/5 shrink-0">
                  {assetClass}
                </span>
                <span className="hidden xs:flex items-center gap-1 text-[10px] sm:text-[11px] text-emerald-400 font-medium shrink-0">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" /> Live Market
                </span>
              </div>
              <span className="text-[11px] sm:text-[12px] text-muted-foreground truncate">
                {name} • <span className="font-mono text-[10.5px] sm:text-[11px] text-primary">{tvSymbol}</span>
              </span>
            </div>

            <div className="mx-2 sm:mx-3 hidden sm:block h-7 w-px bg-border/80 shrink-0" />

            {/* Price Badge */}
            <div className="hidden sm:flex flex-col shrink-0">
              <span className="font-mono text-lg sm:text-xl font-bold tracking-tight text-white">{last}</span>
              <div className="flex items-center gap-1.5 text-[11px] font-semibold">
                <span className={cn(isUp ? 'text-emerald-400' : isDown ? 'text-rose-400' : 'text-muted-foreground')}>
                  {change} ({pctChange})
                </span>
              </div>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
            <button
              onClick={handleAskTalvrin}
              className="inline-flex items-center gap-1 sm:gap-1.5 rounded-xl bg-primary px-2.5 sm:px-3 py-1.5 text-[11.5px] sm:text-[12px] font-semibold text-primary-foreground shadow-sm hover:opacity-90 transition active:scale-95"
            >
              <Search className="h-3.5 w-3.5" />
              <span>Research</span>
            </button>

            <button
              onClick={() => setShowSetAlert(true)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-primary/30 bg-primary/10 px-3 py-1.5 text-[12px] font-semibold text-primary hover:bg-primary/20 transition cursor-pointer shadow-xs"
            >
              <Bell className="h-3.5 w-3.5 text-primary" />
              <span>Set Alert</span>
            </button>

            {/* Maximize / Restore Toggle */}
            <button
              onClick={() => setIsMaximized((prev) => !prev)}
              title={isMaximized ? 'Restore normal size' : 'Expand to full screen'}
              aria-label={isMaximized ? 'Restore' : 'Maximize'}
              className="grid h-8 w-8 place-items-center rounded-xl text-muted-foreground hover:bg-accent hover:text-foreground transition"
            >
              {isMaximized ? (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 14h6m0 0v6m0-6L3 21m17-7h-6m0 0v6m0-6l7 7M14 10V4m0 6h6m-6 0l7-7M10 10V4m0 6H4m6 0L3 3" />
                </svg>
              ) : (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-5h-4m4 0v4m0-4l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                </svg>
              )}
            </button>

            <button
              onClick={onClose}
              className="grid h-8 w-8 place-items-center rounded-xl text-muted-foreground hover:bg-accent hover:text-foreground transition"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Toolbar: Timeframe & Engine / Chart Style */}
        <div className="flex shrink-0 items-center justify-between border-b border-border/60 bg-[#0f1217] px-3 py-1.5 sm:px-5 sm:py-2 gap-2 overflow-x-auto scrollbar-none">
          {/* Timeframe Selectors */}
          <div className="flex items-center gap-0.5 sm:gap-1 shrink-0">
            {(['1D', '1W', '1M', '3M', '1Y', '5Y', 'ALL'] as Timeframe[]).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={cn(
                  'rounded-lg px-2 sm:px-2.5 py-1 text-[11px] sm:text-[12px] font-semibold transition',
                  timeframe === tf
                    ? 'bg-primary text-primary-foreground shadow-xs'
                    : 'text-muted-foreground hover:bg-white/5 hover:text-white'
                )}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Style Controls */}
          <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
            {!useTradingViewEmbed ? (
              <div className="flex rounded-lg border border-border/80 bg-background/50 p-0.5 text-[11px]">
                <button
                  onClick={() => setChartMode('candles')}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-md px-2 sm:px-2.5 py-1 font-medium transition text-[11px]',
                    chartMode === 'candles' ? 'bg-primary text-white shadow-xs' : 'text-muted-foreground hover:text-white'
                  )}
                >
                  <CandlestickChart className="h-3 w-3" />
                  <span className="hidden xs:inline">Candlesticks</span>
                </button>
                <button
                  onClick={() => setChartMode('area')}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-md px-2 sm:px-2.5 py-1 font-medium transition text-[11px]',
                    chartMode === 'area' ? 'bg-primary text-white shadow-xs' : 'text-muted-foreground hover:text-white'
                  )}
                >
                  <LineChart className="h-3 w-3" />
                  <span className="hidden xs:inline">Area Line</span>
                </button>
              </div>
            ) : null}

            {/* If asset is non-sovereign, allow toggling between Live TradingView Engine & Native Canvas */}
            {!isSovereign && (
              <button
                onClick={() => setUseTradingViewEmbed((prev) => !prev)}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg border border-border/70 px-2 sm:px-2.5 py-1 text-[11px] font-medium transition',
                  useTradingViewEmbed ? 'bg-blue-600/20 text-blue-400 border-blue-500/30' : 'bg-card/60 text-muted-foreground hover:text-white'
                )}
              >
                <span>{useTradingViewEmbed ? '● TradingView Live' : 'TradingView Live'}</span>
              </button>
            )}

            {/* External link directly to official symbol on TradingView */}
            <a
              href={`https://www.tradingview.com/symbols/${encodeURIComponent(tvSymbol.replace(':', '-'))}/`}
              target="_blank"
              rel="noopener noreferrer"
              className="hidden sm:inline-flex items-center gap-1 rounded-lg border border-border/70 bg-card/60 px-2.5 py-1 text-[11px] font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition"
              title="Open full chart on TradingView.com"
            >
              <span>TV Link</span>
              <ExternalLink className="h-2.5 w-2.5" />
            </a>

            <div className="hidden lg:flex items-center gap-1.5 text-[11px] text-muted-foreground border-l border-border/60 pl-2.5">
              <ShieldCheck className="h-3.5 w-3.5 text-primary" />
              <span className="truncate max-w-[150px]">{source}</span>
            </div>
          </div>
        </div>

        {/* Main Chart Canvas */}
        <div className="relative flex-1 min-h-0 bg-[#090b0e] p-1.5 sm:p-2 select-none overflow-hidden flex flex-col">
          {/* Active Hover Telemetry HUD (Shown when hovering over canvas chart) */}
          {!useTradingViewEmbed && hoverQuote && (
            <div className="absolute left-3 top-3 z-20 flex flex-wrap items-center gap-2 sm:gap-3 rounded-lg border border-border/80 bg-[#12151b]/95 px-2.5 py-1 text-[11px] sm:text-[12px] font-mono shadow-md backdrop-blur-xs">
              <span className="text-muted-foreground">{hoverQuote.time}</span>
              <span>O: <strong className="text-white">{hoverQuote.open}</strong></span>
              <span>H: <strong className="text-white">{hoverQuote.high}</strong></span>
              <span>L: <strong className="text-white">{hoverQuote.low}</strong></span>
              <span>C: <strong className="text-white">{hoverQuote.close}</strong></span>
              <span className="text-muted-foreground/80 hidden sm:inline">Vol: {hoverQuote.volume.toLocaleString()}</span>
            </div>
          )}

          <div className="relative h-full w-full min-h-0 flex-1">
            {useTradingViewEmbed && !isSovereign ? (
              <TradingViewWidget
                symbol={symbol}
                theme="dark"
                interval={timeframe === '1D' ? '60' : timeframe === '1W' ? 'D' : 'D'}
                onFallbackToNative={() => setUseTradingViewEmbed(false)}
              />
            ) : (
              <InstitutionalChart
                symbol={symbol}
                baseValueStr={last}
                timeframe={timeframe}
                chartMode={chartMode}
                onHoverQuote={setHoverQuote}
              />
            )}
          </div>
        </div>

        {/* Footer Meta Details */}
        <div className="flex shrink-0 items-center justify-between border-t border-border/80 bg-[#12151a] px-3 py-2 sm:px-5 sm:py-2.5 text-[11px] sm:text-[12px] text-muted-foreground gap-3">
          <div className="flex items-center gap-2 sm:gap-4 truncate">
            <span className="flex items-center gap-1.5 shrink-0">
              <Clock className="h-3.5 w-3.5 text-primary" />
              <span>As of: {freshness}</span>
            </span>
            <span className="hidden sm:inline">•</span>
            <span className="text-white font-medium truncate">Bitemporal state: {bitemporalStatus}</span>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <span className="hidden sm:inline">Authoritative Source:</span>
            <span className="font-semibold text-white">{source}</span>
          </div>
        </div>
      </div>

      {showSetAlert && (
        <SetAlertModal
          symbol={symbol}
          name={name}
          currentPrice={last}
          onClose={() => setShowSetAlert(false)}
          onAlertCreated={(created) => {
            toast.success(`Alert armed for ${created.assetSymbol} at ${created.threshold}`)
          }}
        />
      )}
    </div>,
    document.body
  )
}
