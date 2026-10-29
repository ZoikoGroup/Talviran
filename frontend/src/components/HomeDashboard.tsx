import React, { useState, useEffect, useMemo, useRef } from 'react'
import {
  Search,
  ArrowRight,
  Bell,
  ChevronRight,
  BarChart3,
  FileText,
  Bookmark,
  Layers,
  Cpu,
  Settings,
  Plus,
  Trash2,
  X,
  Check,
  BookOpen,
  TrendingUp,
  TrendingDown,
  Sparkles,
} from 'lucide-react'
import earthImg from '@/assets/earth_space_view.jpg'
import {
  getDashboardOverview,
  type DashboardOverviewResponse,
} from '@/lib/api'
import type { Chat } from '@/components/Sidebar'
import { useLiveMarket } from '@/hooks/useLiveMarket'
import { GLOBAL_MARKET_ASSETS, type MarketAsset } from '@/data/globalAssets'
import { matchAssetSearch } from '@/lib/searchSynonyms'
import TradingViewModal from '@/components/TradingViewModal'
import type { TaggedAsset } from '@/data/mockReply'

interface HomeDashboardProps {
  onSearch: (query: string) => void
  onStartResearch: (assetOrQuery?: string | TaggedAsset, prompt?: string) => void
  onOpenMonitoring?: (symbol?: string) => void
  onOpenWatchlists?: () => void
  onOpenMarkets?: (symbol?: string) => void
  onOpenGuides?: (topicId?: string) => void
  chats?: Chat[]
  onSelectChat?: (chatId: string) => void
}

