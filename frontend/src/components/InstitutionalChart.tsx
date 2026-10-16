import { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  CandlestickSeries,
  AreaSeries,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type AreaData,
  type WhitespaceData,
  type Time,
} from 'lightweight-charts'

interface InstitutionalChartProps {
  symbol: string
  baseValueStr: string
  timeframe: '1D' | '1W' | '1M' | '3M' | '1Y' | '5Y' | 'ALL'
  chartMode: 'candles' | 'area'
  onHoverQuote?: (point: {
    time: string
    open: number
    high: number
    low: number
    close: number
    volume: number
  } | null) => void
}

/**
 * Generates realistic chronological multi-timeframe OHLCV historical series.
 */
function generateHistoricalBars(
  baseStr: string,
  timeframe: string
): {
  candles: (CandlestickData<Time> | WhitespaceData<Time>)[]
  areas: (AreaData<Time> | WhitespaceData<Time>)[]
  volumes: { time: Time; value: number; color: string }[]
} {
  const clean = parseFloat(baseStr.replace(/[^0-9.-]/g, '')) || 100
  const isPercent = baseStr.includes('%')

  // Bar count and day span based on timeframe
  const barCount =
    timeframe === '1D'
      ? 48
      : timeframe === '1W'
      ? 35
      : timeframe === '1M'
      ? 30
      : timeframe === '3M'
      ? 65
      : timeframe === '1Y'
      ? 120
      : timeframe === '5Y'
      ? 200
      : 250

  const candles: CandlestickData<Time>[] = []
  const areas: AreaData<Time>[] = []
  const volumes: { time: Time; value: number; color: string }[] = []

  const now = new Date()

  // Generate a smooth geometric random walk ending exactly on the terminal value (Brownian Bridge)
  const vol = isPercent ? 0.008 : clean * 0.004
  const drift = 0.0

  // 1. Generate unconstrained walk
  const rawPath: number[] = [clean]
  let p = clean
  for (let i = 1; i < barCount; i++) {
    const shock = (Math.random() - 0.49) * 2
    p = p + drift + shock * vol
    if (isPercent) p = Math.max(0.1, p)
    else p = Math.max(clean * 0.2, p)
    rawPath.push(p)
  }

  // 2. Reverse path so it originates in the past and ties smoothly into current clean price
  rawPath.reverse()
  const diff = clean - rawPath[rawPath.length - 1]
  const bridgePath = rawPath.map((val, idx) => {
    // Linear bridge adjustment
    const adj = diff * (idx / (barCount - 1 || 1))
    return val + adj
  })

  // 3. Assemble OHLCV bars
  for (let i = 0; i < barCount; i++) {
    const daysAgo = barCount - 1 - i
    const d = new Date(now.getTime() - daysAgo * (timeframe === '1D' ? 30 * 60 * 1000 : 86400000))
    
    const timeVal = (
      timeframe === '1D'
        ? Math.floor(d.getTime() / 1000)
        : d.toISOString().split('T')[0]
    ) as Time

    const targetClose = bridgePath[i]
    const prevClose = i > 0 ? bridgePath[i - 1] : targetClose * (1 - (Math.random() - 0.5) * 0.002)
    const open = prevClose
    const close = targetClose

    const noise = (isPercent ? 0.012 : clean * 0.003) * Math.random()
    const high = Math.max(open, close) + noise
    const low = Math.min(open, close) - noise

    const volume = Math.floor(Math.random() * 95000 + 15000)
    const decimals = isPercent ? 3 : 2

    const roundedOpen = parseFloat(open.toFixed(decimals))
    const roundedClose = parseFloat(close.toFixed(decimals))
    const roundedHigh = parseFloat(high.toFixed(decimals))
    const roundedLow = parseFloat(low.toFixed(decimals))

    candles.push({
      time: timeVal,
      open: roundedOpen,
      high: roundedHigh,
      low: roundedLow,
      close: roundedClose,
    })

    areas.push({
      time: timeVal,
      value: roundedClose,
    })

    volumes.push({
      time: timeVal,
      value: volume,
      color: roundedClose >= roundedOpen ? 'rgba(16, 185, 129, 0.25)' : 'rgba(244, 63, 94, 0.25)',
    })
  }

  // Exact clamp on the final bar
  if (candles.length > 0) {
    const lastIdx = candles.length - 1
    candles[lastIdx].close = clean
    areas[lastIdx].value = clean
    candles[lastIdx].high = Math.max(candles[lastIdx].high, clean)
    candles[lastIdx].low = Math.min(candles[lastIdx].low, clean)
  }

  return { candles, areas, volumes }
}

