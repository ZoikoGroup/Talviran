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
  AlertTriangle,
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

// Maps each timeframe button to TradingView's own `range` (the visible
// history window - '1D','5D','1M','3M','12M','60M','ALL' are its actual
// date-range-selector values; it has no native '1W'/'1Y'/'5Y' spelling) and
// a matching bar `interval`. Previously only `interval` was set, and it
// collapsed to 'D' for every timeframe except '1D' - so every button past
// "1D" sent an identical config and TradingView just showed its own
// default history window regardless of which button was clicked. Live
// Playwright-verified across all 7 buttons before relying on this mapping.
const TIMEFRAME_TO_TV: Record<Timeframe, { range: string; interval: string }> = {
  '1D': { range: '1D', interval: '5' },
  '1W': { range: '5D', interval: '30' },
  '1M': { range: '1M', interval: '60' },
  '3M': { range: '3M', interval: '120' },
  '1Y': { range: '12M', interval: 'D' },
  '5Y': { range: '60M', interval: 'W' },
  ALL: { range: 'ALL', interval: 'M' },
}

// Sovereign yield-curve points (this app's only real SOVEREIGN-class
// instruments: UK Gilts, US Treasuries) are served through a synthetic
// TVC vendor symbol (TVC:GB10Y etc.), not a tradable security with real
// intraday ticks. Live-verified: TradingView's embed rejects this symbol
// type outright - "This symbol is only available on TradingView" -
// whenever ANY date-range feature is requested (the `range` config key,
// or even just `withdateranges: true`), and separately rejects any
// interval finer than daily. Only `interval: 'D'` with no range-related
// key at all resolves successfully. There is no TradingView-side window
// to change for this instrument, so the timeframe buttons are disabled
// for it below rather than presented as functional when they can't do
// anything - the same vendor-data symptom likely explains the "Apple
// Inc" legend seen under a "UK 10Y Gilt" header: TradingView's own
// broken-symbol dialog offers a "Change symbol" escape hatch, which (pre
// allow_symbol_change:false) a user or a stray interaction could have
// clicked through to land on an unrelated instrument.
const YIELD_CURVE_ASSET_CLASSES = new Set(['SOVEREIGN'])

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
  // TradingView's embed genuinely covers sovereign yields too (TVC:GB10Y
  // etc. - see mapToTradingViewSymbol), so there is no real reason to force
  // every sovereign instrument onto the fabricated native chart - that was
  // the core of the G06 chart-integrity defect (2026-11-10 UAT gap
  // analysis remediation): real TradingView is now the default for every
  // instrument, and the native canvas survives only as an explicitly
  // labeled, dev-only fallback.
  const [timeframe, setTimeframe] = useState<Timeframe>('1M')
  const [chartMode, setChartMode] = useState<ChartMode>('candles')
  const [useTradingViewEmbed, setUseTradingViewEmbed] = useState(true)
  const [chartUnavailable, setChartUnavailable] = useState(false)
  const [isMaximized, setIsMaximized] = useState(false)
  const [hoverQuote, setHoverQuote] = useState<HoverQuote | null>(null)
  const [showSetAlert, setShowSetAlert] = useState(false)
  const isProdBuild = import.meta.env.PROD

  const isUp = direction === 'up'
  const isDown = direction === 'down'
  const tvSymbol = mapToTradingViewSymbol(symbol)
  const isYieldCurveAsset = YIELD_CURVE_ASSET_CLASSES.has(assetClass)
  const tvChartConfig = isYieldCurveAsset
    ? { interval: 'D', range: undefined }
    : TIMEFRAME_TO_TV[timeframe]

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
        <div className="flex shrink-0 items-center justify-between border-b border-border/80 bg-[#12151a] px-3 py-2.5 sm:px-5 sm:py-3 gap-2 sm:gap-3">
          <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-1">
            <div className="flex flex-col min-w-0 flex-1">
              <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
                <span className="text-[14px] sm:text-[17px] font-bold tracking-tight text-white truncate min-w-0 max-w-[120px] xs:max-w-[200px] sm:max-w-none">{symbol}</span>
                <span className="rounded-md bg-white/10 px-1.5 sm:px-2 py-0.5 text-[9.5px] sm:text-[11px] font-medium text-muted-foreground border border-white/5 shrink-0">
                  {assetClass}
                </span>
                <span className="hidden xs:flex items-center gap-1 text-[10px] sm:text-[11px] text-emerald-400 font-medium shrink-0">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" /> Live Market
                </span>
              </div>
              <span className="text-[10.5px] sm:text-[12px] text-muted-foreground truncate min-w-0">
                {name} • <span className="font-mono text-[10px] sm:text-[11px] text-primary">{tvSymbol}</span>
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
              aria-label="Close chart"
              className="grid h-8 w-8 place-items-center rounded-xl text-muted-foreground hover:bg-accent hover:text-foreground transition"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Toolbar: Timeframe & Engine / Chart Style */}
        <div className="flex shrink-0 items-center justify-between border-b border-border/60 bg-[#0f1217] px-3 py-1.5 sm:px-5 sm:py-2 gap-2 overflow-x-auto scrollbar-none">
          {/* Timeframe Selectors - no chart is rendered at all for
              sovereign yield-curve instruments (see the Main Chart Canvas
              branch below), so there's nothing for these to control. */}
          {!isYieldCurveAsset && (
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
          )}

          {/* Style Controls */}
          <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
            {!useTradingViewEmbed ? (
              <div className="flex rounded-lg border border-border/80 bg-background/50 p-0.5 text-[11px]">
                <button
                  onClick={() => setChartMode('candles')}
                  aria-label="Switch to candlestick chart style"
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
                  aria-label="Switch to area line chart style"
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

            {/* Dev-only: let an engineer compare against the simulated native
                canvas. There is no legitimate reason to offer this switch in
                production - TradingView is the only real chart source. Never
                shown for yield-curve assets either - "TradingView Live"
                would be false for an instrument we never attempt to embed. */}
            {!isProdBuild && !chartUnavailable && !isYieldCurveAsset && (
              <button
                onClick={() => setUseTradingViewEmbed((prev) => !prev)}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg border border-border/70 px-2 sm:px-2.5 py-1 text-[11px] font-medium transition',
                  useTradingViewEmbed ? 'bg-blue-600/20 text-blue-400 border-blue-500/30' : 'bg-card/60 text-muted-foreground hover:text-white'
                )}
              >
                <span>{useTradingViewEmbed ? '● TradingView Live' : 'Simulated (dev only)'}</span>
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
            {isYieldCurveAsset ? (
              // Live-verified (repeatedly, across fresh sessions): TradingView's
              // Advanced Chart embed never resolves this symbol family
              // (TVC:GB10Y, TVC:US10Y - this app's only two real
              // SOVEREIGN-class instruments), in any interval/range
              // combination - it's a permanent vendor/widget limitation, not
              // a transient outage, so a "Retry" would be misleading. Worse,
              // dismissing TradingView's own "symbol not available" dialog
              // makes the widget silently fall back to ITS OWN demo symbol
              // (Apple Inc) with no visible error at all - confirmed as the
              // actual cause of an "Apple Inc" chart legend seen under a
              // "UK 10Y Gilt" header. Never attempting the embed for this
              // asset class closes that off entirely rather than racing it.
              <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-center px-6">
                <AlertTriangle className="h-6 w-6 text-amber-400" />
                <span className="text-[13px] font-semibold text-white">No chart feed available for this instrument</span>
                <span className="max-w-sm text-[11.5px] text-muted-foreground">
                  TradingView doesn&apos;t carry a working live chart for {symbol} as a sovereign
                  yield instrument. The yield figure above and its history are still real,
                  sourced facts from {source} - just not chartable via this embed.
                </span>
              </div>
            ) : chartUnavailable ? (
              <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-center">
                <AlertTriangle className="h-6 w-6 text-amber-400" />
                <span className="text-[13px] font-semibold text-white">Chart data unavailable</span>
                <span className="max-w-xs text-[11.5px] text-muted-foreground">
                  Talvrin couldn&apos;t reach the live TradingView feed for {symbol}. No historical
                  chart is shown rather than an invented one.
                </span>
                <button
                  type="button"
                  onClick={() => setChartUnavailable(false)}
                  className="mt-1 rounded-lg border border-border/70 bg-card/60 px-2.5 py-1 text-[11px] font-medium text-muted-foreground hover:text-white transition"
                >
                  Retry
                </button>
              </div>
            ) : useTradingViewEmbed ? (
              <TradingViewWidget
                // Force a full remount (fresh DOM container) per symbol -
                // TradingView's external embed script manages its own iframe
                // outside React's control and (per TradingView's own docs)
                // requires re-initializing the whole widget on any change,
                // not just a prop/attribute update. Without this key, the
                // chart could keep showing a PREVIOUS instrument's real data
                // under a NEW instrument's header - confirmed reproducible
                // via HomeDashboard.tsx's search box: handleSearchSubmit
                // never blurs it after a selection, so it keeps keyboard
                // focus underneath this modal's full-screen overlay: typing
                // a second query and pressing Enter again calls
                // handleSelectAsset -> setSelectedAssetForChart on the SAME
                // mounted modal instance, swapping `symbol` without ever
                // unmounting - a real-data mislabeling bug, not a
                // fabrication one, but just as misleading.
                key={symbol}
                symbol={symbol}
                theme="dark"
                interval={tvChartConfig.interval}
                range={tvChartConfig.range}
                onFallbackToNative={isProdBuild ? undefined : () => setUseTradingViewEmbed(false)}
                onTimeout={isProdBuild ? () => setChartUnavailable(true) : undefined}
              />
            ) : (
              <div className="relative h-full w-full">
                {/* Never shown in production - see the toggle button above,
                    which is itself hidden outside dev. */}
                <div className="absolute left-1/2 top-3 z-20 -translate-x-1/2 rounded-full border border-amber-500/40 bg-amber-500/15 px-3 py-1 text-[10.5px] font-semibold tracking-wide text-amber-300">
                  SIMULATED CHART — DEVELOPMENT ONLY, NOT REAL MARKET DATA
                </div>
                <InstitutionalChart
                  symbol={symbol}
                  baseValueStr={last}
                  timeframe={timeframe}
                  chartMode={chartMode}
                  onHoverQuote={setHoverQuote}
                />
              </div>
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
            <span className="hidden sm:inline">
              {bitemporalStatus === 'UNVERIFIED' ? 'Data Source:' : 'Authoritative Source:'}
            </span>
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
