import { useEffect, useRef, useState } from 'react'

declare global {
  interface Window {
    TradingView?: {
      widget: new (config: Record<string, unknown>) => void
    }
  }
}

interface TradingViewWidgetProps {
  symbol: string
  theme?: 'dark' | 'light'
  interval?: string
  // TradingView's own date-range selector value (e.g. '1D','5D','1M','3M',
  // '12M','60M','ALL') - controls which window of history is visible on
  // open, independent of `interval` (the bar/candle size). Without this,
  // every interval beyond the shortest one left the widget showing
  // whatever its own default history window happened to be, so switching
  // timeframe buttons past "1D" had no visible effect.
  range?: string
  timezone?: string
  onFallbackToNative?: () => void
  //: Fired once the embed has taken more than 4s to paint, in addition to
  //: this widget's own "taking longer than expected" message - lets a
  //: caller that has no legitimate fallback to offer (production, where
  //: there is no real OHLC source besides this embed) show an explicit
  //: unavailable state instead of leaving the spinner up indefinitely.
  onTimeout?: () => void
}

/**
 * Maps institutional / platform symbols to TradingView canonical symbols.
 * Covers UK Gilts, US Treasuries, Bunds, JGBs, Equities, FX, and Commodities.
 */
export function mapToTradingViewSymbol(symbol: string): string {
  const s = symbol.trim().toUpperCase()

  // Sovereign Fixed Income (Official TVC benchmarks). Only tenors confirmed
  // live to actually resolve on TradingView are mapped - a guessed symbol
  // that doesn't exist renders a wrong/misleading chart, whereas falling
  // through to the "no chart feed" state (below) is an honest result.
  if (s.includes('UK 10Y') || s.includes('GILT 10Y') || s === 'UK10Y' || s === 'GB10Y') return 'TVC:GB10Y'
  if (s.includes('UK 2Y') || s.includes('GILT 2Y') || s === 'UK02Y' || s === 'GB02Y') return 'TVC:GB02Y'
  if (s.includes('UK 5Y') || s.includes('GILT 5Y') || s === 'UK05Y' || s === 'GB05Y') return 'TVC:GB05Y'
  if (s.includes('UK 30Y') || s.includes('GILT 30Y') || s === 'UK30Y' || s === 'GB30Y') return 'TVC:GB30Y'
  if (s.includes('US 10Y') || s.includes('TREASURY 10Y') || s === 'US10Y') return 'TVC:US10Y'
  if (s.includes('US 2Y') || s.includes('TREASURY 2Y') || s === 'US02Y') return 'TVC:US02Y'
  if (s.includes('US 5Y') || s.includes('TREASURY 5Y') || s === 'US05Y') return 'TVC:US05Y'
  if (s.includes('US 20Y') || s.includes('TREASURY 20Y') || s === 'US20Y') return 'TVC:US20Y'
  if (s.includes('US 30Y') || s.includes('TREASURY 30Y') || s === 'US30Y') return 'TVC:US30Y'
  if (s.includes('DE 10Y') || s.includes('BUND') || s === 'DE10Y') return 'TVC:DE10Y'
  if (s.includes('DE 2Y') || s.includes('SCHATZ') || s === 'DE02Y') return 'TVC:DE02Y'
  if (s.includes('DE 30Y') || s === 'DE30Y') return 'TVC:DE30Y'
  if (s.includes('FR 10Y') || s.includes('OAT') || s === 'FR10Y') return 'TVC:FR10Y'
  if (s.includes('IT 10Y') || s.includes('BTP') || s === 'IT10Y') return 'TVC:IT10Y'
  if (s.includes('JP 10Y') || s.includes('JGB') || s === 'JP10Y') return 'TVC:JP10Y'
  if (s.includes('IN 10Y') || s.includes('G-SEC') || s === 'IN10Y') return 'TVC:IN10Y'

  // Equity Indices
  if (s.includes('S&P 500') || s === 'SPX' || s === 'SP500') return 'FOREXCOM:SPXUSD'
  if (s.includes('NASDAQ') || s === 'NDX') return 'FOREXCOM:NAS100'
  if (s.includes('DOW') || s === 'DJI' || s === 'DJIA') return 'FOREXCOM:DJI'
  if (s.includes('RUSSELL') || s === 'RUT') return 'FOREXCOM:US2000'
  if (s.includes('FTSE 100') || s === 'UKX' || s === 'FTSE') return 'FOREXCOM:UK100'
  if (s.includes('DAX') || s === 'GDAXI') return 'XETR:DAX'
  if (s.includes('CAC 40') || s === 'PX1') return 'EURONEXT:PX1'
  if (s.includes('EURO STOXX') || s.includes('STOXX 50') || s === 'SX5E') return 'FOREXCOM:EUSTX50'
  if (s.includes('NIKKEI') || s === 'NI225') return 'TVC:NI225'
  if (s.includes('HANG SENG') || s === 'HSI') return 'HSI:HSI'
  if (s === 'NIFTY' || s.includes('NIFTY 50')) return 'NSE:NIFTY'
  if (s === 'SENSEX' || s.includes('BSE SENSEX')) return 'BSE:SENSEX'

  // Mega-Cap & Global Equities
  if (s === 'AAPL' || s.includes('APPLE')) return 'NASDAQ:AAPL'
  if (s === 'MSFT' || s.includes('MICROSOFT')) return 'NASDAQ:MSFT'
  if (s === 'NVDA' || s.includes('NVIDIA')) return 'NASDAQ:NVDA'
  if (s === 'GOOGL' || s === 'GOOG' || s.includes('ALPHABET')) return 'NASDAQ:GOOGL'
  if (s === 'AMZN' || s.includes('AMAZON')) return 'NASDAQ:AMZN'
  if (s === 'META') return 'NASDAQ:META'
  if (s === 'TSLA' || s.includes('TESLA')) return 'NASDAQ:TSLA'
  if (s === 'ASML') return 'NASDAQ:ASML'
  if (s === 'LVMH' || s === 'MC') return 'EURONEXT:MC'
  if (s === 'SAP') return 'XETR:SAP'
  if (s === 'TSM' || s.includes('TSMC')) return 'NYSE:TSM'
  if (s === 'BABA' || s.includes('ALIBABA')) return 'NYSE:BABA'
  if (s === 'AZN' || s === 'AZN.L' || s.includes('ASTRAZENECA')) return 'LSE:AZN'
  if (s === 'SHEL' || s === 'SHEL.L' || s.includes('SHELL')) return 'LSE:SHEL'
  if (s === 'BP' || s === 'BP.L') return 'LSE:BP'
  if (s === 'ARM') return 'NASDAQ:ARM'
  if (s === 'AVGO' || s.includes('BROADCOM')) return 'NASDAQ:AVGO'
  if (s === 'LLY' || s.includes('LILLY')) return 'NYSE:LLY'
  if (s === 'NVO' || s.includes('NOVO NORDISK')) return 'NYSE:NVO'
  if (s === 'BRK.B' || s.includes('BERKSHIRE')) return 'NYSE:BRK.B'
  if (s === 'JPM' || s.includes('JPMORGAN')) return 'NYSE:JPM'
  if (s === 'V' || s.includes('VISA')) return 'NYSE:V'

  // Exchange Traded Funds (ETFs) & Baskets
  if (s === 'SPY') return 'AMEX:SPY'
  if (s === 'QQQ') return 'NASDAQ:QQQ'
  if (s === 'VOO') return 'AMEX:VOO'
  if (s === 'VTI') return 'AMEX:VTI'
  if (s === 'IWM') return 'AMEX:IWM'
  if (s === 'DIA') return 'AMEX:DIA'
  if (s === 'TLT') return 'NASDAQ:TLT'
  if (s === 'IEF') return 'NASDAQ:IEF'
  if (s === 'SHY') return 'NASDAQ:SHY'
  if (s === 'BND') return 'NASDAQ:BND'
  if (s === 'AGG') return 'AMEX:AGG'
  if (s === 'LQD') return 'AMEX:LQD'
  if (s === 'HYG') return 'AMEX:HYG'
  if (s === 'GLD') return 'AMEX:GLD'
  if (s === 'SLV') return 'AMEX:SLV'
  if (s === 'USO') return 'AMEX:USO'
  if (s === 'UNG') return 'AMEX:UNG'
  if (s === 'SMH') return 'NASDAQ:SMH'
  if (s === 'XLK') return 'AMEX:XLK'
  if (s === 'XLF') return 'AMEX:XLF'
  if (s === 'XLE') return 'AMEX:XLE'
  if (s === 'XLV') return 'AMEX:XLV'
  if (s === 'ARKK') return 'BATS:ARKK'
  if (s === 'EEM') return 'AMEX:EEM'
  if (s === 'INDA') return 'BATS:INDA'

  // Indian Equities & IPOs (NSE / BSE)
  if (s === 'SUZLON' || s.includes('SUZLON')) return 'NSE:SUZLON'
  if (s === 'RELIANCE' || s.includes('RELIANCE')) return 'NSE:RELIANCE'
  if (s === 'TCS' || s.includes('TCS')) return 'NSE:TCS'
  if (s === 'INFY' || s.includes('INFOSYS')) return 'NSE:INFY'
  if (s === 'HDFCBANK' || s.includes('HDFCBANK') || s === 'HDFCBANK:NSE') return 'NSE:HDFCBANK'
  if (s === 'TATAMOTORS' || s.includes('TATA MOTORS')) return 'NSE:TATAMOTORS'
  if (s === 'TATASTEEL' || s.includes('TATA STEEL')) return 'NSE:TATASTEEL'
  if (s === 'BSE') return 'BSE:BSE'
  if (s.includes('HYUNDAI')) return 'NSE:HYUNDAI'
  if (s.includes('SWIGGY')) return 'NSE:SWIGGY'
  if (s.includes('NTPCGREEN')) return 'NSE:NTPCGREEN'
  if (s === 'JPL' || s.includes('JPL')) return 'NSE:JPL'
  if (s.includes('JIO')) return 'NSE:RELIANCE' // Parent holding entity on NSE
  if (s.includes('NSE-IPO')) return 'BSE:BSE'

  // Institutional Mutual Funds & UCITS
  if (s === 'VFIAX') return 'MUTF:VFIAX'
  if (s === 'FXAIX') return 'MUTF:FXAIX'
  if (s === 'VWRL') return 'LSE:VWRL'
  if (s.includes('SBIBLUE')) return 'BSE:SBIBLUE'
  if (s.includes('PPFCF') || s.includes('PARAG')) return 'BSE:539000'
  if (s.includes('HDFCBAL')) return 'BSE:500180'
  if (s.includes('MIRAELE')) return 'BSE:532800'
  if (s.includes('NIPPONSM')) return 'BSE:540716'


  // Foreign Exchange
  if (s.includes('GBP/USD') || s === 'GBPUSD') return 'FX:GBPUSD'
  if (s.includes('EUR/USD') || s === 'EURUSD') return 'FX:EURUSD'
  if (s.includes('USD/JPY') || s === 'USDJPY') return 'FX:USDJPY'
  if (s.includes('USD/CHF') || s === 'USDCHF') return 'FX:USDCHF'
  if (s.includes('AUD/USD') || s === 'AUDUSD') return 'FX:AUDUSD'
  if (s.includes('USD/CAD') || s === 'USDCAD') return 'FX:USDCAD'
  if (s.includes('USD/INR') || s === 'USDINR') return 'FX_IDC:USDINR'
  if (s.includes('EUR/GBP') || s === 'EURGBP') return 'FX:EURGBP'

  // Commodities & Energy
  if (s.includes('BRENT') || s.includes('UKOIL')) return 'TVC:UKOIL'
  if (s.includes('WTI') || s.includes('USOIL') || (s.includes('CRUDE') && !s.includes('BRENT'))) return 'TVC:USOIL'
  if (s.includes('GOLD') || s.includes('XAU')) return 'TVC:GOLD'
  if (s.includes('SILVER') || s.includes('XAG')) return 'TVC:SILVER'
  if (s.includes('NATURAL GAS') || s === 'NG' || s.includes('NATGAS')) return 'TVC:NATGAS'
  if (s.includes('COPPER') || s === 'HG') return 'COMEX:HG1!'
  if (s.includes('PLATINUM') || s === 'PL') return 'NYMEX:PL1!'

  // Cryptocurrencies (CoinMarketCap & TradingView)
  if (s.includes('BTC') || s === 'BITCOIN') return 'BINANCE:BTCUSDT'
  if (s.includes('ETH') || s === 'ETHEREUM') return 'BINANCE:ETHUSDT'
  if (s.includes('SOL') || s === 'SOLANA') return 'BINANCE:SOLUSDT'
  if (s.includes('BNB') || s.includes('BINANCE')) return 'BINANCE:BNBUSDT'
  if (s.includes('XRP') || s === 'RIPPLE') return 'BINANCE:XRPUSDT'
  if (s.includes('ADA') || s === 'CARDANO') return 'BINANCE:ADAUSDT'
  if (s.includes('DOGE') || s === 'DOGECOIN') return 'BINANCE:DOGEUSDT'
  if (s.includes('AVAX') || s === 'AVALANCHE') return 'BINANCE:AVAXUSDT'
  if (s.includes('LINK') || s === 'CHAINLINK') return 'BINANCE:LINKUSDT'
  if (s.includes('DOT') || s === 'POLKADOT') return 'BINANCE:DOTUSDT'
  if (s.includes('NEAR')) return 'BINANCE:NEARUSDT'
  if (s.includes('SUI')) return 'BINANCE:SUIUSDT'
  if (s.includes('UNI') || s === 'UNISWAP') return 'BINANCE:UNIUSDT'
  if (s.includes('TON') || s === 'TONCOIN') return 'OKX:TONUSDT'
  if (s.includes('POL') || s.includes('MATIC') || s === 'POLYGON') return 'BINANCE:POLUSDT'
  if (s.includes('LTC') || s === 'LITECOIN') return 'BINANCE:LTCUSDT'

  // Clean raw symbol if already in TICKER or EXCHANGE:TICKER format
  return symbol.replace(/\s+/g, '')
}

