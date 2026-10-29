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
          reconnectTimer = setTimeout(connect, 3000)
        }

        ws.onerror = () => {
          ws.close()
        }
      } catch {
        reconnectTimer = setTimeout(connect, 4000)
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