function MiniSparkline({ data, direction }: { data: number[]; direction: 'up' | 'down' | 'flat' }) {
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const width = 76
  const height = 22

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

export default function HomeDashboard({
  onSearch,
  onStartResearch,
  onOpenMonitoring,
  onOpenWatchlists,
  onOpenMarkets,
  onOpenGuides,
  chats = [],
  onSelectChat,
}: HomeDashboardProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedSource, setSelectedSource] = useState('All sources')
  const [isSearchFocused, setIsSearchFocused] = useState(false)
  const [selectedSearchIndex, setSelectedSearchIndex] = useState(-1)
  const [selectedAssetForChart, setSelectedAssetForChart] = useState<MarketAsset | null>(null)
  const searchContainerRef = useRef<HTMLDivElement>(null)

  // Live filter matching assets based on search query and optional selected source
  const matchedAssets = useMemo(() => {
    const q = searchQuery.trim()
    if (!q) return []
    return GLOBAL_MARKET_ASSETS.filter((asset) => {
      if (!matchAssetSearch(asset, q)) return false
      if (selectedSource !== 'All sources') {
        const s = asset.source.toLowerCase()
        if (selectedSource === 'TradingView' && !s.includes('tradingview')) return false
        if (selectedSource === 'CoinMarketCap' && !s.includes('coinmarketcap')) return false
        if (selectedSource === 'Primary Exchanges' && !['nasdaq', 'nyse', 'london stock exchange', 'bombay stock exchange', 'national stock exchange', 'deutsche', 'euronext', 'hkex', 'tokyo stock exchange', 'six swiss', 'asx', 'krx', 'cboe', 'sp dow jones'].some(ex => s.includes(ex))) return false
        if (selectedSource === 'Commodities' && !['lbma', 'cme', 'ice', 'nymex', 'comex', 'cbot'].some(c => s.includes(c))) return false
        if (selectedSource === 'Central Banks' && !['bank of england', 'federal reserve', 'deutsche bundesbank', 'ministry of finance japan', 'bank of japan', 'reserve bank of india', 'ecb', 'ons', 'bls', 'swiss national bank', 'reserve bank of australia', 'bank of canada', "people's bank of china", 'eurostat', 'mospi', 'treasury', 'dmo'].some(cb => s.includes(cb))) return false
        if (selectedSource === 'UK DMO & Gilts' && !s.includes('dmo') && !s.includes('gilt') && !s.includes('bank of england')) return false
      }
      return true
    }).slice(0, 8)
  }, [searchQuery, selectedSource])

  // Handle outside click to close search dropdown
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target as Node)) {
        setIsSearchFocused(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Reset highlight index when query changes
  useEffect(() => {
    setSelectedSearchIndex(-1)
  }, [searchQuery])
  const [currentTime, setCurrentTime] = useState(() => new Date())
  const [overview, setOverview] = useState<DashboardOverviewResponse | null>(null)
  const { livePrices } = useLiveMarket()

  useEffect(() => {
    // Load real aggregated data from backend API
    void getDashboardOverview()
      .then((data) => {
        if (data) setOverview(data)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    // Tick every second to keep clocks accurate
    const timer = setInterval(() => {
      setCurrentTime(new Date())
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  // Dynamic greeting based on current local hour
  const getGreeting = () => {
    const hour = currentTime.getHours()
    if (hour < 12) return 'Good morning,'
    if (hour < 17) return 'Good afternoon,'
    return 'Good evening,'
  }

interface ClockItem {
  id: string
  label: string
  timeZone: string
}

const DEFAULT_CLOCKS: ClockItem[] = [
  { id: '1', label: 'London', timeZone: 'Europe/London' },
  { id: '2', label: 'New York', timeZone: 'America/New_York' },
  { id: '3', label: 'Tokyo', timeZone: 'Asia/Tokyo' },
]

const AVAILABLE_TIMEZONES = [
  { label: 'London (GMT/BST)', city: 'London', zone: 'Europe/London' },
  { label: 'New York (EST/EDT)', city: 'New York', zone: 'America/New_York' },
  { label: 'Tokyo (JST)', city: 'Tokyo', zone: 'Asia/Tokyo' },
  { label: 'Hong Kong (HKT)', city: 'Hong Kong', zone: 'Asia/Hong_Kong' },
  { label: 'Singapore (SGT)', city: 'Singapore', zone: 'Asia/Singapore' },
  { label: 'Frankfurt / Paris (CET/CEST)', city: 'Frankfurt', zone: 'Europe/Berlin' },
  { label: 'Zurich (CET)', city: 'Zurich', zone: 'Europe/Zurich' },
  { label: 'Sydney (AEST)', city: 'Sydney', zone: 'Australia/Sydney' },
  { label: 'Mumbai / Delhi (IST)', city: 'Mumbai', zone: 'Asia/Kolkata' },
  { label: 'Dubai (GST)', city: 'Dubai', zone: 'Asia/Dubai' },
  { label: 'Chicago (CST/CDT)', city: 'Chicago', zone: 'America/Chicago' },
  { label: 'San Francisco (PST/PDT)', city: 'San Francisco', zone: 'America/Los_Angeles' },
  { label: 'Toronto (EST/EDT)', city: 'Toronto', zone: 'America/Toronto' },
  { label: 'Sao Paulo (BRT)', city: 'São Paulo', zone: 'America/Sao_Paulo' },
  { label: 'Shanghai (CST)', city: 'Shanghai', zone: 'Asia/Shanghai' },
  { label: 'Seoul (KST)', city: 'Seoul', zone: 'Asia/Seoul' },
  { label: 'Johannesburg (SAST)', city: 'Johannesburg', zone: 'Africa/Johannesburg' },
]

  // Configurable user clocks (1 to 3 clocks stored in localStorage)
  const [clocks, setClocks] = useState<ClockItem[]>(() => {
    try {
      const saved = localStorage.getItem('talvrin_user_clocks')
      if (saved) {
        const parsed = JSON.parse(saved)
        if (Array.isArray(parsed) && parsed.length >= 1 && parsed.length <= 3) {
          return parsed
        }
      }
    } catch {
      // fallback
    }
    return DEFAULT_CLOCKS
  })
  const [isClockSettingsOpen, setIsClockSettingsOpen] = useState(false)
  const [editingClocks, setEditingClocks] = useState<ClockItem[]>(clocks)

  const saveClocks = (newClocks: ClockItem[]) => {
    setClocks(newClocks)
    try {
      localStorage.setItem('talvrin_user_clocks', JSON.stringify(newClocks))
    } catch {
      // ignore
    }
  }

  // Format real-time clock for a given IANA timezone
  const getZoneTime = (timeZone: string): { time: string; date: string } => {
    try {
      const timeFormatter = new Intl.DateTimeFormat('en-GB', {
        timeZone,
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      })
      const dateFormatter = new Intl.DateTimeFormat('en-GB', {
        timeZone,
        weekday: 'short',
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
      return {
        time: timeFormatter.format(currentTime),
        date: dateFormatter.format(currentTime),
      }
    } catch {
      return { time: '--:--', date: '---' }
    }
  }

  const handleSelectAsset = (asset: MarketAsset) => {
    setIsSearchFocused(false)
    setSelectedAssetForChart(asset)
  }

  const handleResearchAsset = (asset: MarketAsset) => {
    setIsSearchFocused(false)
    const prompt = `Provide institutional evidence, valuation analysis, and primary driver breakdown for ${asset.name} (${asset.symbol}).`
    onStartResearch(
      {
        symbol: asset.symbol,
        name: asset.name,
        assetClass: asset.assetClass,
        price: asset.price,
        change: asset.change,
        pctChange: asset.pctChange,
        direction: asset.direction,
        source: asset.source,
      },
      prompt
    )
  }

  const handleSearchSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    const q = searchQuery.trim()
    if (!q) return
    setIsSearchFocused(false)

    // If an asset in the dropdown is highlighted via ArrowDown, open that asset
    if (selectedSearchIndex >= 0 && selectedSearchIndex < matchedAssets.length) {
      handleSelectAsset(matchedAssets[selectedSearchIndex])
      return
    }

    // Check if query exactly or synonymously matches an asset
    if (matchedAssets.length > 0) {
      const exactMatch = matchedAssets.find(
        (a) =>
          a.symbol.toLowerCase() === q.toLowerCase() ||
          a.name.toLowerCase() === q.toLowerCase()
      )
      if (exactMatch) {
        handleSelectAsset(exactMatch)
        return
      }
    }

    onSearch(q)
  }

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedSearchIndex((prev) => (prev < matchedAssets.length - 1 ? prev + 1 : prev))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedSearchIndex((prev) => (prev > -1 ? prev - 1 : -1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      handleSearchSubmit()
    } else if (e.key === 'Escape') {
      setIsSearchFocused(false)
    }
  }

  const quickPills = [
    'Compare 10Y gilts vs 10Y Treasuries',
    'Bitcoin market cap & volume (CoinMarketCap)',
    'Gold spot price (LBMA)',
    'NVIDIA financials & TradingView chart',
    'S&P 500 & Global Equities benchmark',
  ]

  // Helper to convert numerical sparkline array [1, 2, 3] to SVG path string
  const toSvgPath = (points: number[] | string | undefined, isUp: boolean): string => {
    if (!points) {
      return isUp
        ? 'M0,22 C12,24 24,18 36,19 C48,15 60,12 72,14 C84,8 90,4 100,2'
        : 'M0,8 C12,10 24,7 36,15 C48,12 60,18 72,22 C84,18 90,24 100,22'
    }
    if (typeof points === 'string') return points
    if (!Array.isArray(points) || points.length === 0) {
      return isUp ? 'M0,25 L100,5' : 'M0,5 L100,25'
    }
    const min = Math.min(...points)
    const max = Math.max(...points)
    const range = max - min || 1
    const width = 100
    const height = 26
    const padding = 2

    return points
      .map((val, idx) => {
        const x = (idx / (points.length - 1)) * width
        // Invert y because SVG y=0 is top
        const normalized = (val - min) / range
        const y = height - padding - normalized * (height - 2 * padding)
        return `${idx === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(' ')
  }

  const defaultTickers = [
    {
      title: 'UK 10Y Gilt',
      value: '4.216%',
      change: '▼ 2.4 bps',
      isUp: false,
      isBps: true,
      sparkline: 'M0,18 C10,15 20,24 30,22 C40,20 50,26 60,18 C70,12 80,16 90,8',
    },
    {
      title: 'US 10Y Treasury',
      value: '4.327%',
      change: '▲ 1.1 bps',
      isUp: true,
      isBps: true,
      sparkline: 'M0,22 C12,24 24,18 36,19 C48,15 60,12 72,14 C84,8 90,4 100,2',
    },
    {
      title: 'S&P 500',
      value: '6,589.34',
      change: '▲ 0.62%',
      isUp: true,
      sparkline: 'M0,25 C15,22 25,26 35,20 C45,16 55,22 65,14 C75,10 85,12 95,2',
    },
    {
      title: 'Gold (XAU)',
      value: '$2,735.40',
      change: '▲ 0.67%',
      isUp: true,
      sparkline: 'M0,22 C12,20 24,18 36,15 48,16 60,12 72,10 84,6 90,4 100,2',
    },
    {
      title: 'BTC/USD',
      value: '$67,420',
      change: '▲ 2.82%',
      isUp: true,
      sparkline: 'M0,26 C12,22 24,19 36,21 48,16 60,12 72,14 84,6 90,4 100,2',
    },
    {
      title: 'FTSE 100',
      value: '8,261.40',
      change: '▲ 0.28%',
      isUp: true,
      sparkline: 'M0,24 C10,22 20,25 30,20 C40,16 50,19 60,14 C70,15 80,10 90,6',
    },
  ]

  // Dynamic tickers derived from live API overview or fallback, merged with live WebSocket stream
  const baseTickers = overview?.tickers && overview.tickers.length > 0
    ? overview.tickers.map((t) => ({
        title: t.title,
        value: t.value,
        change: t.change,
        isUp: t.is_up,
        isBps: t.is_bps,
        sparkline: toSvgPath(t.sparkline, t.is_up),
      }))
    : defaultTickers

  const tickers = baseTickers.map((t) => {
    const live = livePrices[t.title]
    if (!live) return t
    const isUp = live.direction === 'up'
    const isDown = live.direction === 'down'
    return {
      ...t,
      value: live.price,
      change: `${isUp ? '▲' : isDown ? '▼' : '—'} ${live.change}`,
      isUp,
    }
  })

  const keyDevelopments = [
    {
      time: '2h',
      dotColor: 'bg-emerald-400',
      title: 'US Treasury yields edge higher after strong retail sales data',
      tags: ['US Treasury', 'Economic Data', 'Macro'],
    },
    {
      time: '4h',
      dotColor: 'bg-emerald-400',
      title: 'UK inflation falls to 2.2% in August',
      tags: ['UK Economy', 'Inflation', 'BoE'],
    },
    {
      time: '6h',
      dotColor: 'bg-blue-400',
      title: 'NVIDIA announces new AI chip platform',
      tags: ['NVIDIA', 'Equities', 'Company Filings'],
    },
    {
      time: '8h',
      dotColor: 'bg-blue-400',
      title: 'ECB signals cautious approach to further cuts',
      tags: ['ECB', 'Monetary Policy', 'Euro Area'],
    },
    {
      time: '1d',
      dotColor: 'bg-blue-400',
      title: 'China industrial output beats expectations',
      tags: ['China', 'Economic Data', 'Asia'],
    },
  ]

  const defaultAlerts = [
    {
      title: 'US 10Y yield moved above 4.30%',
      time: '12 minutes ago',
      color: 'bg-amber-400',
    },
    {
      title: 'UK CPI data released',
      time: '2 hours ago',
      color: 'bg-emerald-400',
    },
    {
      title: 'NVIDIA filing updated (10-Q)',
      time: '6 hours ago',
      color: 'bg-blue-500',
    },
  ]

  // Dynamic user alerts from real Monitoring rule events in database
  const userAlerts = overview?.alerts && overview.alerts.length > 0
    ? overview.alerts.map((a) => {
        let dot = 'bg-blue-400'
        if (a.status === 'open' || a.status === 'triggered') dot = 'bg-amber-400'
        else if (a.status === 'acknowledged') dot = 'bg-blue-400'
        else if (a.status === 'resolved') dot = 'bg-emerald-400'
        return {
          title: a.title,
          time: a.time_ago,
          color: dot,
        }
      })
    : defaultAlerts

  const defaultCalendar = [
    { date: '18 Sep', time: '13:30', flag: '🇺🇸', code: 'US', event: 'Initial Jobless Claims' },
    { date: '18 Sep', time: '15:00', flag: '🇺🇸', code: 'US', event: 'Existing Home Sales' },
    { date: '19 Sep', time: '07:00', flag: '🇬🇧', code: 'UK', event: 'Retail Sales (MoM)' },
    { date: '19 Sep', time: '09:00', flag: '🇪🇺', code: 'EU', event: 'ECB President Speech' },
    { date: '19 Sep', time: '13:30', flag: '🇺🇸', code: 'US', event: 'Fed Balance Sheet' },
  ]

  const economicCalendar = overview?.economic_calendar && overview.economic_calendar.length > 0
    ? overview.economic_calendar.map((e) => ({
        date: e.date,
        time: e.time,
        flag: e.flag,
        code: e.code,
        event: e.event,
      }))
    : defaultCalendar

  const defaultResearch = [
    {
      id: '',
      title: 'Compare the 10Y gilt and 10Y Treasury',
      time: 'Last edited 2 hours ago',
      icon: BarChart3,
    },
    {
      id: '',
      title: 'NVIDIA - latest financial performance',
      time: 'Last edited 5 hours ago',
      icon: FileText,
    },
    {
      id: '',
      title: 'UK inflation analysis',
      time: 'Last edited 1 day ago',
      icon: BarChart3,
    },
    {
      id: '',
      title: 'Global central bank policy comparison',
      time: 'Last edited 2 days ago',
      icon: Bookmark,
    },
  ]

  // Map real user chats from Sidebar/App state if available
  const activeChats = chats.filter((c) => c.title && c.title !== 'New Research')
  const recentResearch = activeChats.length > 0
    ? activeChats.slice(0, 4).map((c) => ({
        id: c.id,
        title: c.title,
        time: 'Active investigation',
        icon: FileText,
      }))
    : defaultResearch

  const defaultWatchlists = [
    {
      id: 'default-1',
      title: 'Core Bonds',
      detail: '12 instruments',
      change: '▲ 0.18%',
      isUp: true,
      icon: Layers,
    },
    {
      id: 'default-2',
      title: 'Tech Leaders',
      detail: '8 instruments',
      change: '▲ 1.24%',
      isUp: true,
      icon: Cpu,
    },
    {
      id: 'default-3',
      title: 'UK Equities',
      detail: '15 instruments',
      change: '▲ 0.32%',
      isUp: true,
      icon: FileText,
    },
    {
      id: 'default-4',
      title: 'Global ETFs',
      detail: '10 instruments',
      change: '▼ 0.21%',
      isUp: false,
      icon: Layers,
    },
  ]

  // Real user watchlists from DB
  const savedWatchlists = overview?.watchlists && overview.watchlists.length > 0
    ? overview.watchlists.map((w) => ({
        id: w.id,
        title: w.title,
        detail: w.detail,
        change: w.change,
        isUp: w.is_up,
        icon: Layers,
      }))
    : defaultWatchlists

  return (
    <div className="flex-1 overflow-y-auto px-6 py-6 scrollbar-slim lg:px-10">
      <div className="mx-auto max-w-[1480px] space-y-6">
        {/* Top Header Row: Greeting + Live Market Timezones & Global Coverage */}
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
          <div>
            <div className="text-[13px] font-medium text-muted-foreground">{getGreeting()}</div>
            <div className="mt-0.5 flex flex-wrap items-center gap-3">
              <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
                Turn questions into evidence.
              </h1>
              <button
                type="button"
                onClick={() => {
                  if (onOpenGuides) onOpenGuides('how-to-use')
                  else window.open('/guides?topic=how-to-use', '_blank')
                }}
                className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-[12px] font-medium text-primary transition-all hover:bg-primary/20 hover:border-primary/50 active:scale-95 cursor-pointer shadow-sm shadow-primary/10"
              >
                <BookOpen className="h-3.5 w-3.5" />
                <span>User Guide</span>
                <ChevronRight className="h-3 w-3 opacity-70" />
              </button>
            </div>
            <p className="mt-1.5 text-[14px] text-muted-foreground">
              Search authoritative sources. Get clear answers. Make better decisions.
            </p>
          </div>

          <div className="relative flex shrink-0 items-center gap-4 sm:gap-5 rounded-xl border border-border/60 bg-card/60 px-4 py-2.5 backdrop-blur-md">
            {clocks.map((c, idx) => {
              const t = getZoneTime(c.timeZone)
              return (
                <React.Fragment key={c.id}>
                  {idx > 0 && <div className="h-7 w-px bg-border/80" />}
                  <div>
                    <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground truncate max-w-[100px]">
                      {c.label}
                    </div>
                    <div className="text-[14px] font-semibold font-mono text-foreground">{t.time}</div>
                    <div className="text-[10px] text-muted-foreground whitespace-nowrap">{t.date}</div>
                  </div>
                </React.Fragment>
              )
            })}

            <div className="h-7 w-px bg-border/80" />

            {/* Settings button to customize world clocks */}
            <button
              type="button"
              onClick={() => {
                setEditingClocks([...clocks])
                setIsClockSettingsOpen(true)
              }}
              title="Configure World Clocks (1 to 3)"
              className="grid h-7 w-7 place-items-center rounded-lg border border-border/80 bg-background/60 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            >
              <Settings className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Modal: Customize Market Clocks */}
        {isClockSettingsOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm animate-in fade-in duration-150">
            <div className="w-full max-w-md rounded-2xl border border-border/80 bg-card p-5 shadow-2xl space-y-4">
              <div className="flex items-center justify-between border-b border-border/60 pb-3">
                <div>
                  <h3 className="text-base font-semibold text-foreground">Market Timezone Settings</h3>
                  <p className="text-xs text-muted-foreground">
                    Customize up to 3 world clocks displayed on your dashboard.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setIsClockSettingsOpen(false)}
                  className="rounded-lg p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="space-y-3">
                {editingClocks.map((clock, index) => (
                  <div
                    key={clock.id}
                    className="flex items-center gap-2 rounded-xl border border-border/70 bg-background/50 p-3"
                  >
                    <div className="flex-1 space-y-2">
                      <div className="flex items-center gap-2">
                        <label className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                          Clock {index + 1} Label
                        </label>
                        <input
                          type="text"
                          value={clock.label}
                          onChange={(e) => {
                            const updated = [...editingClocks]
                            updated[index] = { ...updated[index], label: e.target.value }
                            setEditingClocks(updated)
                          }}
                          placeholder="e.g. London"
                          className="w-full rounded-md border border-border/70 bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                        />
                      </div>

                      <div className="flex items-center gap-2">
                        <label className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                          Timezone
                        </label>
                        <select
                          value={clock.timeZone}
                          onChange={(e) => {
                            const selectedOption = AVAILABLE_TIMEZONES.find((tz) => tz.zone === e.target.value)
                            const updated = [...editingClocks]
                            updated[index] = {
                              ...updated[index],
                              timeZone: e.target.value,
                              label: selectedOption ? selectedOption.city : updated[index].label,
                            }
                            setEditingClocks(updated)
                          }}
                          className="w-full rounded-md border border-border/70 bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer"
                        >
                          {AVAILABLE_TIMEZONES.map((tz) => (
                            <option key={tz.zone} value={tz.zone}>
                              {tz.label}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>

                    {editingClocks.length > 1 && (
                      <button
                        type="button"
                        onClick={() => {
                          setEditingClocks(editingClocks.filter((_, i) => i !== index))
                        }}
                        title="Remove clock"
                        className="rounded-lg p-2 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                ))}

                {editingClocks.length < 3 && (
                  <button
                    type="button"
                    onClick={() => {
                      const unusedZone =
                        AVAILABLE_TIMEZONES.find(
                          (tz) => !editingClocks.some((c) => c.timeZone === tz.zone)
                        ) || AVAILABLE_TIMEZONES[0]

                      setEditingClocks([
                        ...editingClocks,
                        {
                          id: String(Date.now()),
                          label: unusedZone.city,
                          timeZone: unusedZone.zone,
                        },
                      ])
                    }}
                    className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-border py-2.5 text-xs font-medium text-muted-foreground hover:border-primary/50 hover:bg-primary/5 hover:text-primary transition-all"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Add Another Timer ({editingClocks.length}/3)
                  </button>
                )}
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-border/60">
                <button
                  type="button"
                  onClick={() => {
                    setEditingClocks(DEFAULT_CLOCKS)
                  }}
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  Reset defaults
                </button>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setIsClockSettingsOpen(false)}
                    className="rounded-lg border border-border/80 px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (editingClocks.length >= 1 && editingClocks.length <= 3) {
                        saveClocks(editingClocks)
                        setIsClockSettingsOpen(false)
                      }
                    }}
                    className="flex items-center gap-1 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
                  >
                    <Check className="h-3.5 w-3.5" />
                    Save Clocks
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Master Search Bar & Filter with Live Autocomplete Dropdown */}
        <div ref={searchContainerRef} className="relative z-30 space-y-3">
          <form
            onSubmit={handleSearchSubmit}
            className="relative flex items-center gap-3 rounded-2xl border border-border/80 bg-card/95 px-4 py-3 shadow-lg shadow-black/25 ring-1 ring-border/40 backdrop-blur-xl focus-within:border-primary/80 focus-within:ring-2 focus-within:ring-primary/20"
          >
            <Search className="h-5 w-5 text-muted-foreground shrink-0" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value)
                setIsSearchFocused(true)
              }}
              onFocus={() => setIsSearchFocused(true)}
              onKeyDown={handleSearchKeyDown}
              placeholder="Search assets (BTC, Tata Steel, Gilts, NVDA), ticker aliases or research questions..."
              className="flex-1 bg-transparent text-[15px] text-foreground placeholder:text-muted-foreground focus:outline-none"
            />
            {searchQuery.trim().length > 0 && (
              <button
                type="button"
                onClick={() => {
                  setSearchQuery('')
                  setIsSearchFocused(false)
                }}
                title="Clear search"
                className="grid h-6 w-6 place-items-center rounded-md text-muted-foreground hover:bg-muted/60 hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
            <div className="flex items-center gap-2">
              <select
                value={selectedSource}
                onChange={(e) => setSelectedSource(e.target.value)}
                className="rounded-lg border border-border/80 bg-background/80 px-2.5 py-1.5 text-[12.5px] font-medium text-muted-foreground outline-none hover:text-foreground cursor-pointer"
              >
                <option value="All sources">All sources (Global)</option>
                <option value="TradingView">TradingView (Global Tape)</option>
                <option value="CoinMarketCap">CoinMarketCap (Crypto)</option>
                <option value="Primary Exchanges">Primary Exchanges (NYSE/NASDAQ/LSE/BSE/NSE)</option>
                <option value="Commodities">Commodities (LBMA/CME/ICE)</option>
                <option value="Central Banks">Central Banks (Fed/BoE/ECB/BoJ)</option>
                <option value="UK DMO & Gilts">UK DMO & Gilts</option>
                <option value="Tradeweb">Tradeweb</option>
                <option value="Twelve Data">Twelve Data</option>
                <option value="DBnomics">DBnomics</option>
              </select>
              <button
                type="submit"
                aria-label="Search"
                className="grid h-9 w-9 place-items-center rounded-xl bg-primary text-primary-foreground shadow-md transition-all hover:brightness-110 active:scale-95"
              >
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </form>

          {/* Live Search Results Dropdown Panel */}
          {isSearchFocused && searchQuery.trim().length > 0 && (
            <div className="absolute left-0 right-0 top-full mt-2 overflow-hidden rounded-2xl border border-border/80 bg-card/95 shadow-2xl backdrop-blur-xl ring-1 ring-black/40 animate-in fade-in zoom-in-95 duration-150 z-50">
              <div className="flex items-center justify-between border-b border-border/60 bg-muted/30 px-4 py-2 text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                <span>
                  {matchedAssets.length > 0
                    ? `Matching Assets (${matchedAssets.length})`
                    : 'Search Results'}
                </span>
                <span>Press Enter to select · Esc to close</span>
              </div>

              {matchedAssets.length > 0 ? (
                <div className="max-h-[380px] overflow-y-auto divide-y divide-border/40 scrollbar-slim">
                  {matchedAssets.map((asset, idx) => {
                    const isSelected = idx === selectedSearchIndex
                    const isUp = asset.direction === 'up'
                    return (
                      <div
                        key={`${asset.symbol}-${idx}`}
                        onClick={() => handleSelectAsset(asset)}
                        className={`group flex items-center justify-between gap-3 px-4 py-3 transition-colors cursor-pointer ${
                          isSelected ? 'bg-primary/10' : 'hover:bg-muted/40'
                        }`}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border/80 bg-background/80 text-xs font-bold text-foreground">
                            {asset.symbol.slice(0, 3)}
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-sm text-foreground truncate">
                                {asset.symbol}
                              </span>
                              <span className="rounded px-1.5 py-0.2 text-[10px] font-semibold uppercase tracking-wider bg-muted text-muted-foreground">
                                {asset.assetClass}
                              </span>
                              <span className="text-[10px] text-muted-foreground hidden sm:inline">
                                {asset.region}
                              </span>
                            </div>
                            <p className="text-xs text-muted-foreground truncate max-w-[280px] sm:max-w-md">
                              {asset.name}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-4 shrink-0">
                          <div className="hidden sm:block">
                            <MiniSparkline data={asset.sparkline} direction={asset.direction} />
                          </div>
                          <div className="text-right min-w-[70px]">
                            <div className="font-mono text-xs font-semibold text-foreground">
                              {asset.price}
                            </div>
                            <div
                              className={`flex items-center justify-end gap-0.5 text-[11px] font-medium ${
                                isUp ? 'text-emerald-500' : 'text-rose-500'
                              }`}
                            >
                              {isUp ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                              <span>{asset.pctChange}</span>
                            </div>
                          </div>

                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleResearchAsset(asset)
                            }}
                            title="Start AI deep research for this asset"
                            className="hidden md:inline-flex items-center gap-1 rounded-lg border border-primary/40 bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary hover:bg-primary/20 transition-colors"
                          >
                            <Sparkles className="h-3 w-3" />
                            <span>Evidence</span>
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="py-8 px-4 text-center">
                  <div className="flex h-11 w-11 mx-auto items-center justify-center rounded-2xl bg-muted/60 text-muted-foreground/80 border border-border/80 mb-2.5">
                    <Search className="h-5 w-5" />
                  </div>
                  <h4 className="text-sm font-semibold text-foreground">
                    No matching assets found for "{searchQuery}"
                  </h4>
                  <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
                    Try searching by asset ticker (e.g. BTC, ETH, TATASTEEL, AVGO), company name, or asset class.
                  </p>
                </div>
              )}

              {/* Action Bar Footer: Ask AI Research with full query */}
              <div className="border-t border-border/60 bg-muted/30 p-2.5">
                <button
                  type="button"
                  onClick={() => {
                    setIsSearchFocused(false)
                    onSearch(searchQuery.trim())
                  }}
                  className="w-full flex items-center justify-between gap-2 rounded-xl bg-primary/10 hover:bg-primary/20 border border-primary/30 px-3.5 py-2 text-xs font-medium text-primary transition-all text-left"
                >
                  <div className="flex items-center gap-2 truncate">
                    <Sparkles className="h-4 w-4 shrink-0 text-primary" />
                    <span className="truncate">
                      Ask AI Research: <strong className="font-semibold text-foreground">"{searchQuery}"</strong>
                    </span>
                  </div>
                  <div className="flex items-center gap-1 shrink-0 text-[11px] opacity-80">
                    <span>Evidence Mode</span>
                    <ArrowRight className="h-3.5 w-3.5" />
                  </div>
                </button>
              </div>
            </div>
          )}

          {/* Quick Filter Pill Buttons */}
          <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
            {quickPills.map((pill) => (
              <button
                key={pill}
                type="button"
                onClick={() => {
                  setSearchQuery(pill)
                  onSearch(pill)
                }}
                className="inline-flex items-center gap-1.5 rounded-full border border-border/60 bg-card/50 px-3.5 py-1 text-muted-foreground backdrop-blur-sm transition-colors hover:border-primary/50 hover:bg-card hover:text-foreground cursor-pointer"
              >
                <span>{pill}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Ticker Row */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6">
          {tickers.map((t) => (
            <div
              key={t.title}
              onClick={() => {
                if (onOpenMarkets) onOpenMarkets(t.title)
                else onSearch(t.title)
              }}
              title={`Click to view ${t.title} market chart`}
              className="institutional-card group relative flex cursor-pointer flex-col justify-between rounded-xl border border-border/70 bg-card/70 p-3.5 shadow-sm backdrop-blur-md hover:border-primary/50 hover:bg-card hover:shadow-md"
            >
              <div className="flex items-center justify-between gap-1.5 min-w-0">
                <div className="flex items-center gap-1 min-w-0 shrink">
                  <span className="text-[12px] font-medium text-muted-foreground group-hover:text-primary transition-colors truncate">
                    {t.title}
                  </span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      onSearch(t.title)
                    }}
                    title={`Research ${t.title}`}
                    className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-muted-foreground hover:text-primary hover:bg-primary/20 transition cursor-pointer shrink-0"
                  >
                    <Search className="h-3 w-3" />
                  </button>
                </div>
                <span
                  className={`inline-flex items-center whitespace-nowrap text-[11px] font-semibold shrink-0 ${
                    t.isUp ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {t.change}
                </span>
              </div>
              <div className="mt-2.5 flex items-baseline justify-between gap-2">
                <span className="text-[17px] font-bold tracking-tight text-foreground whitespace-nowrap">{t.value}</span>
                {/* SVG Sparkline */}
                <svg className="h-5 w-14 overflow-visible shrink-0" viewBox="0 0 100 30" fill="none">
                  <path
                    d={t.sparkline}
                    stroke={t.isUp ? '#34d399' : '#f87171'}
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
            </div>
          ))}

          <button
            onClick={() => {
              if (onOpenMarkets) onOpenMarkets()
              else onSearch('Global market overview')
            }}
            className="flex flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-border/80 bg-card/30 p-3.5 min-h-[78px] text-[12.5px] font-medium text-primary transition-all hover:border-primary/50 hover:bg-primary/5 active:scale-98"
          >
            <div className="flex items-center gap-1">
              <span>View all markets</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </div>
            <span className="text-[10.5px] text-muted-foreground font-normal">70+ global assets</span>
          </button>
        </div>

        {/* Main Grid: Hero Banner + Key Developments + Alerts & Economic Calendar */}
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
          {/* Left Column: Hero Banner (Deeper insight. Stronger decisions.) */}
          <div className="relative flex flex-col justify-between overflow-hidden rounded-2xl border border-border/80 bg-black/60 p-7 shadow-xl lg:col-span-4 min-h-[340px]">
            {/* Background space image */}
            <img
              src={earthImg}
              alt="Global view"
              className="absolute inset-0 h-full w-full object-cover object-center opacity-65 transition-transform duration-700 hover:scale-105"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-black via-black/40 to-transparent" />

            <div className="relative z-10 space-y-2">
              <span className="inline-block text-[10px] font-bold uppercase tracking-widest text-primary-foreground/90">
                GLOBAL MARKETS
              </span>
              <h2 className="text-2xl font-bold leading-tight text-white sm:text-3xl">
                Deeper insight.<br />Stronger decisions.
              </h2>
              <p className="text-[13px] text-white/80">
                Authoritative data. Verifiable sources.<br />A clearer view of what's next.
              </p>
            </div>

            <div className="relative z-10 pt-6">
              <button
                onClick={() => onStartResearch()}
                className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-[13px] font-semibold text-black shadow-lg transition-all hover:bg-white/90 active:scale-95"
              >
                <span>Start new research</span>
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Center Column: Key market developments */}
          <div className="flex flex-col justify-between rounded-2xl border border-border/70 bg-card/70 p-5 backdrop-blur-md lg:col-span-5">
            <div>
              <div className="flex items-center justify-between pb-3 border-b border-border/50">
                <h3 className="text-[14px] font-semibold text-foreground">Key market developments</h3>
                <button
                  onClick={() => onSearch('Latest market developments')}
                  className="flex items-center gap-1 text-[11.5px] font-medium text-primary hover:underline"
                >
                  View all <ArrowRight className="h-3 w-3" />
                </button>
              </div>

              <div className="mt-3 divide-y divide-border/40">
                {keyDevelopments.map((item, idx) => (
                  <div
                    key={idx}
                    onClick={() => onSearch(item.title)}
                    className="group flex cursor-pointer items-start gap-3 py-2.5 transition-colors hover:bg-accent/30 rounded-lg px-1.5"
                  >
                    <span className="w-5 shrink-0 text-[11.5px] font-mono text-muted-foreground">{item.time}</span>
                    <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${item.dotColor}`} />
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] font-medium text-foreground group-hover:text-primary leading-snug">
                        {item.title}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {item.tags.map((tag) => (
                          <span
                            key={tag}
                            className="rounded-md bg-secondary/80 px-1.5 py-0.5 text-[10px] text-muted-foreground"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right Column: Your Alerts & Economic Calendar */}
          <div className="space-y-4 lg:col-span-3">
            {/* Alerts Box */}
            <div className="rounded-2xl border border-border/70 bg-card/70 p-4 backdrop-blur-md">
              <div className="flex items-center justify-between pb-2 border-b border-border/50">
                <h3 className="text-[13px] font-semibold text-foreground">Your alerts</h3>
                <button
                  onClick={() => { if (onOpenMonitoring) onOpenMonitoring() }}
                  className="flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
                >
                  View all <ArrowRight className="h-3 w-3" />
                </button>
              </div>

              <div className="mt-2 space-y-2">
                {userAlerts.map((a, i) => (
                  <div
                    key={i}
                    onClick={() => { if (onOpenMonitoring) onOpenMonitoring() }}
                    className="flex cursor-pointer items-center justify-between rounded-xl border border-border/40 bg-background/50 p-2.5 transition-all hover:border-primary/40 hover:bg-background"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <span className={`h-2 w-2 shrink-0 rounded-full ${a.color}`} />
                      <Bell className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      <div className="min-w-0 truncate">
                        <div className="text-[12px] font-medium text-foreground truncate">{a.title}</div>
                        <div className="text-[10px] text-muted-foreground">{a.time}</div>
                      </div>
                    </div>
                    <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  </div>
                ))}
              </div>
            </div>

            {/* Economic Calendar */}
            <div className="rounded-2xl border border-border/70 bg-card/70 p-4 backdrop-blur-md">
              <div className="flex items-center justify-between pb-2 border-b border-border/50">
                <h3 className="text-[13px] font-semibold text-foreground">Economic calendar (next 5)</h3>
                <button
                  onClick={() => onSearch('Economic calendar schedule')}
                  className="flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
                >
                  View all <ArrowRight className="h-3 w-3" />
                </button>
              </div>

              <div className="mt-2 divide-y divide-border/40 text-[11.5px]">
                {economicCalendar.map((ec, i) => (
                  <div
                    key={i}
                    onClick={() => onSearch(`${ec.event} ${ec.code}`)}
                    className="flex cursor-pointer items-center justify-between gap-1.5 py-2 transition-colors hover:text-primary min-w-0"
                  >
                    <div className="flex items-center gap-1.5 min-w-0 flex-1">
                      <span className="font-mono text-muted-foreground shrink-0 text-[11px]">{ec.date}</span>
                      <span className="font-mono text-muted-foreground shrink-0 text-[11px]">{ec.time}</span>
                      <span className="text-[12px] shrink-0">{ec.flag}</span>
                      <span className="font-semibold text-foreground shrink-0">{ec.code}</span>
                      <span className="text-muted-foreground truncate flex-1 min-w-0" title={ec.event}>{ec.event}</span>
                    </div>
                    <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Bottom 3-Card Row: Continue Research + Saved Watchlists + The Talvrin Difference */}
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
          {/* Continue your research */}
          <div className="rounded-2xl border border-border/70 bg-card/70 p-5 backdrop-blur-md lg:col-span-4">
            <div className="flex items-center justify-between pb-3 border-b border-border/50">
              <h3 className="text-[14px] font-semibold text-foreground">Continue your research</h3>
              <button
                onClick={() => onStartResearch()}
                className="flex items-center gap-1 text-[11.5px] font-medium text-primary hover:underline"
              >
                View all <ArrowRight className="h-3 w-3" />
              </button>
            </div>

            <div className="mt-3 space-y-2">
              {recentResearch.map((item, idx) => (
                <div
                  key={idx}
                  onClick={() => {
                    if (item.id && onSelectChat) {
                      onSelectChat(item.id)
                    } else {
                      onSearch(item.title)
                    }
                  }}
                  className="flex cursor-pointer items-center justify-between rounded-xl border border-border/40 bg-background/50 p-2.5 transition-all hover:border-primary/40 hover:bg-background"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <item.icon className="h-4 w-4 shrink-0 text-primary" />
                    <div className="min-w-0">
                      <div className="text-[12.5px] font-medium text-foreground truncate">{item.title}</div>
                      <div className="text-[10.5px] text-muted-foreground">{item.time}</div>
                    </div>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                </div>
              ))}
            </div>
          </div>

          {/* Saved watchlists */}
          <div className="rounded-2xl border border-border/70 bg-card/70 p-5 backdrop-blur-md lg:col-span-4">
            <div className="flex items-center justify-between pb-3 border-b border-border/50">
              <h3 className="text-[14px] font-semibold text-foreground">Saved watchlists</h3>
              <button
                onClick={() => {
                  if (onOpenWatchlists) onOpenWatchlists()
                  else onSearch('Watchlists and market portfolios')
                }}
                className="flex items-center gap-1 text-[11.5px] font-medium text-primary hover:underline"
              >
                View all <ArrowRight className="h-3 w-3" />
              </button>
            </div>

            <div className="mt-3 space-y-2">
              {savedWatchlists.map((w, idx) => (
                <div
                  key={idx}
                  onClick={() => {
                    if (onOpenWatchlists) onOpenWatchlists()
                    else onSearch(w.title)
                  }}
                  className="flex cursor-pointer items-center justify-between rounded-xl border border-border/40 bg-background/50 p-2.5 transition-all hover:border-primary/40 hover:bg-background"
                >
                  <div className="flex items-center gap-3">
                    <w.icon className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <div className="text-[12.5px] font-medium text-foreground">{w.title}</div>
                      <div className="text-[10.5px] text-muted-foreground">{w.detail}</div>
                    </div>
                  </div>
                  <span
                    className={`text-[12px] font-semibold ${
                      w.isUp ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {w.change}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* The Talvrin Difference Banner */}
          <div className="relative flex flex-col justify-between overflow-hidden rounded-2xl border border-primary/40 bg-gradient-to-br from-indigo-950/80 via-purple-950/40 to-black p-5 shadow-xl backdrop-blur-xl lg:col-span-4">
            <div>
              <span className="text-[10.5px] font-bold uppercase tracking-wider text-primary">
                THE TALVRIN DIFFERENCE
              </span>
              <h3 className="mt-1 text-xl font-bold text-white">Every answer has a source.</h3>
              <p className="mt-1 text-[12.5px] text-white/70">
                Explore the evidence behind the numbers.
              </p>

              {/* Stack diagram */}
              <div className="mt-4 flex flex-col items-center justify-center py-2">
                <div className="relative flex w-full max-w-[210px] flex-col items-center gap-1.5 text-[11px] font-medium text-white/90">
                  <div className="w-full rounded-md border border-indigo-400/30 bg-indigo-600/40 py-1.5 text-center shadow">
                    Answer
                  </div>
                  <div className="w-[85%] rounded-md border border-indigo-500/30 bg-indigo-700/40 py-1.5 text-center shadow">
                    Analysis
                  </div>
                  <div className="w-[70%] rounded-md border border-indigo-600/30 bg-indigo-800/40 py-1.5 text-center shadow">
                    Data
                  </div>
                  <div className="w-[55%] rounded-md border border-indigo-700/30 bg-indigo-900/40 py-1.5 text-center shadow">
                    Source
                  </div>
                </div>
              </div>
            </div>

            <div className="pt-3">
              <button
                onClick={() => onStartResearch()}
                className="inline-flex items-center gap-2 rounded-xl bg-white px-3.5 py-2 text-[12px] font-semibold text-black shadow transition-all hover:bg-white/90 active:scale-95"
              >
                <span>Learn more</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex flex-col items-center justify-between gap-3 border-t border-border/50 pt-5 text-[11px] text-muted-foreground sm:flex-row pb-6">
          <div>© 2026 Talvrin. All rights reserved.</div>
          <div className="flex items-center gap-4">
            <span className="hover:text-foreground cursor-pointer">Terms</span>
            <span className="hover:text-foreground cursor-pointer">Privacy</span>
            <span className="hover:text-foreground cursor-pointer">Cookies</span>
            <span className="hover:text-foreground cursor-pointer">Disclaimers</span>
            <span className="hover:text-foreground cursor-pointer">Contact</span>
          </div>
        </div>
      </div>

      {/* Interactive Asset TradingView Modal on Click */}
      {selectedAssetForChart && (
        <TradingViewModal
          symbol={selectedAssetForChart.symbol}
          name={selectedAssetForChart.name}
          assetClass={selectedAssetForChart.assetClass}
          last={selectedAssetForChart.price}
          change={selectedAssetForChart.change}
          pctChange={selectedAssetForChart.pctChange}
          direction={selectedAssetForChart.direction}
          source={selectedAssetForChart.source}
          freshness={selectedAssetForChart.freshness}
          bitemporalStatus={selectedAssetForChart.bitemporalStatus}
          onClose={() => setSelectedAssetForChart(null)}
          onStartResearch={(asset, prompt) => {
            setSelectedAssetForChart(null)
            onStartResearch(asset, prompt)
          }}
          onOpenMonitoring={(symbol) => {
            setSelectedAssetForChart(null)
            if (onOpenMonitoring) onOpenMonitoring(symbol)
          }}
        />
      )}
    </div>
  )
}
