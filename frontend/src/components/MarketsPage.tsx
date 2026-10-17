import { useEffect, useState, useMemo } from 'react'
import {
  Globe2,
  ArrowLeft,
  Search,
  Plus,
  Bookmark,
  Check,
  TrendingUp,
  TrendingDown,
  ShieldCheck,
  ChevronDown,
  Layers,
  BarChart2,
  RefreshCw,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  listWatchlists,
  addWatchlistItem,
  type Watchlist,
  triggerExternalSync,
  getLiveSyncedAssets,
} from '@/lib/api'
import TradingViewModal from '@/components/TradingViewModal'
import TradingViewScreener from '@/components/TradingViewScreener'
import type { TaggedAsset } from '@/data/mockReply'

interface MarketsPageProps {
  initialSymbol?: string | null
  onBack?: () => void
  onStartResearch: (assetOrQuery: string | TaggedAsset, prompt?: string) => void
  onOpenMonitoringForRule?: (symbol: string) => void
  onOpenWatchlists?: () => void
}

export { GLOBAL_MARKET_ASSETS, type MarketAsset } from '@/data/globalAssets'
import { GLOBAL_MARKET_ASSETS, type MarketAsset } from '@/data/globalAssets'

function MiniSparkline({ data, direction }: { data: number[]; direction: 'up' | 'down' | 'flat' }) {
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const width = 80
  const height = 24

  const points = data
    .map((val, i) => {
      const x = (i / (data.length - 1)) * width
      const y = height - ((val - min) / range) * (height - 6) - 3
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

  const strokeColor =
    direction === 'up' ? '#10b981' : direction === 'down' ? '#f43f5e' : '#94a3b8'

  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  )
}

export default function MarketsPage({
  initialSymbol,
  onBack,
  onStartResearch,
  onOpenMonitoringForRule,
  onOpenWatchlists,
}: MarketsPageProps) {
  const [activeTab, setActiveTab] = useState<'ALL' | 'SOVEREIGN' | 'EQUITY' | 'ETF' | 'FX' | 'COMMODITIES' | 'CRYPTO' | 'MACRO' | 'IPO' | 'MUTUAL_FUND'>('ALL')
  const [activeRegion, setActiveRegion] = useState<'ALL' | 'UK' | 'US' | 'EU' | 'APAC'>('ALL')
  const [activeSource, setActiveSource] = useState<string>('ALL')
  const [viewMode, setViewMode] = useState<'table' | 'screener'>('table')
  const [search, setSearch] = useState('')
  const [watchlists, setWatchlists] = useState<Watchlist[]>([])
  const [addedItemSymbol, setAddedItemSymbol] = useState<string | null>(null)
  const [activeDropdownSymbol, setActiveDropdownSymbol] = useState<string | null>(null)
  const [selectedAsset, setSelectedAsset] = useState<MarketAsset | null>(null)
  const [dynamicSyncedAssets, setDynamicSyncedAssets] = useState<MarketAsset[]>([])
  const [isSyncing, setIsSyncing] = useState(false)
  const [lastSyncTime, setLastSyncTime] = useState<string | null>(null)

  useEffect(() => {
    void listWatchlists().then(setWatchlists).catch(() => {})
    // Auto-fetch any dynamically ingested assets
    void getLiveSyncedAssets().then((items) => {
      if (items && items.length > 0) {
        setDynamicSyncedAssets(
          items.map((i) => ({
            symbol: i.symbol,
            name: i.name,
            assetClass: (i.asset_class as MarketAsset['assetClass']) || 'EQUITY',
            region: 'GLOBAL',
            price: i.price,
            change: '+0.00',
            pctChange: '+0.00%',
            direction: 'flat' as const,
            sparkline: [100, 101, 102, 102, 103],
            source: i.source,
            freshness: i.freshness,
            bitemporalStatus: i.bitemporal_status,
          }))
        )
      }
    }).catch(() => {})
  }, [])

  const handleTriggerSync = async () => {
    try {
      setIsSyncing(true)
      const res = await triggerExternalSync('all', 50)
      if (res && res.assets) {
        setDynamicSyncedAssets(
          res.assets.map((i) => ({
            symbol: i.symbol,
            name: i.name,
            assetClass: (i.asset_class as MarketAsset['assetClass']) || 'EQUITY',
            region: 'GLOBAL',
            price: i.price,
            change: '+0.00',
            pctChange: '+0.00%',
            direction: 'flat' as const,
            sparkline: [100, 101, 102, 102, 103],
            source: i.source,
            freshness: i.freshness,
            bitemporalStatus: i.bitemporal_status,
          }))
        )
        setLastSyncTime(new Date().toLocaleTimeString())
      }
    } catch {
      // Graceful fallback
    } finally {
      setIsSyncing(false)
    }
  }

  const allAssets = useMemo(() => {
    const existingSymbols = new Set(GLOBAL_MARKET_ASSETS.map((a) => a.symbol.toUpperCase()))
    const newItems = dynamicSyncedAssets.filter((a) => !existingSymbols.has(a.symbol.toUpperCase()))
    return [...newItems, ...GLOBAL_MARKET_ASSETS]
  }, [dynamicSyncedAssets])

  // Auto-open modal if initialSymbol was provided
  useEffect(() => {
    if (!initialSymbol) return
    const match = allAssets.find(
      (a) =>
        a.symbol.toLowerCase() === initialSymbol.toLowerCase() ||
        a.name.toLowerCase().includes(initialSymbol.toLowerCase())
    )
    if (match) {
      setSelectedAsset(match)
      if (match.assetClass) setActiveTab(match.assetClass)
    }
  }, [initialSymbol, allAssets])

  const assetCounts = useMemo(() => {
    const counts: Record<string, number> = {
      ALL: allAssets.length,
      SOVEREIGN: 0,
      EQUITY: 0,
      ETF: 0,
      COMMODITIES: 0,
      FX: 0,
      CRYPTO: 0,
      MACRO: 0,
      IPO: 0,
      MUTUAL_FUND: 0,
    }
    for (const a of allAssets) {
      if (counts[a.assetClass] !== undefined) {
        counts[a.assetClass]++
      }
    }
    return counts
  }, [allAssets])

  const tabs = [
    { id: 'ALL' as const, label: 'All Assets', count: assetCounts.ALL },
    { id: 'SOVEREIGN' as const, label: 'Sovereign Debt', count: assetCounts.SOVEREIGN },
    { id: 'EQUITY' as const, label: 'Equities & Indices', count: assetCounts.EQUITY },
    { id: 'IPO' as const, label: 'IPOs & Issues', count: assetCounts.IPO },
    { id: 'MUTUAL_FUND' as const, label: 'Mutual Funds', count: assetCounts.MUTUAL_FUND },
    { id: 'ETF' as const, label: 'ETFs & Index Funds', count: assetCounts.ETF },
    { id: 'COMMODITIES' as const, label: 'Commodities', count: assetCounts.COMMODITIES },
    { id: 'FX' as const, label: 'Foreign Exchange', count: assetCounts.FX },
    { id: 'CRYPTO' as const, label: 'Crypto (CMC)', count: assetCounts.CRYPTO },
    { id: 'MACRO' as const, label: 'Macro & Policy', count: assetCounts.MACRO },
  ]

  const filteredAssets = useMemo(() => {
    return allAssets.filter((a) => {
      if (search.trim()) {
        const q = search.toLowerCase()
        const matchesQuery = a.symbol.toLowerCase().includes(q) || a.name.toLowerCase().includes(q) || a.source.toLowerCase().includes(q)
        if (!matchesQuery) return false
      }
      if (activeTab !== 'ALL' && a.assetClass !== activeTab) return false
      if (activeRegion !== 'ALL' && a.region !== activeRegion && a.region !== 'GLOBAL') return false
      if (activeSource !== 'ALL') {
        const s = a.source.toLowerCase()
        if (activeSource === 'TradingView' && !s.includes('tradingview')) return false
        if (activeSource === 'CoinMarketCap' && !s.includes('coinmarketcap')) return false
        if (activeSource === 'Primary Exchanges' && !['nasdaq', 'nyse', 'london stock exchange', 'bombay stock exchange', 'national stock exchange', 'deutsche', 'euronext', 'hkex', 'tokyo stock exchange', 'six swiss', 'asx', 'krx', 'cboe', 'sp dow jones'].some(ex => s.includes(ex))) return false
        if (activeSource === 'Commodities' && !['lbma', 'cme', 'ice', 'nymex', 'comex', 'cbot'].some(c => s.includes(c))) return false
        if (activeSource === 'Central Banks' && !['bank of england', 'federal reserve', 'deutsche bundesbank', 'ministry of finance japan', 'bank of japan', 'reserve bank of india', 'ecb', 'ons', 'bls', 'swiss national bank', 'reserve bank of australia', 'bank of canada', 'people\'s bank of china', 'eurostat', 'mospi', 'treasury', 'dmo'].some(cb => s.includes(cb))) return false
      }
      return true
    })
  }, [allAssets, activeTab, activeRegion, activeSource, search])

  const handleAddToWatchlist = async (watchlistId: string, asset: MarketAsset) => {
    try {
      await addWatchlistItem(watchlistId, {
        symbol: asset.symbol,
        name: asset.name,
        assetClass: asset.assetClass,
      })
      setAddedItemSymbol(asset.symbol)
      setActiveDropdownSymbol(null)
      setTimeout(() => setAddedItemSymbol(null), 2500)
    } catch (err) {
      console.error(err)
    }
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-background p-6 md:p-8">
      {/* Header */}
      <div className="mx-auto flex w-full max-w-7xl items-start justify-between gap-4 pb-6 border-b border-border">
        <div>
          <div className="flex items-center gap-2.5">
            {onBack && (
              <button
                onClick={onBack}
                aria-label="Back"
                className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground mr-1"
              >
                <ArrowLeft className="h-[18px] w-[18px]" />
              </button>
            )}
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary border border-primary/20">
              <Globe2 className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-foreground sm:text-2xl">
                Global Markets Coverage
              </h1>
              <p className="text-[13px] text-muted-foreground">
                Trusted multi-asset coverage powered by TradingView, CoinMarketCap, Primary Exchanges (NYSE, NASDAQ, LSE, BSE, NSE), Commodities (LBMA, CME), and Central Banks.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* View Switch: Curated Table vs Full World Screener */}
          <div className="flex items-center rounded-xl border border-border bg-card/80 p-1 text-xs">
            <button
              onClick={() => setViewMode('table')}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium transition',
                viewMode === 'table'
                  ? 'bg-primary text-primary-foreground font-semibold shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <BarChart2 className="h-3.5 w-3.5" />
              <span>Benchmarks Table</span>
            </button>
            <button
              onClick={() => setViewMode('screener')}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium transition',
                viewMode === 'screener'
                  ? 'bg-primary text-primary-foreground font-semibold shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <Layers className="h-3.5 w-3.5" />
              <span>World Screener (All Stocks)</span>
            </button>
          </div>

          <button
            onClick={handleTriggerSync}
            disabled={isSyncing}
            className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-card px-3.5 py-2 text-[13px] font-semibold text-foreground shadow-sm hover:bg-accent transition disabled:opacity-50"
            title="Auto-sync new assets from TwelveData, AMFI, and TradingView"
          >
            <RefreshCw className={cn("h-4 w-4 text-primary", isSyncing && "animate-spin")} />
            <span>{isSyncing ? "Syncing..." : lastSyncTime ? `Synced (${lastSyncTime})` : "Live Provider Sync"}</span>
          </button>

          {onOpenWatchlists && (
            <button
              onClick={onOpenWatchlists}
              className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-card px-3.5 py-2 text-[13px] font-semibold text-foreground shadow-sm hover:bg-accent transition"
            >
              <Bookmark className="h-4 w-4 text-primary" />
              <span>Open Watchlists</span>
            </button>
          )}
        </div>
      </div>

      <div className="mx-auto mt-6 flex w-full max-w-7xl flex-1 flex-col gap-6">
        {/* Filter and Search Bar */}
        {/* Filter and Search Bar */}
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-card/60 p-4">
          <div className="flex flex-wrap items-center gap-2">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id)
                  if (viewMode !== 'table') setViewMode('table')
                }}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium transition cursor-pointer',
                  activeTab === tab.id
                    ? 'bg-primary text-primary-foreground font-semibold shadow-xs'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                )}
              >
                <span>{tab.label}</span>
                <span
                  className={cn(
                    'rounded-full px-1.5 py-0.2 text-[10.5px] font-semibold tabular-nums',
                    activeTab === tab.id
                      ? 'bg-primary-foreground/20 text-primary-foreground'
                      : 'bg-muted text-muted-foreground'
                  )}
                >
                  {tab.count}
                </span>
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* View Mode Quick Switcher in Filter Bar */}
            <div className="flex items-center rounded-lg border border-border bg-background p-0.5 text-[11.5px]">
              <button
                onClick={() => setViewMode('table')}
                className={cn(
                  'inline-flex items-center gap-1 rounded-md px-2.5 py-1 font-medium transition cursor-pointer',
                  viewMode === 'table' ? 'bg-primary text-primary-foreground font-semibold shadow-xs' : 'text-muted-foreground hover:text-foreground'
                )}
              >
                <BarChart2 className="h-3 w-3" />
                <span>Benchmarks</span>
              </button>
              <button
                onClick={() => setViewMode('screener')}
                className={cn(
                  'inline-flex items-center gap-1 rounded-md px-2.5 py-1 font-medium transition cursor-pointer',
                  viewMode === 'screener' ? 'bg-primary text-primary-foreground font-semibold shadow-xs' : 'text-muted-foreground hover:text-foreground'
                )}
              >
                <Layers className="h-3 w-3" />
                <span>World Screener</span>
              </button>
            </div>

            <div className="flex items-center gap-1 rounded-lg border border-border bg-background p-0.5 text-[11.5px]">
              {(['ALL', 'UK', 'US', 'EU', 'APAC'] as const).map((reg) => (
                <button
                  key={reg}
                  onClick={() => setActiveRegion(reg)}
                  className={cn(
                    'rounded-md px-2 py-0.5 font-medium transition',
                    activeRegion === reg ? 'bg-primary/15 text-primary font-semibold' : 'text-muted-foreground hover:text-foreground'
                  )}
                >
                  {reg}
                </button>
              ))}
            </div>

            <select
              value={activeSource}
              onChange={(e) => setActiveSource(e.target.value)}
              className="h-8 rounded-lg border border-border bg-background px-2.5 text-[12px] font-medium text-muted-foreground outline-none hover:text-foreground cursor-pointer focus:ring-1 focus:ring-primary"
            >
              <option value="ALL">All Sources (Global)</option>
              <option value="TradingView">TradingView</option>
              <option value="CoinMarketCap">CoinMarketCap</option>
              <option value="Primary Exchanges">Primary Exchanges</option>
              <option value="Commodities">Commodities (LBMA/CME/ICE)</option>
              <option value="Central Banks">Central Banks & Treasury</option>
            </select>

            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search markets or sources..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-8 w-48 rounded-lg border border-border bg-background pl-8 pr-3 text-[12.5px] text-foreground placeholder:text-muted-foreground/70 focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>
        </div>

        {viewMode === 'screener' ? (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between rounded-xl border border-border bg-card/60 px-4 py-3 text-xs text-muted-foreground gap-2">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-foreground">Global Screener Coverage:</span>
                <span>All US, UK, European & International Equities with Real-Time Volume, P/E, Highs, Lows, and Technical Signals.</span>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setViewMode('table')}
                  className="rounded-lg bg-primary/15 border border-primary/30 px-2.5 py-1 text-primary hover:bg-primary hover:text-primary-foreground font-semibold text-[11.5px] flex items-center gap-1 transition cursor-pointer"
                >
                  <BarChart2 className="h-3 w-3" />
                  <span>&larr; Switch to Benchmarks Table ({GLOBAL_MARKET_ASSETS.length})</span>
                </button>
                <span className="text-[11px] text-muted-foreground hidden sm:inline">TradingView Engine</span>
              </div>
            </div>
            <TradingViewScreener
              initialMarket={activeRegion === 'UK' ? 'uk' : activeRegion === 'EU' ? 'germany' : activeRegion === 'APAC' ? 'india' : 'america'}
              height={700}
              colorTheme="dark"
              onStartResearch={onStartResearch}
            />
          </div>
        ) : (
          /* Global Market Data Table */
          <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-muted/20 px-4 py-2.5 text-xs text-muted-foreground">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-foreground">Showing {filteredAssets.length} of {GLOBAL_MARKET_ASSETS.length} Curated Benchmarks</span>
                <span>• Live TradingView, CoinMarketCap & Primary Exchange feeds</span>
              </div>
              <button
                onClick={() => setViewMode('screener')}
                className="text-primary hover:underline font-medium text-[11.5px] flex items-center gap-1 transition"
              >
                <span>Need 10,000+ international equities? Switch to World Screener &rarr;</span>
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[13px]">
                <thead className="border-b border-border bg-muted/40 text-[11.5px] font-medium uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="py-3 pl-4 pr-3">Instrument</th>
                    <th className="px-3 py-3">Class / Region</th>
                    <th className="px-3 py-3 text-right">Price / Yield</th>
                    <th className="px-3 py-3 text-right">Net Chg</th>
                    <th className="px-3 py-3 text-right">% Chg</th>
                    <th className="px-3 py-3 text-center">Trend (7D)</th>
                    <th className="px-3 py-3">Data Origin</th>
                    <th className="py-3 pl-3 pr-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {filteredAssets.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-12 text-center text-muted-foreground">
                        <div className="flex flex-col items-center justify-center gap-3">
                          <span>No pre-configured benchmark matching "{search}"</span>
                          {search.trim().length > 1 && (
                            <div className="flex flex-wrap items-center justify-center gap-2">
                              <button
                                onClick={() => {
                                  const customTicker = search.trim().toUpperCase()
                                  onStartResearch({
                                    symbol: customTicker,
                                    name: customTicker === 'BSE' ? 'Bombay Stock Exchange (BSE)' : `${customTicker} Market Asset`,
                                    assetClass: 'EQUITY',
                                    source: 'Primary Market',
                                  })
                                }}
                                className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-[12px] font-semibold text-primary-foreground shadow-sm hover:opacity-90 transition active:scale-95"
                              >
                                <Search className="h-4 w-4" />
                                <span>Research: "{search}"</span>
                              </button>

                              <button
                                onClick={() => {
                                  const customTicker = search.trim().toUpperCase()
                                  setSelectedAsset({
                                    symbol: customTicker,
                                    name: `${customTicker} Global Market Instrument`,
                                    assetClass: 'EQUITY',
                                    region: 'GLOBAL',
                                    price: 'Live',
                                    change: '0.00',
                                    pctChange: '0.00%',
                                    direction: 'flat',
                                    sparkline: [100, 101, 100.5, 102],
                                    source: 'Global Exchange / TradingView',
                                    freshness: 'Real-time',
                                    bitemporalStatus: 'LIVE_FEED',
                                  })
                                }}
                                className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-card px-3.5 py-2 text-[12px] font-medium text-foreground hover:bg-accent transition active:scale-95"
                              >
                                <Globe2 className="h-4 w-4 text-muted-foreground" />
                                <span>Open live chart</span>
                              </button>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  ) : (
                    filteredAssets.map((asset) => {
                      const isUp = asset.direction === 'up'
                      const isDown = asset.direction === 'down'
                      const isAdded = addedItemSymbol === asset.symbol

                      return (
                        <tr
                          key={asset.symbol}
                          onClick={() => setSelectedAsset(asset)}
                          className="group cursor-pointer transition-colors hover:bg-accent/40"
                        >
                          {/* Instrument */}
                          <td className="py-3.5 pl-4 pr-3">
                            <div className="flex flex-col">
                              <span className="font-semibold text-foreground group-hover:text-primary transition-colors flex items-center gap-1.5">
                                {asset.symbol}
                                <span className="opacity-0 group-hover:opacity-100 text-[10px] text-primary transition font-normal bg-primary/10 px-1 rounded">
                                  View Chart
                                </span>
                              </span>
                              <span className="text-[11.5px] text-muted-foreground">
                                {asset.name}
                              </span>
                            </div>
                          </td>

                          {/* Class & Region */}
                          <td className="px-3 py-3.5">
                            <div className="flex items-center gap-1.5">
                              <span className="rounded-md bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground border border-border/70">
                                {asset.assetClass}
                              </span>
                              <span className="rounded-md bg-primary/10 px-1.5 py-0.5 text-[10.5px] font-semibold text-primary">
                                {asset.region}
                              </span>
                            </div>
                          </td>

                          {/* Price / Yield */}
                          <td className="px-3 py-3.5 text-right font-mono font-semibold text-foreground">
                            {asset.price}
                          </td>

                          {/* Net Change */}
                          <td
                            className={cn(
                              'px-3 py-3.5 text-right font-mono text-[12.5px] font-medium',
                              isUp ? 'text-emerald-500' : isDown ? 'text-rose-500' : 'text-muted-foreground'
                            )}
                          >
                            {asset.change}
                          </td>

                          {/* % Change Pill */}
                          <td className="px-3 py-3.5 text-right font-mono">
                            <span
                              className={cn(
                                'inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-[11px] font-semibold',
                                isUp
                                  ? 'bg-emerald-500/15 text-emerald-500'
                                  : isDown
                                  ? 'bg-rose-500/15 text-rose-500'
                                  : 'bg-muted text-muted-foreground'
                              )}
                            >
                              {isUp && <TrendingUp className="h-3 w-3" />}
                              {isDown && <TrendingDown className="h-3 w-3" />}
                              {asset.pctChange}
                            </span>
                          </td>

                          {/* Trend */}
                          <td className="px-3 py-3.5 text-center">
                            <div className="inline-flex justify-center">
                              <MiniSparkline data={asset.sparkline} direction={asset.direction} />
                            </div>
                          </td>

                          {/* Source */}
                          <td className="px-3 py-3.5">
                            <div className="flex flex-col">
                              <span className="text-[12px] font-medium text-foreground flex items-center gap-1">
                                <ShieldCheck className="h-3 w-3 text-primary" />
                                {asset.source}
                              </span>
                              <span className="text-[11px] text-muted-foreground">
                                {asset.freshness} • {asset.bitemporalStatus}
                              </span>
                            </div>
                          </td>

                          {/* Actions */}
                          <td className="py-3.5 pl-3 pr-4 text-right">
                            <div
                              onClick={(e) => e.stopPropagation()}
                              className="relative flex items-center justify-end gap-1.5"
                            >
                              <button
                                onClick={() =>
                                  onStartResearch({
                                    symbol: asset.symbol,
                                    name: asset.name,
                                    assetClass: asset.assetClass,
                                    price: asset.price,
                                    change: asset.change,
                                    pctChange: asset.pctChange,
                                    direction: asset.direction,
                                    source: asset.source,
                                  })
                                }
                                title="Research Asset"
                                className="inline-flex items-center gap-1 rounded-lg border border-border bg-secondary/60 px-2.5 py-1 text-[11.5px] font-semibold text-foreground hover:bg-primary hover:text-primary-foreground hover:border-primary transition shadow-xs"
                              >
                                <Search className="h-3 w-3" />
                                <span>Research</span>
                              </button>

                              {/* Add to Watchlist Dropdown Trigger */}
                              <div className="relative">
                                <button
                                  onClick={() =>
                                    setActiveDropdownSymbol(
                                      activeDropdownSymbol === asset.symbol ? null : asset.symbol
                                    )
                                  }
                                  title="Add to Watchlist"
                                  className={cn(
                                    'inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-[11.5px] font-medium transition',
                                    isAdded
                                      ? 'border-emerald-500/50 bg-emerald-500/15 text-emerald-400'
                                      : 'border-border bg-card text-foreground hover:bg-accent'
                                  )}
                                >
                                  {isAdded ? (
                                    <>
                                      <Check className="h-3 w-3" />
                                      <span>Added!</span>
                                    </>
                                  ) : (
                                    <>
                                      <Plus className="h-3 w-3" />
                                      <span>Watchlist</span>
                                      <ChevronDown className="h-3 w-3 opacity-60" />
                                    </>
                                  )}
                                </button>

                                {/* Watchlist Selection Menu */}
                                {activeDropdownSymbol === asset.symbol && (
                                  <div className="absolute right-0 top-full z-30 mt-1 w-52 rounded-xl border border-border bg-[#12151c] p-1.5 shadow-xl text-left animate-in fade-in zoom-in-95">
                                    <div className="px-2 py-1 text-[11px] font-medium text-muted-foreground border-b border-border/60">
                                      Select Target Watchlist
                                    </div>
                                    <div className="mt-1 space-y-0.5 max-h-48 overflow-y-auto">
                                      {watchlists.length === 0 ? (
                                        <div className="px-2 py-2 text-xs text-muted-foreground">
                                          No watchlists found.
                                        </div>
                                      ) : (
                                        watchlists.map((wl) => (
                                          <button
                                            key={wl.id}
                                            onClick={() => handleAddToWatchlist(wl.id, asset)}
                                            className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-[12px] text-foreground hover:bg-white/10 transition text-left"
                                          >
                                            <span className="truncate">{wl.name}</span>
                                            <Bookmark className="h-3 w-3 opacity-50 shrink-0" />
                                          </button>
                                        ))
                                      )}
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* TradingView Charting Modal on Selected Asset */}
      {selectedAsset && (
        <TradingViewModal
          symbol={selectedAsset.symbol}
          name={selectedAsset.name}
          assetClass={selectedAsset.assetClass}
          last={selectedAsset.price}
          change={selectedAsset.change}
          pctChange={selectedAsset.pctChange}
          direction={selectedAsset.direction}
          source={selectedAsset.source}
          freshness={selectedAsset.freshness}
          bitemporalStatus={selectedAsset.bitemporalStatus}
          onClose={() => setSelectedAsset(null)}
          onStartResearch={(asset) => {
            setSelectedAsset(null)
            onStartResearch(asset)
          }}
          onOpenMonitoring={(sym) => {
            setSelectedAsset(null)
            if (onOpenMonitoringForRule) onOpenMonitoringForRule(sym)
          }}
        />
      )}
    </div>
  )
}
