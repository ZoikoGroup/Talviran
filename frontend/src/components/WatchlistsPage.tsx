import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { createPortal } from 'react-dom'
import {
  Bookmark,
  ArrowLeft,
  Plus,
  Trash2,
  TrendingDown,
  TrendingUp,
  Search,
  Bell,
  FolderPlus,
  Layers,
  ShieldCheck,
  Download,
  BarChart2,
  BookOpen,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Field, SubmitButton } from '@/components/ui/field'
import TradingViewModal from '@/components/TradingViewModal'
import { matchAssetSearch } from '@/lib/searchSynonyms'
import {
  type Watchlist,
  listWatchlists,
  createWatchlist,
  deleteWatchlist,
  addWatchlistItem,
  removeWatchlistItem,
  ApiError,
} from '@/lib/api'
import { useEntitlement } from '@/context/EntitlementContext'
import { toast } from 'sonner'
import type { TaggedAsset } from '@/data/mockReply'

interface WatchlistsPageProps {
  onBack?: () => void
  onStartResearch: (assetOrQuery: string | TaggedAsset, prompt?: string) => void
  onOpenMonitoringForRule?: (symbol: string) => void
  onOpenPricing?: () => void
}

// Live simulated pricing & market state mapped to instruments
interface MarketQuote {
  last: string
  change: string
  pctChange: string
  direction: 'up' | 'down' | 'flat'
  sparkline: number[]
  source: string
  freshness: string
  bitemporalStatus: 'RECONCILED' | 'CANONICAL'
}

const LIVE_QUOTES: Record<string, MarketQuote> = {
  'UK 10Y Gilt': {
    last: '4.216%',
    change: '-2.4 bps',
    pctChange: '-0.57%',
    direction: 'down',
    sparkline: [4.24, 4.235, 4.23, 4.225, 4.22, 4.216],
    source: 'Bank of England',
    freshness: '12m ago',
    bitemporalStatus: 'CANONICAL',
  },
  'US 10Y Treasury': {
    last: '4.327%',
    change: '+1.1 bps',
    pctChange: '+0.25%',
    direction: 'up',
    sparkline: [4.31, 4.315, 4.32, 4.322, 4.325, 4.327],
    source: 'Federal Reserve / US Treasury',
    freshness: '5m ago',
    bitemporalStatus: 'CANONICAL',
  },
  'DE 10Y Bund': {
    last: '2.441%',
    change: '+0.8 bps',
    pctChange: '+0.33%',
    direction: 'up',
    sparkline: [2.42, 2.425, 2.43, 2.435, 2.438, 2.441],
    source: 'Deutsche Bundesbank',
    freshness: '20m ago',
    bitemporalStatus: 'CANONICAL',
  },
  'JP 10Y JGB': {
    last: '0.845%',
    change: '-0.2 bps',
    pctChange: '-0.24%',
    direction: 'down',
    sparkline: [0.85, 0.849, 0.848, 0.846, 0.845, 0.845],
    source: 'Ministry of Finance Japan',
    freshness: '1h ago',
    bitemporalStatus: 'CANONICAL',
  },
  'S&P 500': {
    last: '6,589.34',
    change: '+40.6',
    pctChange: '+0.62%',
    direction: 'up',
    sparkline: [6540, 6555, 6562, 6570, 6580, 6589.34],
    source: 'Cboe / S&P Dow Jones',
    freshness: 'Real-time',
    bitemporalStatus: 'RECONCILED',
  },
  'FTSE 100': {
    last: '8,261.40',
    change: '+23.1',
    pctChange: '+0.28%',
    direction: 'up',
    sparkline: [8230, 8240, 8245, 8250, 8255, 8261.4],
    source: 'London Stock Exchange',
    freshness: 'Real-time',
    bitemporalStatus: 'RECONCILED',
  },
  'GBP/USD': {
    last: '1.2984',
    change: '-0.0012',
    pctChange: '-0.09%',
    direction: 'down',
    sparkline: [1.301, 1.2995, 1.299, 1.2988, 1.2984, 1.2984],
    source: 'Bank of England FX Fix',
    freshness: '3m ago',
    bitemporalStatus: 'CANONICAL',
  },
  'EUR/USD': {
    last: '1.0872',
    change: '+0.0005',
    pctChange: '+0.05%',
    direction: 'up',
    sparkline: [1.086, 1.0865, 1.0868, 1.087, 1.0871, 1.0872],
    source: 'ECB Reference Rate',
    freshness: '15m ago',
    bitemporalStatus: 'CANONICAL',
  },
}

