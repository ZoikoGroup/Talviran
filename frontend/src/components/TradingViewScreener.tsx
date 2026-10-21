import { useEffect, useRef, useState } from 'react'
import { Search, Tag } from 'lucide-react'
import type { TaggedAsset } from '@/data/mockReply'

export type TradingViewMarket =
  | 'america'
  | 'uk'
  | 'india'
  | 'germany'
  | 'france'
  | 'japan'
  | 'canada'
  | 'australia'
  | 'brazil'
  | 'china'
  | 'hongkong'
  | 'singapore'
  | 'crypto'
  | 'forex'

interface TradingViewScreenerProps {
  initialMarket?: TradingViewMarket
  defaultScreen?: 'most_capitalized' | 'general' | 'top_gainers' | 'top_losers' | 'ath'
  height?: number | string
  colorTheme?: 'dark' | 'light'
  onStartResearch?: (assetOrQuery: string | TaggedAsset) => void
}

const SUPPORTED_MARKETS: { id: TradingViewMarket; label: string; short: string; flag: string }[] = [
  { id: 'america', label: 'United States', short: 'US', flag: '🇺🇸' },
  { id: 'uk', label: 'United Kingdom', short: 'UK', flag: '🇬🇧' },
  { id: 'india', label: 'India (NSE / BSE)', short: 'India', flag: '🇮🇳' },
  { id: 'germany', label: 'Germany (XETRA)', short: 'Germany', flag: '🇩🇪' },
  { id: 'france', label: 'France (Euronext)', short: 'France', flag: '🇫🇷' },
  { id: 'japan', label: 'Japan (TSE)', short: 'Japan', flag: '🇯🇵' },
  { id: 'canada', label: 'Canada (TSX)', short: 'Canada', flag: '🇨🇦' },
  { id: 'australia', label: 'Australia (ASX)', short: 'Australia', flag: '🇦🇺' },
  { id: 'china', label: 'China (SSE/SZSE)', short: 'China', flag: '🇨🇳' },
  { id: 'hongkong', label: 'Hong Kong (HKEX)', short: 'Hong Kong', flag: '🇭🇰' },
  { id: 'singapore', label: 'Singapore (SGX)', short: 'Singapore', flag: '🇸🇬' },
  { id: 'brazil', label: 'Brazil (B3)', short: 'Brazil', flag: '🇧🇷' },
  { id: 'crypto', label: 'Global Crypto', short: 'Crypto', flag: '🪙' },
  { id: 'forex', label: 'Global FX', short: 'FX', flag: '💱' },
]

const MARKET_QUICK_TAGS: Record<TradingViewMarket, { symbol: string; name: string }[]> = {
  india: [
    { symbol: 'BSE', name: 'BSE Limited (Bombay Stock Exchange)' },
    { symbol: 'BSE SENSEX', name: 'S&P BSE SENSEX' },
    { symbol: 'NIFTY 50', name: 'NIFTY 50 Benchmark' },
    { symbol: 'RELIANCE', name: 'Reliance Industries' },
    { symbol: 'TCS', name: 'Tata Consultancy Services' },
    { symbol: 'TATAMOTORS', name: 'Tata Motors' },
  ],
  america: [
    { symbol: 'S&P 500', name: 'S&P 500 Index' },
    { symbol: 'AAPL', name: 'Apple Inc.' },
    { symbol: 'NVDA', name: 'NVIDIA Corp' },
    { symbol: 'MSFT', name: 'Microsoft Corp' },
    { symbol: 'TSLA', name: 'Tesla Inc.' },
  ],
  uk: [
    { symbol: 'UK 10Y Gilt', name: 'UK 10-Year Benchmark Gilt' },
    { symbol: 'FTSE 100', name: 'FTSE 100 Index' },
    { symbol: 'AZN.L', name: 'AstraZeneca PLC' },
    { symbol: 'SHEL.L', name: 'Shell PLC' },
  ],
  germany: [
    { symbol: 'DE 10Y Bund', name: 'Germany 10-Year Bund' },
    { symbol: 'DAX', name: 'DAX 40 Index' },
    { symbol: 'SAP', name: 'SAP SE' },
  ],
  france: [
    { symbol: 'CAC 40', name: 'CAC 40 Index' },
    { symbol: 'LVMH', name: 'LVMH Moët Hennessy' },
  ],
  japan: [
    { symbol: 'JP 10Y JGB', name: 'Japan 10-Year JGB' },
    { symbol: 'Nikkei 225', name: 'Nikkei 225 Index' },
    { symbol: '7203', name: 'Toyota Motor Corp' },
  ],
  canada: [
    { symbol: 'TSX', name: 'S&P/TSX Composite' },
    { symbol: 'SHOP', name: 'Shopify Inc.' },
  ],
  australia: [
    { symbol: 'ASX 200', name: 'S&P/ASX 200' },
    { symbol: 'BHP', name: 'BHP Group' },
  ],
  brazil: [
    { symbol: 'IBOV', name: 'Ibovespa Index' },
    { symbol: 'PETR4', name: 'Petrobras' },
  ],
  china: [
    { symbol: 'SSE', name: 'Shanghai Composite' },
    { symbol: '600519', name: 'Kweichow Moutai' },
  ],
  hongkong: [
    { symbol: 'HSI', name: 'Hang Seng Index' },
    { symbol: '0700', name: 'Tencent Holdings' },
  ],
  singapore: [
    { symbol: 'STI', name: 'Straits Times Index' },
    { symbol: 'DBS', name: 'DBS Group' },
  ],
  crypto: [
    { symbol: 'BTC/USD', name: 'Bitcoin' },
    { symbol: 'ETH/USD', name: 'Ethereum' },
    { symbol: 'SOL/USD', name: 'Solana' },
  ],
  forex: [
    { symbol: 'GBP/USD', name: 'British Pound / US Dollar' },
    { symbol: 'EUR/USD', name: 'Euro / US Dollar' },
    { symbol: 'USD/JPY', name: 'US Dollar / Japanese Yen' },
  ],
}

