import { useEffect, useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
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
  Bell,
  BookOpen,
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
import SetAlertModal from '@/components/SetAlertModal'
import { toast } from 'sonner'
import TradingViewScreener from '@/components/TradingViewScreener'
import type { TaggedAsset } from '@/data/mockReply'
import { useLiveMarket } from '@/hooks/useLiveMarket'

interface MarketsPageProps {
  initialSymbol?: string | null
  onBack?: () => void
  onStartResearch: (assetOrQuery: string | TaggedAsset, prompt?: string) => void
  onOpenMonitoringForRule?: (symbol: string) => void
  onOpenWatchlists?: () => void
}

export { GLOBAL_MARKET_ASSETS, type MarketAsset } from '@/data/globalAssets'
import { GLOBAL_MARKET_ASSETS, type MarketAsset } from '@/data/globalAssets'
import { matchAssetSearch } from '@/lib/searchSynonyms'

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
  const [alertAsset, setAlertAsset] = useState<MarketAsset | null>(null)
  const [dynamicSyncedAssets, setDynamicSyncedAssets] = useState<MarketAsset[]>([])
  const [isSyncing, setIsSyncing] = useState(false)
  const [lastSyncTime, setLastSyncTime] = useState<string | null>(null)
  const { livePrices } = useLiveMarket()

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
    const q = search.trim().toLowerCase()

    const results = allAssets.filter((a) => {
      if (q) {
        if (!matchAssetSearch(a, q)) return false
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

    if (!q) return results

    // Relevance Ranking: prioritize exact ticker match, ticker prefix, name match
    return results.sort((a, b) => {
      const aSym = a.symbol.toLowerCase()
      const bSym = b.symbol.toLowerCase()
      const aName = a.name.toLowerCase()
      const bName = b.name.toLowerCase()

      // Exact symbol match is top rank
      const aExact = aSym === q
      const bExact = bSym === q
      if (aExact && !bExact) return -1
      if (!aExact && bExact) return 1

      // Prefix symbol match
      const aPrefix = aSym.startsWith(q)
      const bPrefix = bSym.startsWith(q)
      if (aPrefix && !bPrefix) return -1
      if (!aPrefix && bPrefix) return 1

      // Exact name match or starts with name
      const aNamePrefix = aName.startsWith(q)
      const bNamePrefix = bName.startsWith(q)
      if (aNamePrefix && !bNamePrefix) return -1
      if (!aNamePrefix && bNamePrefix) return 1

      return 0
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
    <div className="flex h-full flex-col overflow-y-auto bg-background p-4 md:p-6 scrollbar-slim">
      {/* Header */}
      <div className="mx-auto flex w-full flex-col gap-4 pb-4 border-b border-border/70 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-start gap-3">
          {onBack && (
            <button
              onClick={onBack}
              aria-label="Back"
              className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <ArrowLeft className="h-[18px] w-[18px]" />
            </button>
          )}
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary border border-primary/20">
            <Globe2 className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-foreground sm:text-2xl">
              Global Markets Coverage
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-2.5 self-start lg:self-center">
          <Link
            to="/guides?topic=market-data-freshness"
            className="hidden sm:inline-flex items-center gap-1.5 rounded-xl border border-border/80 bg-background px-3 py-1.5 text-xs font-semibold text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            title="Learn how market feeds, connector protocols, and freshness states work"
          >
            <BookOpen className="h-3.5 w-3.5 text-primary" />
            <span>Feeds & Sources Guide</span>
          </Link>

          {/* View Switch: Curated Table vs Full World Screener */}
          <div className="inline-flex items-center rounded-xl border border-border/80 bg-muted/40 p-1 text-xs">
            <button
              onClick={() => setViewMode('table')}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium whitespace-nowrap transition cursor-pointer',
                viewMode === 'table'
                  ? 'bg-background text-foreground font-semibold shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <BarChart2 className="h-3.5 w-3.5 shrink-0" />
              <span>Benchmarks Table</span>
            </button>
            <button
              onClick={() => setViewMode('screener')}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium whitespace-nowrap transition cursor-pointer',
                viewMode === 'screener'
                  ? 'bg-background text-foreground font-semibold shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <Layers className="h-3.5 w-3.5 shrink-0" />
              <span>World Screener</span>
            </button>
          </div>

          <button
            onClick={handleTriggerSync}
            disabled={isSyncing}
            className="inline-flex items-center gap-1.5 rounded-xl border border-border/80 bg-background px-3.5 py-2 text-xs font-medium whitespace-nowrap text-foreground shadow-xs hover:bg-accent transition disabled:opacity-50 cursor-pointer"
            title="Auto-sync new assets from TwelveData, AMFI, and TradingView"
          >
            <RefreshCw className={cn("h-3.5 w-3.5 shrink-0 text-primary", isSyncing && "animate-spin")} />
            <span>{isSyncing ? "Syncing..." : lastSyncTime ? `Synced (${lastSyncTime})` : "Live Sync"}</span>
          </button>

          {onOpenWatchlists && (
            <button
              onClick={onOpenWatchlists}
              className="inline-flex items-center gap-1.5 rounded-xl border border-border/80 bg-background px-3.5 py-2 text-xs font-medium whitespace-nowrap text-foreground shadow-xs hover:bg-accent transition cursor-pointer"
            >
              <Bookmark className="h-3.5 w-3.5 shrink-0 text-primary" />
              <span>Watchlists</span>
            </button>
          )}
        </div>
      </div>

      <div className="mx-auto mt-4 flex w-full flex-1 flex-col gap-4">
        {/* Unified Filter and Controls Bar */}
        <div className="flex flex-col gap-3 rounded-xl border border-border/80 bg-card/60 p-3.5 shadow-xs backdrop-blur-sm">
          {/* Asset Class Categories */}
          <div className="flex flex-wrap items-center gap-1.5">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id)
                  if (viewMode !== 'table') setViewMode('table')
                }}
                className={cn(
                  'inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition cursor-pointer',
                  activeTab === tab.id
                    ? 'bg-primary text-primary-foreground font-semibold shadow-xs'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                )}
              >
                <span>{tab.label}</span>
                <span
                  className={cn(
                    'rounded-full px-1.5 py-0.5 text-[10px] font-semibold tabular-nums leading-none',
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

          <div className="h-px w-full bg-border/50" />

          {/* Secondary Controls: Region + Data Source + Search */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mr-1">
                Region:
              </span>
              <div className="inline-flex h-8 items-center rounded-lg border border-border/80 bg-background p-0.5 text-xs">
                {(['ALL', 'UK', 'US', 'EU', 'APAC'] as const).map((reg) => (
                  <button
                    key={reg}
                    onClick={() => setActiveRegion(reg)}
                    className={cn(
                      'h-7 rounded-md px-2.5 text-xs font-medium transition cursor-pointer',
                      activeRegion === reg
                        ? 'bg-primary/15 text-primary font-semibold'
                        : 'text-muted-foreground hover:text-foreground'
                    )}
                  >
                    {reg}
                  </button>
                ))}
              </div>

              <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mx-1">
                Source:
              </span>
              <select
                value={activeSource}
                onChange={(e) => setActiveSource(e.target.value)}
                className="h-8 rounded-lg border border-border/80 bg-background px-2.5 text-xs font-medium text-foreground outline-none hover:border-primary/50 cursor-pointer focus:ring-1 focus:ring-primary"
              >
                <option value="ALL">All Sources (Global)</option>
                <option value="TradingView">TradingView</option>
                <option value="CoinMarketCap">CoinMarketCap</option>
                <option value="Primary Exchanges">Primary Exchanges</option>
                <option value="Commodities">Commodities (LBMA/CME)</option>
                <option value="Central Banks">Central Banks & Treasury</option>
              </select>
            </div>

            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search benchmark or ticker..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-8 w-56 rounded-lg border border-border/80 bg-background pl-8 pr-3 text-xs text-foreground placeholder:text-muted-foreground/70 focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary/70"
              />
            </div>
          </div>
        </div>

        {viewMode === 'screener' ? (
          <div className="flex flex-col gap-3 min-h-[850px] pb-6">
            <TradingViewScreener
              initialMarket={activeRegion === 'UK' ? 'uk' : activeRegion === 'EU' ? 'germany' : activeRegion === 'APAC' ? 'india' : 'america'}
              height={850}
              colorTheme="dark"
              onStartResearch={onStartResearch}
            />
          </div>
        ) : (
          /* Global Market Data Table */
          <div className="overflow-hidden rounded-xl border border-border/80 bg-card shadow-xs">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs min-w-[980px]">
                <thead className="border-b border-border/80 bg-muted/50 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="py-2.5 pl-4 pr-3 w-[24%]">Instrument</th>
                    <th className="px-3 py-2.5 w-[14%]">Class / Region</th>
                    <th className="px-3 py-2.5 text-right w-[11%]">Price / Yield</th>
                    <th className="px-3 py-2.5 text-right w-[9%]">Net Chg</th>
                    <th className="px-3 py-2.5 text-right w-[10%]">% Chg</th>
                    <th className="px-3 py-2.5 text-center w-[9%]">Trend (7D)</th>
                    <th className="px-3 py-2.5 w-[13%]">Data Origin</th>
                    <th className="py-2.5 pl-3 pr-4 text-right w-[10%]">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {filteredAssets.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-16 text-center text-muted-foreground">
                        <div className="flex flex-col items-center justify-center gap-3.5 max-w-md mx-auto">
                          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-muted/60 text-muted-foreground/80 border border-border/80">
                            <Search className="h-6 w-6" />
                          </div>
                          <div className="space-y-1">
                            <h3 className="text-sm font-semibold text-foreground">No matching assets found</h3>
                            <p className="text-xs text-muted-foreground">
                              {search.trim()
                                ? `No instruments or benchmarks match "${search}". Try searching ticker, company name, or asset class.`
                                : 'No assets match the selected filter criteria.'}
                            </p>
                          </div>
                          {(activeTab !== 'ALL' || activeRegion !== 'ALL' || activeSource !== 'ALL') && (
                            <button
                              onClick={() => {
                                setActiveTab('ALL')
                                setActiveRegion('ALL')
                                setActiveSource('ALL')
                              }}
                              className="inline-flex items-center gap-1.5 text-xs text-primary hover:underline font-medium"
                            >
                              Reset filters to search all 247+ assets
                            </button>
                          )}
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
                      const live = livePrices[asset.symbol]
                      const displayedPrice = live ? live.price : asset.price
                      const displayedChange = live ? live.change : asset.change
                      const currentDirection = live ? live.direction : asset.direction
                      const isUp = currentDirection === 'up'
                      const isDown = currentDirection === 'down'
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
                              <div className="flex items-center gap-2">
                                <span className="font-semibold text-foreground group-hover:text-primary transition-colors whitespace-nowrap">
                                  {asset.symbol}
                                </span>
                                {live && (
                                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-ping inline-block" title="Real-time WebSocket streaming" />
                                )}
                                <span className="opacity-0 group-hover:opacity-100 transition-all duration-150 inline-flex items-center gap-1 rounded-md bg-primary/15 border border-primary/25 px-1.5 py-0.5 text-[10.5px] font-medium text-primary whitespace-nowrap shadow-2xs">
                                  <BarChart2 className="h-2.5 w-2.5" />
                                  <span>View Chart</span>
                                </span>
                              </div>
                              <span className="text-[11.5px] text-muted-foreground truncate max-w-xs">
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
                            <span
                              className={cn(
                                'transition-colors rounded px-1 py-0.5',
                                live?.direction === 'up' && 'bg-emerald-500/15 text-emerald-400 font-bold',
                                live?.direction === 'down' && 'bg-rose-500/15 text-rose-400 font-bold'
                              )}
                            >
                              {displayedPrice}
                            </span>
                          </td>

                          {/* Net Change */}
                          <td
                            className={cn(
                              'px-3 py-3.5 text-right font-mono text-[12.5px] font-medium',
                              isUp ? 'text-emerald-500' : isDown ? 'text-rose-500' : 'text-muted-foreground'
                            )}
                          >
                            {displayedChange}
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
                              {live ? displayedChange : asset.pctChange}
                            </span>
                          </td>

                          {/* Trend */}
                          <td className="px-3 py-3.5 text-center">
                            <div className="inline-flex justify-center">
                              <MiniSparkline data={asset.sparkline} direction={asset.direction} />
                            </div>
                          </td>

                          {/* Source */}
                          <td className="px-3 py-3">
                            <div className="flex flex-col min-w-0">
                              <span className="text-[11.5px] font-medium text-foreground flex items-center gap-1 truncate" title={asset.source}>
                                <ShieldCheck className="h-3 w-3 shrink-0 text-primary" />
                                <span className="truncate">{asset.source}</span>
                              </span>
                              <span className="text-[10.5px] text-muted-foreground whitespace-nowrap">
                                {asset.freshness} • {asset.bitemporalStatus}
                              </span>
                            </div>
                          </td>

                          {/* Actions */}
                          <td className="py-3 pl-3 pr-4 text-right whitespace-nowrap">
                            <div
                              onClick={(e) => e.stopPropagation()}
                              className="relative inline-flex items-center justify-end gap-1.5"
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
                                className="inline-flex h-7 items-center gap-1 rounded-md border border-border/80 bg-background px-2 text-[11px] font-semibold text-foreground hover:bg-primary hover:text-primary-foreground hover:border-primary transition shadow-2xs"
                              >
                                <Search className="h-3 w-3" />
                                <span>Research</span>
                              </button>

                              {/* Direct Set Alert trigger */}
                              <button
                                onClick={() => setAlertAsset(asset)}
                                title="Set Market Trigger / Alert"
                                className="inline-flex h-7 items-center gap-1 rounded-md border border-primary/30 bg-primary/10 px-2 text-[11px] font-medium text-primary hover:bg-primary/20 transition shadow-2xs"
                              >
                                <Bell className="h-3 w-3 text-primary" />
                                <span>Alert</span>
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
                                    'inline-flex h-7 items-center gap-1 rounded-md border px-2 text-[11px] font-medium transition shadow-2xs',
                                    isAdded
                                      ? 'border-emerald-500/50 bg-emerald-500/15 text-emerald-400'
                                      : 'border-border/80 bg-background text-foreground hover:bg-accent'
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
      {/* Charting Modal on Selected Asset */}
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

      {/* Set Alert Modal from Markets Page */}
      {alertAsset && (
        <SetAlertModal
          symbol={alertAsset.symbol}
          name={alertAsset.name}
          currentPrice={alertAsset.price}
          onClose={() => setAlertAsset(null)}
          onAlertCreated={(created) => {
            toast.success(`Alert armed for ${created.assetSymbol} at ${created.threshold}`)
          }}
        />
      )}
    </div>
  )
}