function getQuoteFor(symbol: string): MarketQuote {
  if (LIVE_QUOTES[symbol]) return LIVE_QUOTES[symbol]
  return {
    last: '100.00',
    change: '+0.00',
    pctChange: '0.00%',
    direction: 'flat',
    sparkline: [100, 100, 100, 100, 100, 100],
    source: 'Authoritative Market Observation',
    freshness: 'Active',
    bitemporalStatus: 'RECONCILED',
  }
}

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

export default function WatchlistsPage({
  onBack,
  onStartResearch,
  onOpenMonitoringForRule,
  onOpenPricing,
}: WatchlistsPageProps) {
  const [watchlists, setWatchlists] = useState<Watchlist[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Creation dialogs
  const [showNewWatchlist, setShowNewWatchlist] = useState(false)
  const [newWatchlistName, setNewWatchlistName] = useState('')
  const [newWatchlistDesc, setNewWatchlistDesc] = useState('')
  const [creatingWl, setCreatingWl] = useState(false)

  // Add Item dialog
  const [showAddItem, setShowAddItem] = useState(false)
  const [itemSymbol, setItemSymbol] = useState('')
  const [itemName, setItemName] = useState('')
  const [itemAssetClass, setItemAssetClass] = useState('RATES')
  const [addingItem, setAddingItem] = useState(false)

  // Filter search inside current list
  const [tableSearch, setTableSearch] = useState('')

  // TradingView modal active item
  const [selectedTradeViewItem, setSelectedTradeViewItem] = useState<{
    symbol: string
    name: string
    assetClass: string
  } | null>(null)

  const loadData = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await listWatchlists()
      setWatchlists(data)
      if (data.length > 0 && !selectedId) {
        setSelectedId(data[0].id)
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message)
      } else {
        // Offline or demo fallback
        const mockDefaults: Watchlist[] = [
          {
            id: 'mock-1',
            name: 'Global Sovereign 10Y',
            description: 'Key sovereign benchmark 10-year yields and benchmark debt',
            isDefault: true,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            items: [
              {
                id: 'm1',
                watchlistId: 'mock-1',
                symbol: 'UK 10Y Gilt',
                name: 'UK 10-Year Benchmark Gilt',
                assetClass: 'RATES',
                sortOrder: 0,
                createdAt: new Date().toISOString(),
              },
              {
                id: 'm2',
                watchlistId: 'mock-1',
                symbol: 'US 10Y Treasury',
                name: 'US 10-Year Treasury Note',
                assetClass: 'RATES',
                sortOrder: 1,
                createdAt: new Date().toISOString(),
              },
              {
                id: 'm3',
                watchlistId: 'mock-1',
                symbol: 'DE 10Y Bund',
                name: 'Germany 10-Year Bund',
                assetClass: 'RATES',
                sortOrder: 2,
                createdAt: new Date().toISOString(),
              },
              {
                id: 'm4',
                watchlistId: 'mock-1',
                symbol: 'JP 10Y JGB',
                name: 'Japan 10-Year JGB',
                assetClass: 'RATES',
                sortOrder: 3,
                createdAt: new Date().toISOString(),
              },
            ],
          },
          {
            id: 'mock-2',
            name: 'Major Indices & FX',
            description: 'Primary equity indices and currency pairs',
            isDefault: false,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            items: [
              {
                id: 'm5',
                watchlistId: 'mock-2',
                symbol: 'S&P 500',
                name: 'S&P 500 Index',
                assetClass: 'EQUITY',
                sortOrder: 0,
                createdAt: new Date().toISOString(),
              },
              {
                id: 'm6',
                watchlistId: 'mock-2',
                symbol: 'FTSE 100',
                name: 'FTSE 100 Index',
                assetClass: 'EQUITY',
                sortOrder: 1,
                createdAt: new Date().toISOString(),
              },
              {
                id: 'm7',
                watchlistId: 'mock-2',
                symbol: 'GBP/USD',
                name: 'British Pound / US Dollar',
                assetClass: 'FX',
                sortOrder: 2,
                createdAt: new Date().toISOString(),
              },
              {
                id: 'm8',
                watchlistId: 'mock-2',
                symbol: 'EUR/USD',
                name: 'Euro / US Dollar',
                assetClass: 'FX',
                sortOrder: 3,
                createdAt: new Date().toISOString(),
              },
            ],
          },
        ]
        setWatchlists(mockDefaults)
        if (!selectedId) setSelectedId('mock-1')
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [])

  const currentList = watchlists.find((w) => w.id === selectedId) || watchlists[0]

  const { checkLimit } = useEntitlement()

  const handleCreateWatchlist = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newWatchlistName.trim()) return

    // Quota gating check
    const quota = checkLimit('watchlists')
    if (quota.isExceeded || (quota.max !== 'unlimited' && watchlists.length >= quota.max)) {
      toast.error(
        `Watchlist limit reached (${quota.current} / ${quota.max}). Upgrade your plan to create more watchlists.`
      )
      if (onOpenPricing) onOpenPricing()
      return
    }

    try {
      setCreatingWl(true)
      const created = await createWatchlist({
        name: newWatchlistName.trim(),
        description: newWatchlistDesc.trim() || undefined,
      })
      setWatchlists((prev) => [...prev, created])
      setSelectedId(created.id)
      setNewWatchlistName('')
      setNewWatchlistDesc('')
      setShowNewWatchlist(false)
      toast.success(`Watchlist "${created.name}" created successfully.`)
    } catch (err) {
      console.error(err)
      toast.error('Failed to create watchlist. Please try again.')
    } finally {
      setCreatingWl(false)
    }
  }

  const handleDeleteWatchlist = async (id: string) => {
    if (!confirm('Are you sure you want to delete this watchlist?')) return
    try {
      await deleteWatchlist(id)
      setWatchlists((prev) => prev.filter((w) => w.id !== id))
      if (selectedId === id) {
        const remaining = watchlists.filter((w) => w.id !== id)
        setSelectedId(remaining.length ? remaining[0].id : null)
      }
    } catch (err) {
      console.error(err)
    }
  }

  const handleAddItem = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!currentList || !itemSymbol.trim() || !itemName.trim()) return
    try {
      setAddingItem(true)
      const added = await addWatchlistItem(currentList.id, {
        symbol: itemSymbol.trim(),
        name: itemName.trim(),
        assetClass: itemAssetClass,
      })
      setWatchlists((prev) =>
        prev.map((w) =>
          w.id === currentList.id ? { ...w, items: [...w.items, added] } : w
        )
      )
      setItemSymbol('')
      setItemName('')
      setShowAddItem(false)
    } catch (err) {
      console.error(err)
    } finally {
      setAddingItem(false)
    }
  }

  const handleRemoveItem = async (itemId: string) => {
    if (!currentList) return
    try {
      await removeWatchlistItem(currentList.id, itemId)
      setWatchlists((prev) =>
        prev.map((w) =>
          w.id === currentList.id
            ? { ...w, items: w.items.filter((it) => it.id !== itemId) }
            : w
        )
      )
    } catch (err) {
      console.error(err)
    }
  }

  const handleExportCsv = () => {
    if (!currentList) return
    const headers = ['Symbol', 'Name', 'Asset Class', 'Last Price/Yield', 'Change', '% Change', 'Source', 'Bitemporal Status']
    const rows = (currentList.items || []).map((it) => {
      const q = getQuoteFor(it.symbol)
      return [
        `"${it.symbol.replace(/"/g, '""')}"`,
        `"${it.name.replace(/"/g, '""')}"`,
        `"${it.assetClass}"`,
        `"${q.last}"`,
        `"${q.change}"`,
        `"${q.pctChange}"`,
        `"${q.source}"`,
        `"${q.bitemporalStatus}"`,
      ].join(',')
    })

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows].join('\n')
    const encodedUri = encodeURI(csvContent)
    const link = document.createElement('a')
    link.setAttribute('href', encodedUri)
    link.setAttribute('download', `${currentList.name.toLowerCase().replace(/\s+/g, '_')}_portfolio.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const filteredItems = (currentList?.items || []).filter((item) => {
    if (!tableSearch) return true
    return matchAssetSearch(item, tableSearch)
  })

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
              <Bookmark className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-foreground sm:text-2xl">
                Watchlists & Market Portfolios
              </h1>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <Link
            to="/guides?topic=platform-surfaces"
            className="inline-flex items-center gap-1.5 rounded-xl border border-border/80 bg-background px-3 py-2 text-[12.5px] font-semibold text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            title="Read documentation on portfolio watchlists & canonical reconciliation"
          >
            <BookOpen className="h-4 w-4 text-primary" />
            <span>Watchlists Guide</span>
          </Link>

          <button
            onClick={() => setShowNewWatchlist(true)}
            className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-3.5 py-2 text-[13px] font-semibold text-primary-foreground shadow-sm transition hover:opacity-90 active:scale-95"
          >
            <FolderPlus className="h-4 w-4" />
            <span>New Watchlist</span>
          </button>
        </div>
      </div>

      <div className="mx-auto mt-6 flex w-full max-w-7xl flex-1 flex-col gap-6">
        {error && (
          <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-2.5 text-[13px] text-destructive">
            {error}
          </div>
        )}
        {loading && (
          <div className="text-[12.5px] text-muted-foreground animate-pulse">
            Loading real-time watchlists...
          </div>
        )}
        {/* Watchlist Tabs Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/80 pb-3">
          <div className="flex flex-wrap items-center gap-2">
            {watchlists.map((w) => {
              const active = w.id === (currentList?.id || selectedId)
              return (
                <button
                  key={w.id}
                  onClick={() => setSelectedId(w.id)}
                  className={cn(
                    'group flex items-center gap-2 rounded-xl px-3.5 py-2 text-[13px] font-medium transition-all',
                    active
                      ? 'bg-card text-foreground shadow-sm ring-1 ring-border font-semibold'
                      : 'text-muted-foreground hover:bg-card/60 hover:text-foreground'
                  )}
                >
                  <Layers className={cn('h-3.5 w-3.5', active ? 'text-primary' : 'opacity-60')} />
                  <span>{w.name}</span>
                  <span
                    className={cn(
                      'rounded-full px-1.5 py-0.2 text-[11px]',
                      active
                        ? 'bg-primary/15 text-primary'
                        : 'bg-muted text-muted-foreground group-hover:text-foreground'
                    )}
                  >
                    {w.items?.length || 0}
                  </span>
                </button>
              )
            })}
          </div>

          {currentList && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              {!currentList.isDefault && (
                <button
                  onClick={() => handleDeleteWatchlist(currentList.id)}
                  title="Delete Watchlist"
                  className="rounded-lg p-1.5 text-muted-foreground hover:bg-rose-500/10 hover:text-rose-400 transition"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </div>
          )}
        </div>

        {/* Current Watchlist Details Bar */}
        {currentList && (
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-xl border border-border bg-card/60 p-4">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-[16px] font-semibold text-foreground">{currentList.name}</h2>
                {currentList.isDefault && (
                  <span className="rounded bg-primary/15 px-2 py-0.5 text-[10px] font-semibold text-primary">
                    DEFAULT
                  </span>
                )}
              </div>
              {currentList.description && (
                <p className="mt-1 text-[13px] text-muted-foreground">
                  {currentList.description}
                </p>
              )}
            </div>

            <div className="flex items-center gap-3">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="text"
                  placeholder="Filter instruments..."
                  value={tableSearch}
                  onChange={(e) => setTableSearch(e.target.value)}
                  className="h-8 w-48 rounded-lg border border-border bg-background pl-8 pr-3 text-[12.5px] text-foreground placeholder:text-muted-foreground/70 focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              <button
                onClick={handleExportCsv}
                title="Export this portfolio to CSV"
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-accent transition shadow-sm"
              >
                <Download className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="hidden sm:inline">Export CSV</span>
              </button>

              <button
                onClick={() => setShowAddItem(true)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-accent transition shadow-sm"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>Add Instrument</span>
              </button>
            </div>
          </div>
        )}

        {/* Table Content */}
        <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[13px]">
              <thead className="border-b border-border bg-muted/40 text-[11.5px] font-medium uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="py-3 pl-4 pr-3">Instrument</th>
                  <th className="px-3 py-3">Asset Class</th>
                  <th className="px-3 py-3 text-right">Last / Yield</th>
                  <th className="px-3 py-3 text-right">Net Chg</th>
                  <th className="px-3 py-3 text-right">% Chg</th>
                  <th className="px-3 py-3 text-center">Trend (7D)</th>
                  <th className="px-3 py-3">Authoritative Source</th>
                  <th className="py-3 pl-3 pr-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {filteredItems.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-16 text-center text-muted-foreground">
                      <div className="flex flex-col items-center justify-center gap-2.5 max-w-sm mx-auto">
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-muted/60 text-muted-foreground border border-border">
                          <Search className="h-5 w-5" />
                        </div>
                        <div className="text-sm font-semibold text-foreground">
                          {tableSearch.trim() ? 'No matching instruments found' : 'No instruments in this watchlist'}
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {tableSearch.trim()
                            ? `No items match "${tableSearch}". Try searching by asset symbol or company name.`
                            : 'Add assets to track live prices, yield benchmarks, and risk metrics.'}
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  filteredItems.map((item) => {
                    const quote = getQuoteFor(item.symbol)
                    const isUp = quote.direction === 'up'
                    const isDown = quote.direction === 'down'

                    return (
                      <tr
                        key={item.id}
                        onClick={() =>
                          setSelectedTradeViewItem({
                            symbol: item.symbol,
                            name: item.name,
                            assetClass: item.assetClass,
                          })
                        }
                        className="group cursor-pointer transition-colors hover:bg-accent/40"
                      >
                        {/* Instrument */}
                        <td className="py-3.5 pl-4 pr-3">
                          <div className="flex flex-col">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-foreground group-hover:text-primary transition-colors whitespace-nowrap">
                                {item.symbol}
                              </span>
                              <span className="opacity-0 group-hover:opacity-100 transition-all duration-150 inline-flex items-center gap-1 rounded-md bg-primary/15 border border-primary/25 px-1.5 py-0.5 text-[10.5px] font-medium text-primary whitespace-nowrap shadow-2xs">
                                <BarChart2 className="h-2.5 w-2.5" />
                                <span>View Chart</span>
                              </span>
                            </div>
                            <span className="text-[11.5px] text-muted-foreground truncate max-w-xs">
                              {item.name}
                            </span>
                          </div>
                        </td>

                        {/* Asset Class */}
                        <td className="px-3 py-3.5">
                          <span className="inline-flex rounded-md bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground border border-border/70">
                            {item.assetClass}
                          </span>
                        </td>

                        {/* Last */}
                        <td className="px-3 py-3.5 text-right font-mono font-semibold text-foreground">
                          {quote.last}
                        </td>

                        {/* Change */}
                        <td
                          className={cn(
                            'px-3 py-3.5 text-right font-mono text-[12.5px] font-medium',
                            isUp ? 'text-emerald-500' : isDown ? 'text-rose-500' : 'text-muted-foreground'
                          )}
                        >
                          {quote.change}
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
                            {quote.pctChange}
                          </span>
                        </td>

                        {/* Sparkline */}
                        <td className="px-3 py-3.5 text-center">
                          <div className="inline-flex justify-center">
                            <MiniSparkline data={quote.sparkline} direction={quote.direction} />
                          </div>
                        </td>

                        {/* Source & Freshness */}
                        <td className="px-3 py-3.5">
                          <div className="flex flex-col">
                            <span className="text-[12px] font-medium text-foreground flex items-center gap-1">
                              <ShieldCheck className="h-3 w-3 text-primary" />
                              {quote.source}
                            </span>
                            <span className="text-[11px] text-muted-foreground">
                              {quote.freshness} • {quote.bitemporalStatus}
                            </span>
                          </div>
                        </td>

                        {/* Actions */}
                        <td className="py-3.5 pl-3 pr-4 text-right">
                          <div
                            onClick={(e) => e.stopPropagation()}
                            className="flex items-center justify-end gap-1.5 opacity-90 group-hover:opacity-100"
                          >
                            <button
                              onClick={() => {
                                onStartResearch({
                                  symbol: item.symbol,
                                  name: item.name,
                                  assetClass: item.assetClass,
                                  price: quote.last,
                                  change: quote.change,
                                  pctChange: quote.pctChange,
                                  direction: quote.direction,
                                  source: quote.source,
                                })
                              }}
                              title="Research Instrument"
                              className="inline-flex items-center gap-1 rounded-lg border border-border bg-secondary/60 px-2.5 py-1 text-[11.5px] font-semibold text-foreground hover:bg-primary hover:text-primary-foreground hover:border-primary transition shadow-xs"
                            >
                              <Search className="h-3 w-3" />
                              <span>Research</span>
                            </button>

                            <button
                              onClick={() => onOpenMonitoringForRule && onOpenMonitoringForRule(item.symbol)}
                              title="Set Alert Rule"
                              className="rounded-lg border border-border p-1 text-muted-foreground hover:bg-accent hover:text-foreground transition"
                            >
                              <Bell className="h-3.5 w-3.5" />
                            </button>

                            <button
                              onClick={() => handleRemoveItem(item.id)}
                              title="Remove from watchlist"
                              className="rounded-lg p-1 text-muted-foreground hover:bg-rose-500/10 hover:text-rose-400 transition"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
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
      </div>

      {/* New Watchlist Modal */}
      {showNewWatchlist &&
        createPortal(
          <div className="fixed inset-0 z-[999] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
            <div className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl">
              <h3 className="text-lg font-semibold text-foreground">Create New Watchlist</h3>
              <p className="mt-1 text-[13px] text-muted-foreground">
                Create a custom portfolio or observation basket to track across global markets.
              </p>
              <form onSubmit={handleCreateWatchlist} className="mt-5 space-y-4">
                <Field label="Watchlist Name">
                  <input
                    type="text"
                    required
                    placeholder="e.g. European Inflation & Sovereign Debt"
                    value={newWatchlistName}
                    onChange={(e) => setNewWatchlistName(e.target.value)}
                    className="w-full rounded-xl border border-border bg-background px-3 py-2 text-[13.5px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </Field>
                <Field label="Description (optional)">
                  <input
                    type="text"
                    placeholder="Brief description of portfolio scope"
                    value={newWatchlistDesc}
                    onChange={(e) => setNewWatchlistDesc(e.target.value)}
                    className="w-full rounded-xl border border-border bg-background px-3 py-2 text-[13.5px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </Field>
                <div className="mt-6 flex justify-end gap-2.5">
                  <button
                    type="button"
                    onClick={() => setShowNewWatchlist(false)}
                    className="rounded-xl px-4 py-2 text-[13px] font-medium text-muted-foreground hover:bg-accent"
                  >
                    Cancel
                  </button>
                  <SubmitButton busy={creatingWl}>Create Watchlist</SubmitButton>
                </div>
              </form>
            </div>
          </div>,
          document.body
        )}

      {/* Add Item Modal */}
      {showAddItem &&
        createPortal(
          <div className="fixed inset-0 z-[999] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
            <div className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl">
              <h3 className="text-lg font-semibold text-foreground">Add Instrument to Watchlist</h3>
              <p className="mt-1 text-[13px] text-muted-foreground">
                Track a benchmark rate, sovereign bond, index, or currency pair.
              </p>
              <form onSubmit={handleAddItem} className="mt-5 space-y-4">
                <Field label="Symbol / Ticker">
                  <input
                    type="text"
                    required
                    placeholder="e.g. UK 5Y Gilt, EUR/GBP, NASDAQ 100"
                    value={itemSymbol}
                    onChange={(e) => setItemSymbol(e.target.value)}
                    className="w-full rounded-xl border border-border bg-background px-3 py-2 text-[13.5px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </Field>
                <Field label="Instrument Name">
                  <input
                    type="text"
                    required
                    placeholder="e.g. United Kingdom 5-Year Sovereign Benchmark"
                    value={itemName}
                    onChange={(e) => setItemName(e.target.value)}
                    className="w-full rounded-xl border border-border bg-background px-3 py-2 text-[13.5px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </Field>
                <Field label="Asset Class">
                  <select
                    value={itemAssetClass}
                    onChange={(e) => setItemAssetClass(e.target.value)}
                    className="w-full rounded-xl border border-border bg-background px-3 py-2 text-[13.5px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <option value="RATES">Sovereign Rates & Debt (RATES)</option>
                    <option value="EQUITY">Equity & Indices (EQUITY)</option>
                    <option value="FX">Foreign Exchange (FX)</option>
                    <option value="COMMODITY">Commodity (COMMODITY)</option>
                  </select>
                </Field>
                <div className="mt-6 flex justify-end gap-2.5">
                  <button
                    type="button"
                    onClick={() => setShowAddItem(false)}
                    className="rounded-xl px-4 py-2 text-[13px] font-medium text-muted-foreground hover:bg-accent"
                  >
                    Cancel
                  </button>
                  <SubmitButton busy={addingItem}>Add Instrument</SubmitButton>
                </div>
              </form>
            </div>
          </div>,
          document.body
        )}

      {/* TradingView Interactive Chart Modal */}
      {selectedTradeViewItem && (() => {
        const quote = getQuoteFor(selectedTradeViewItem.symbol)
        return (
          <TradingViewModal
            symbol={selectedTradeViewItem.symbol}
            name={selectedTradeViewItem.name}
            assetClass={selectedTradeViewItem.assetClass}
            last={quote.last}
            change={quote.change}
            pctChange={quote.pctChange}
            direction={quote.direction}
            source={quote.source}
            freshness={quote.freshness}
            bitemporalStatus={quote.bitemporalStatus}
            onClose={() => setSelectedTradeViewItem(null)}
            onStartResearch={(asset) => {
              setSelectedTradeViewItem(null)
              onStartResearch(asset)
            }}
            onOpenMonitoring={(sym) => {
              setSelectedTradeViewItem(null)
              if (onOpenMonitoringForRule) onOpenMonitoringForRule(sym)
            }}
          />
        )
      })()}
    </div>
  )
}
