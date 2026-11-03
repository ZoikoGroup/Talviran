import React, { createContext, useContext, useEffect, useState, useRef } from 'react'
import { API_BASE } from '@/lib/api'

export interface LiveTick {
  symbol: string
  price: string
  rawPrice: number
  direction: 'up' | 'down' | 'flat'
  change: string
  timestamp: string
}

interface LiveMarketContextType {
  livePrices: Record<string, LiveTick>
  isConnected: boolean
  lastUpdated: string | null
}

const LiveMarketContext = createContext<LiveMarketContextType>({
  livePrices: {},
  isConnected: false,
  lastUpdated: null,
})

export function LiveMarketProvider({ children }: { children: React.ReactNode }) {
  const [livePrices, setLivePrices] = useState<Record<string, LiveTick>>({})
  const [isConnected, setIsConnected] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let active = true
    let attempt = 0
    const BASE_BACKOFF_MS = 1500
    const MAX_BACKOFF_MS = 30000

    const scheduleReconnect = () => {
      if (!active) return
      if (reconnectTimer) clearTimeout(reconnectTimer)

      // Exponential backoff: BASE * 2^attempt capped at 30s, plus 25% random jitter
      const expDelay = Math.min(BASE_BACKOFF_MS * Math.pow(1.5, attempt), MAX_BACKOFF_MS)
      const jitter = expDelay * 0.25 * (Math.random() * 2 - 1)
      const delay = Math.max(1000, Math.round(expDelay + jitter))

      attempt++
      reconnectTimer = setTimeout(connect, delay)
    }

    const connect = () => {
      if (!active) return
      try {
        // Must derive from the real API host (API_BASE, same source of
        // truth every other request uses), never the page's own host -
        // in production the frontend (app.talvrin.com) and the API are on
        // different hosts, so building this from window.location silently
        // points the socket at the wrong server there.
        const wsUrl = `${API_BASE.replace(/^http/, 'ws')}/api/v1/sync/ws`

        const ws = new WebSocket(wsUrl)
        wsRef.current = ws

        ws.onopen = () => {
          if (!active) return
          setIsConnected(true)
          attempt = 0 // Reset backoff counter on successful connection
        }

        ws.onmessage = (event) => {
          if (!active) return
          try {
            const data = JSON.parse(event.data)
            if (data.type === 'TICK' && Array.isArray(data.ticks)) {
              setLivePrices((prev) => {
                const next = { ...prev }
                data.ticks.forEach((t: LiveTick) => {
                  next[t.symbol] = t
                })
                return next
              })
              setLastUpdated(data.timestamp || new Date().toISOString())
            }
          } catch {
            // ignore JSON parse issue
          }
        }

        ws.onclose = () => {
          if (!active) return
          setIsConnected(false)
          scheduleReconnect()
        }

        ws.onerror = () => {
          ws.close()
        }
      } catch {
        scheduleReconnect()
      }
    }

    connect()

    return () => {
      active = false
      if (reconnectTimer) clearTimeout(reconnectTimer)
      wsRef.current?.close()
    }
  }, [])

  return (
    <LiveMarketContext.Provider value={{ livePrices, isConnected, lastUpdated }}>
      {children}
    </LiveMarketContext.Provider>
  )
}

export function useLiveMarket() {
  return useContext(LiveMarketContext)
}