export default function TradingViewScreener({
  initialMarket = 'america',
  defaultScreen = 'most_capitalized',
  height = 720,
  colorTheme = 'dark',
  onStartResearch,
}: TradingViewScreenerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [selectedMarket, setSelectedMarket] = useState<TradingViewMarket>(initialMarket)
  const [screenerQuery, setScreenerQuery] = useState('')

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    container.innerHTML = ''

    const widgetContainer = document.createElement('div')
    widgetContainer.className = 'tradingview-widget-container__widget'
    widgetContainer.style.width = '100%'
    widgetContainer.style.height = '100%'
    container.appendChild(widgetContainer)

    const script = document.createElement('script')
    script.type = 'text/javascript'
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-screener.js'
    script.async = true
    script.innerHTML = JSON.stringify({
      width: '100%',
      height: '100%',
      defaultColumn: 'overview',
      defaultScreen,
      market: selectedMarket,
      showToolbar: true,
      colorTheme,
      locale: 'en',
      isTransparent: true,
    })

    container.appendChild(script)

    return () => {
      container.innerHTML = ''
    }
  }, [selectedMarket, defaultScreen, colorTheme])

  const handleScreenerAsk = (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    const q = screenerQuery.trim()
    if (!q || !onStartResearch) return
    onStartResearch(q)
  }

  const currentTags = MARKET_QUICK_TAGS[selectedMarket] || []

  return (
    <div className="flex flex-col gap-3 w-full">
      {/* Top Ask Talvrin Research & Country Selector Bar */}
      <div className="flex flex-col gap-2.5 rounded-xl border border-border bg-[#101318] p-3 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* Ask Talvrin Search Bar */}
          <form onSubmit={handleScreenerAsk} className="flex items-center gap-2 flex-1 min-w-[280px] max-w-xl">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
              <input
                type="text"
                value={screenerQuery}
                onChange={(e) => setScreenerQuery(e.target.value)}
                placeholder="Ask Talvrin about any stock or instrument in this screener (e.g. BSE, AAPL, RELIANCE)…"
                className="w-full rounded-lg border border-border/80 bg-[#151922] pl-8 pr-3 py-1.5 text-[12px] text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary/80 focus:ring-1 focus:ring-primary/20"
              />
            </div>
            <button
              type="submit"
              disabled={!screenerQuery.trim()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-[12px] font-semibold text-primary-foreground shadow-sm hover:opacity-90 transition active:scale-95 disabled:opacity-50 disabled:pointer-events-none shrink-0"
            >
              <Search className="h-3.5 w-3.5" />
              <span>Research</span>
            </button>
          </form>

          {/* Country Market Dropdown */}
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-[11.5px] font-medium text-muted-foreground">Market:</span>
            <select
              value={selectedMarket}
              onChange={(e) => setSelectedMarket(e.target.value as TradingViewMarket)}
              className="rounded-lg border border-border bg-[#181c24] px-2.5 py-1.5 text-[12px] font-semibold text-white focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer"
            >
              {SUPPORTED_MARKETS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.flag} {m.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Quick Tag Chips Row for Current Market */}
        <div className="flex flex-wrap items-center gap-1.5 pt-1 border-t border-border/40 text-[11px]">
          <span className="flex items-center gap-1 text-muted-foreground font-medium shrink-0 mr-1">
            <Tag className="h-3 w-3 text-primary" />
            <span>Research tags:</span>
          </span>
          {currentTags.map((tag) => (
            <button
              key={tag.symbol}
              type="button"
              onClick={() => onStartResearch && onStartResearch({ symbol: tag.symbol, name: tag.name, assetClass: 'EQUITY', source: 'Primary Market' })}
              title={`Research ${tag.name}`}
              className="inline-flex items-center gap-1 rounded-md border border-border/80 bg-secondary/60 px-2 py-0.5 font-medium text-foreground hover:bg-primary hover:text-primary-foreground hover:border-primary transition shadow-xs cursor-pointer active:scale-95"
            >
              <span>{tag.symbol}</span>
            </button>
          ))}

          {/* Region Tabs */}
          <div className="ml-auto hidden md:flex items-center gap-1 overflow-x-auto text-[11px] shrink-0 pl-2">
            <span className="text-[10.5px] text-muted-foreground mr-0.5">Quick switch:</span>
            {SUPPORTED_MARKETS.slice(0, 6).map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => setSelectedMarket(m.id)}
                className={`rounded-md px-2 py-0.5 font-semibold transition text-[11px] cursor-pointer ${
                  selectedMarket === m.id
                    ? 'bg-primary/20 text-primary border border-primary/30 shadow-xs'
                    : 'text-muted-foreground hover:bg-white/5 hover:text-white'
                }`}
              >
                {m.short}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div
        ref={containerRef}
        className="tradingview-widget-container relative w-full overflow-hidden rounded-xl border border-border bg-[#0d0f14]"
        style={{
          minHeight: '780px',
          height: typeof height === 'number' ? `${height}px` : height || '780px',
        }}
      />
    </div>
  )
}