export default function InstitutionalChart({
  symbol: _symbol,
  baseValueStr,
  timeframe,
  chartMode,
  onHoverQuote,
}: InstitutionalChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick' | 'Area'> | null>(null)

  useEffect(() => {
    const container = chartContainerRef.current
    if (!container) return

    // Clean previous chart
    if (chartRef.current) {
      chartRef.current.remove()
      chartRef.current = null
    }

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: '#090b0e' },
        textColor: '#94a3b8',
        fontSize: 11,
        fontFamily: "'Inter', monospace, sans-serif",
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
      },
      crosshair: {
        vertLine: {
          color: '#6366f1',
          width: 1,
          style: 3,
          labelBackgroundColor: '#4f46e5',
        },
        horzLine: {
          color: '#6366f1',
          width: 1,
          style: 3,
          labelBackgroundColor: '#4f46e5',
        },
      },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.1)',
        timeVisible: timeframe === '1D',
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.1)',
        scaleMargins: {
          top: 0.1,
          bottom: 0.2,
        },
      },
      autoSize: true,
    })

    chartRef.current = chart

    const { candles, areas } = generateHistoricalBars(baseValueStr, timeframe)

    let currentSeries: ISeriesApi<'Candlestick'> | ISeriesApi<'Area'>

    if (chartMode === 'candles') {
      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: '#10b981',
        downColor: '#f43f5e',
        borderUpColor: '#10b981',
        borderDownColor: '#f43f5e',
        wickUpColor: '#10b981',
        wickDownColor: '#f43f5e',
      })
      candleSeries.setData(candles)
      currentSeries = candleSeries
    } else {
      const areaSeries = chart.addSeries(AreaSeries, {
        topColor: 'rgba(99, 102, 241, 0.45)',
        bottomColor: 'rgba(99, 102, 241, 0.01)',
        lineColor: '#6366f1',
        lineWidth: 2,
      })
      areaSeries.setData(areas)
      currentSeries = areaSeries
    }

    seriesRef.current = currentSeries

    // Crosshair hover synchronization
    chart.subscribeCrosshairMove((param) => {
      if (!onHoverQuote) return

      if (
        !param.point ||
        !param.time ||
        param.point.x < 0 ||
        param.point.x > container.clientWidth ||
        param.point.y < 0 ||
        param.point.y > container.clientHeight
      ) {
        onHoverQuote(null)
        return
      }

      const data = param.seriesData.get(currentSeries) as
        | (CandlestickData<Time> & { volume?: number })
        | (AreaData<Time> & { volume?: number })
        | undefined

      if (data) {
        const timeStr = typeof param.time === 'string' ? param.time : new Date((param.time as number) * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        if ('open' in data) {
          onHoverQuote({
            time: timeStr,
            open: data.open,
            high: data.high,
            low: data.low,
            close: data.close,
            volume: 45000,
          })
        } else if ('value' in data) {
          onHoverQuote({
            time: timeStr,
            open: data.value,
            high: data.value,
            low: data.value,
            close: data.value,
            volume: 45000,
          })
        }
      } else {
        onHoverQuote(null)
      }
    })

    chart.timeScale().fitContent()

    // Handle container resize cleanly
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        })
      }
    }

    const resizeObserver = new ResizeObserver(handleResize)
    resizeObserver.observe(container)

    return () => {
      resizeObserver.disconnect()
      if (chartRef.current) {
        chartRef.current.remove()
        chartRef.current = null
      }
    }
  }, [baseValueStr, timeframe, chartMode, onHoverQuote])

  return (
    <div
      ref={chartContainerRef}
      className="relative h-full w-full min-h-0 overflow-hidden select-none"
      style={{ minHeight: '220px', height: '100%' }}
    />
  )
}
