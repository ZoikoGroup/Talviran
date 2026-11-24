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
  //: True once a TICK frame with `simulated: true` has been received - the
  //: backend only ever sends this outside production (sync.py's
  //: live_market_websocket refuses to serve simulated ticks in production
  //: at all). Consumers must show prices as simulated, not live, whenever
  //: this is true, and must never treat them as grounds for a real alert.
  isSimulated: boolean
}

const LiveMarketContext = createContext<LiveMarketContextType>({
  livePrices: {},
  isConnected: false,
  lastUpdated: null,
  isSimulated: false,
})

export function LiveMarketProvider({ children }: { children: React.ReactNode }) {
  const [livePrices, setLivePrices] = useState<Record<string, LiveTick>>({})
  const [isConnected, setIsConnected] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<string | null>(null)
  const [isSimulated, setIsSimulated] = useState(false)
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

      // Exponential backoff: BASE * 1.5^attempt capped at 30s, plus 25% random
      // jitter so many clients reconnecting after a shared outage don't all
      // retry in lockstep and flood the server the moment it comes back.
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
              setIsSimulated(Boolean(data.simulated))
            } else if (data.type === 'UNAVAILABLE') {
              // Production: the backend has no real feed to serve and is
              // about to close the socket. Don't let onclose's reconnect
              // loop briefly flash a "LIVE" state in the meantime.
              setIsConnected(false)
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
    <LiveMarketContext.Provider value={{ livePrices, isConnected, lastUpdated, isSimulated }}>
      {children}
    </LiveMarketContext.Provider>
  )
}

export function useLiveMarket() {
  return useContext(LiveMarketContext)
}