export default function TradingViewWidget({
  symbol,
  theme = 'dark',
  interval = 'D',
  range,
  timezone = 'Etc/UTC',
  onFallbackToNative,
  onTimeout,
}: TradingViewWidgetProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const tvSymbol = mapToTradingViewSymbol(symbol)
  const [loading, setLoading] = useState(true)
  const [overlayVisible, setOverlayVisible] = useState(true)
  const [loadTimedOut, setLoadTimedOut] = useState(false)
  // Mirrors `loading` for the hard timeout's setTimeout closure below, which
  // otherwise captures the stale `loading` value from the render it was
  // scheduled in and can never see the script.onload handler's later update.
  const loadingRef = useRef(true)
  // A caller's `onTimeout` is not guaranteed to be referentially stable (e.g.
  // TradingViewModal passes a fresh inline arrow function on every render in
  // production builds, where isProdBuild gates it on). If `onTimeout` sat in
  // the mount effect's dependency array below, every parent re-render -
  // routine in production, where live price ticks re-render the modal
  // constantly - would tear down and rebuild the whole TradingView iframe,
  // repeatedly resetting the loading overlay. Mirroring it in a ref read at
  // call time keeps the effect scoped to things that actually describe a
  // different chart (symbol/theme/interval/range/timezone), never a caller's
  // callback identity.
  const onTimeoutRef = useRef(onTimeout)
  onTimeoutRef.current = onTimeout

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    loadingRef.current = true
    setLoading(true)
    setOverlayVisible(true)
    setLoadTimedOut(false)

    container.innerHTML = ''

    const widgetContainer = document.createElement('div')
    widgetContainer.className = 'tradingview-widget-container__widget'
    widgetContainer.style.width = '100%'
    widgetContainer.style.height = '100%'
    container.appendChild(widgetContainer)

    const script = document.createElement('script')
    script.type = 'text/javascript'
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js'
    script.async = true
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: tvSymbol,
      interval,
      ...(range ? { range } : {}),
      timezone,
      theme,
      style: '1',
      locale: 'en',
      enable_publishing: false,
      // 2026-11-12 P0 remediation: `true` here let a user change the
      // displayed symbol from INSIDE the TradingView iframe's own search UI,
      // entirely independent of this app's selected-instrument state - our
      // header (driven by React props) would keep showing the original
      // instrument while the embedded chart silently showed whatever the
      // user searched for inside it. Confirmed as the root cause of a P0
      // header/chart identity mismatch (NIFTY 50 header, AAPL chart data)
      // found while live-testing the chart-switching fix in
      // TradingViewModal.tsx. False makes this app the only way to change
      // what's displayed, so header and chart can never disagree.
      allow_symbol_change: false,
      calendar: false,
      support_host: 'https://www.tradingview.com',
    })

    // This embed type (TradingView's lightweight iframe snippet, not the
    // full Charting Library) exposes no postMessage/onReady handshake this
    // page can listen for - script.onload only confirms the bootstrap
    // script itself downloaded, not that the iframe has actually painted a
    // chart. A single fixed delay here is a guess, and guessing wrong in
    // either direction causes a real, observed bug: too short, and the
    // overlay disappears into TradingView's own black-screen-with-white-dot
    // loading state (the "double loader flash"); too long, and a fast
    // symbol sits behind our spinner needlessly. 2600ms is long enough for
    // the common case without being needlessly conservative, and the
    // opacity fade below means a slightly-early reveal is a soft crossfade
    // into TradingView's own state rather than an abrupt cut.
    script.onload = () => {
      setTimeout(() => {
        loadingRef.current = false
        setLoading(false)
      }, 2600)
    }

    container.appendChild(script)

    // Two-stage timeout, not one: a symbol can be entirely valid and still
    // take much longer than 4s to resolve (confirmed live:
    // FOREXCOM:DJI - a genuinely valid, correctly-mapped symbol - routinely
    // took 5-7s to paint real data during testing). Firing onTimeout at 4s
    // misclassifies a slow-but-working chart as "unavailable" - a false
    // negative, not a real failure. The soft threshold only shows the
    // reassuring "taking longer than expected" message; only the hard
    // threshold actually gives up and calls onTimeout - and only if the
    // widget genuinely never finished (loadingRef still true), so a chart
    // that already loaded successfully is never yanked into an "unavailable"
    // error state just because this timer happened to fire later.
    const softTimer = setTimeout(() => setLoadTimedOut(true), 4000)
    const hardTimer = setTimeout(() => {
      if (loadingRef.current) onTimeoutRef.current?.()
    }, 9000)

    return () => {
      clearTimeout(softTimer)
      clearTimeout(hardTimer)
      container.innerHTML = ''
    }
  }, [tvSymbol, theme, interval, range, timezone])

  // Fades the custom overlay out over 400ms instead of unmounting it the
  // instant `loading` flips false, so any gap between our guessed "ready"
  // moment and the iframe's real paint is a smooth crossfade rather than a
  // hard cut exposing TradingView's own loading animation underneath.
  useEffect(() => {
    if (loading) {
      setOverlayVisible(true)
      return
    }
    const fadeTimer = setTimeout(() => setOverlayVisible(false), 400)
    return () => clearTimeout(fadeTimer)
  }, [loading])

  return (
    <div className="relative h-full w-full min-h-0 overflow-hidden rounded-xl bg-[#090b0e]">
      <div
        ref={containerRef}
        className="tradingview-widget-container relative h-full w-full min-h-0 overflow-hidden rounded-xl bg-[#090b0e]"
        style={{ minHeight: '220px', height: '100%' }}
      />

      {overlayVisible && (
        <div
          className={`absolute inset-0 z-10 flex flex-col items-center justify-center bg-[#090b0e]/85 backdrop-blur-sm p-4 text-center transition-opacity [transition-duration:400ms] ease-out ${loading ? '' : 'pointer-events-none'}`}
          style={{ opacity: loading ? 1 : 0 }}
        >
          <div className="h-6 w-6 institutional-spinner mb-3" />
          <span className="text-[12.5px] font-medium text-white tracking-tight">Connecting to TradingView Feed ({tvSymbol})…</span>
          <span className="text-[11px] text-muted-foreground mt-0.5">Streaming institutional market feeds</span>

          {loadTimedOut && (
            <div className="mt-3 flex flex-col items-center gap-2">
              <span className="text-[11px] text-amber-400/90 max-w-xs">
                TradingView embed taking longer than expected. If third-party iframes are restricted by browser or adblocker:
              </span>
              {onFallbackToNative && (
                <button
                  type="button"
                  onClick={onFallbackToNative}
                  className="rounded-lg bg-primary/20 border border-primary/30 px-3 py-1 text-[11.5px] font-medium text-primary hover:bg-primary hover:text-white transition cursor-pointer"
                >
                  Switch to Native Institutional Chart
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
