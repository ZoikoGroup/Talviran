import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  Search,
  Sparkles,
  TrendingUp,
  MessageSquare,
  CornerDownLeft,
  X,
  Compass,
  Bell,
  BarChart2,
  Layers,
  Settings,
  Plus,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { TaggedAsset } from '@/data/mockReply'
import { GLOBAL_MARKET_ASSETS } from '@/components/MarketsPage'
import type { Chat } from '@/components/Sidebar'

interface SearchModalProps {
  isOpen: boolean
  onClose: () => void
  chats: Chat[]
  onSelectChat: (id: string) => void
  onStartResearch: (assetOrQuery: string | TaggedAsset, prompt?: string) => void
  onNavigate: (surface: 'home' | 'markets' | 'watchlists' | 'monitoring' | 'settings' | 'new-chat') => void
}

interface ActionItem {
  id: string
  category: 'ask' | 'asset' | 'chat' | 'navigation'
  title: string
  subtitle?: string
  badge?: string
  icon: typeof Search
  asset?: TaggedAsset
  chatId?: string
  surface?: 'home' | 'markets' | 'watchlists' | 'monitoring' | 'settings' | 'new-chat'
}

export default function SearchModal({
  isOpen,
  onClose,
  chats,
  onSelectChat,
  onStartResearch,
  onNavigate,
}: SearchModalProps) {
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  // Autofocus when modal opens
  useEffect(() => {
    if (isOpen) {
      setQuery('')
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [isOpen])

  // Filter items based on query
  const trimmed = query.trim()
  const items: ActionItem[] = []

  // 1. Direct AI Query option if query is non-empty
  if (trimmed) {
    items.push({
      id: 'ask-ai-direct',
      category: 'ask',
      title: `Ask Talvrin: "${trimmed}"`,
      subtitle: 'Evidence-backed answer grounded in trusted primary sources only',
      badge: 'AI Research',
      icon: Sparkles,
    })
  }

  // 2. Filter Market Assets
  const matchedAssets = GLOBAL_MARKET_ASSETS.filter((a) => {
    if (!trimmed) return false
    const q = trimmed.toLowerCase()
    return (
      a.symbol.toLowerCase().includes(q) ||
      a.name.toLowerCase().includes(q) ||
      a.assetClass.toLowerCase().includes(q) ||
      a.source.toLowerCase().includes(q)
    )
  }).slice(0, 7)

  matchedAssets.forEach((a) => {
    items.push({
      id: `asset-${a.symbol}`,
      category: 'asset',
      title: `${a.name} (${a.symbol})`,
      subtitle: `${a.price} • ${a.change} (${a.pctChange}) • Source: ${a.source}`,
      badge: a.assetClass,
      icon: TrendingUp,
      asset: {
        symbol: a.symbol,
        name: a.name,
        assetClass: a.assetClass,
        price: a.price,
        change: a.change,
        pctChange: a.pctChange,
        direction: a.direction,
        source: a.source,
      },
    })
  })

  // If query is empty, show top benchmark assets across all trusted asset classes
  if (!trimmed) {
    const defaultBenchmarkAssets = GLOBAL_MARKET_ASSETS.filter((a) =>
      ['US 10Y Treasury', 'UK 10Y Gilt', 'S&P 500', 'Gold (XAU/USD)', 'BTC/USD', 'GBP/USD', 'AAPL'].includes(a.symbol)
    )
    defaultBenchmarkAssets.forEach((a) => {
      items.push({
        id: `bench-${a.symbol}`,
        category: 'asset',
        title: `${a.name} (${a.symbol})`,
        subtitle: `${a.price} • ${a.change} (${a.pctChange}) • Source: ${a.source}`,
        badge: a.assetClass,
        icon: TrendingUp,
        asset: {
          symbol: a.symbol,
          name: a.name,
          assetClass: a.assetClass,
          price: a.price,
          change: a.change,
          pctChange: a.pctChange,
          direction: a.direction,
          source: a.source,
        },
      })
    })
  }


  // 3. Filter Previous Chats
  const matchedChats = chats
    .filter((c) => {
      if (!trimmed) return false
      return c.title.toLowerCase().includes(trimmed.toLowerCase())
    })
    .slice(0, 4)

  matchedChats.forEach((c) => {
    items.push({
      id: `chat-${c.id}`,
      category: 'chat',
      title: c.title,
      subtitle: 'Previous research conversation',
      badge: 'Chat',
      icon: MessageSquare,
      chatId: c.id,
    })
  })

  // 4. Platform Navigation
  const navigationActions: ActionItem[] = [
    {
      id: 'nav-new-chat',
      category: 'navigation',
      title: 'New Research Chat',
      subtitle: 'Start an evidence-backed inquiry',
      badge: 'Action',
      icon: Plus,
      surface: 'new-chat',
    },
    {
      id: 'nav-home',
      category: 'navigation',
      title: 'Home Dashboard',
      subtitle: 'Market pulse, recent alerts & activity overview',
      badge: 'Page',
      icon: Compass,
      surface: 'home',
    },
    {
      id: 'nav-markets',
      category: 'navigation',
      title: 'Markets & Technical Screener',
      subtitle: 'Multi-asset real-time screener and institutional charts',
      badge: 'Page',
      icon: BarChart2,
      surface: 'markets',
    },
    {
      id: 'nav-watchlists',
      category: 'navigation',
      title: 'Portfolio Watchlists',
      subtitle: 'Track customized asset baskets and portfolios',
      badge: 'Page',
      icon: Layers,
      surface: 'watchlists',
    },
    {
      id: 'nav-monitoring',
      category: 'navigation',
      title: 'Monitoring & Alert Rules',
      subtitle: 'Manage alert conditions and watcher health',
      badge: 'Page',
      icon: Bell,
      surface: 'monitoring',
    },
    {
      id: 'nav-settings',
      category: 'navigation',
      title: 'Settings & Workspace',
      subtitle: 'Model configuration and account management',
      badge: 'Settings',
      icon: Settings,
      surface: 'settings',
    },
  ]

  const matchedNav = navigationActions.filter((n) => {
    if (!trimmed) return true
    const q = trimmed.toLowerCase()
    return n.title.toLowerCase().includes(q) || (n.subtitle && n.subtitle.toLowerCase().includes(q))
  })

  matchedNav.forEach((n) => items.push(n))

  // Execute selected item
  const handleExecute = (item: ActionItem) => {
    onClose()
    if (item.category === 'ask') {
      onStartResearch(trimmed)
    } else if (item.category === 'asset' && item.asset) {
      onStartResearch(item.asset)
    } else if (item.category === 'chat' && item.chatId) {
      onSelectChat(item.chatId)
    } else if (item.category === 'navigation' && item.surface) {
      onNavigate(item.surface)
    }
  }

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex((prev) => (prev + 1 < items.length ? prev + 1 : 0))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex((prev) => (prev - 1 >= 0 ? prev - 1 : items.length - 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (items[selectedIndex]) {
        handleExecute(items[selectedIndex])
      } else if (trimmed) {
        onClose()
        onStartResearch(trimmed)
      }
    } else if (e.key === 'Escape') {
      onClose()
    }
  }

  // Scroll active item into view
  useEffect(() => {
    const list = listRef.current
    if (!list) return
    const activeEl = list.children[selectedIndex] as HTMLElement | undefined
    if (activeEl) {
      activeEl.scrollIntoView({ block: 'nearest' })
    }
  }, [selectedIndex])

  if (!isOpen) return null

  return createPortal(
    <div
      onClick={onClose}
      className="fixed inset-0 z-[9999] flex items-start justify-center bg-black/80 p-3 pt-[10vh] sm:p-6 sm:pt-[12vh] backdrop-blur-md animate-in fade-in duration-150"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative flex w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-border bg-[#0d0f12] text-foreground shadow-2xl shadow-black/80 animate-in zoom-in-95 duration-150"
      >
        {/* Search Input Bar */}
        <div className="flex items-center gap-3 border-b border-border/80 bg-[#12151a] px-4 py-3 sm:px-5">
          <Search className="h-5 w-5 shrink-0 text-primary" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setSelectedIndex(0)
            }}
            onKeyDown={handleKeyDown}
            placeholder="Search instruments, markets, research chats, or ask anything…"
            className="flex-1 bg-transparent text-[15px] font-medium text-foreground placeholder:text-muted-foreground/70 focus:outline-hidden"
          />
          {query ? (
            <button
              onClick={() => {
                setQuery('')
                setSelectedIndex(0)
                inputRef.current?.focus()
              }}
              className="rounded-lg p-1 text-muted-foreground hover:bg-white/10 hover:text-foreground transition"
            >
              <X className="h-4 w-4" />
            </button>
          ) : (
            <kbd className="hidden sm:inline-block rounded-md border border-border/80 bg-secondary/80 px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
              ESC
            </kbd>
          )}
        </div>

        {/* Results List */}
        <div
          ref={listRef}
          className="max-h-[60vh] overflow-y-auto p-2 scrollbar-slim divide-y divide-border/20"
        >
          {items.length === 0 ? (
            <div className="py-12 text-center text-[13.5px] text-muted-foreground">
              No matching instruments, conversations, or actions found for "{query}".
            </div>
          ) : (
            items.map((item, index) => {
              const isSelected = index === selectedIndex
              const Icon = item.icon
              return (
                <div
                  key={item.id}
                  onClick={() => handleExecute(item)}
                  onMouseEnter={() => setSelectedIndex(index)}
                  className={cn(
                    'group flex cursor-pointer items-center justify-between rounded-xl px-3.5 py-2.5 transition-colors',
                    isSelected
                      ? 'bg-primary/15 text-primary border border-primary/30'
                      : 'hover:bg-accent/40 text-foreground border border-transparent'
                  )}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span
                      className={cn(
                        'grid h-8 w-8 shrink-0 place-items-center rounded-lg transition-colors',
                        item.category === 'ask'
                          ? 'bg-gradient-to-br from-indigo-500 to-purple-600 text-white'
                          : isSelected
                          ? 'bg-primary/25 text-primary'
                          : 'bg-secondary text-muted-foreground group-hover:text-foreground'
                      )}
                    >
                      <Icon className="h-4 w-4" />
                    </span>
                    <div className="min-w-0 flex flex-col">
                      <span className={cn('text-[13.5px] font-semibold truncate', isSelected && 'text-white')}>
                        {item.title}
                      </span>
                      {item.subtitle && (
                        <span className="text-[11.5px] text-muted-foreground truncate">
                          {item.subtitle}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0 ml-3">
                    {item.badge && (
                      <span
                        className={cn(
                          'rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider',
                          item.category === 'ask'
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-secondary text-muted-foreground border border-border/60'
                        )}
                      >
                        {item.badge}
                      </span>
                    )}
                    {isSelected && (
                      <span className="flex items-center gap-1 font-mono text-[10.5px] text-primary">
                        <CornerDownLeft className="h-3 w-3" />
                      </span>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>

        {/* Modal Footer Hotkey Hints */}
        <div className="flex items-center justify-between border-t border-border/80 bg-[#12151a] px-4 py-2 text-[11.5px] text-muted-foreground">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <kbd className="rounded border border-border/80 bg-secondary/80 px-1.5 py-0.2 font-mono text-[10px]">
                ↑
              </kbd>
              <kbd className="rounded border border-border/80 bg-secondary/80 px-1.5 py-0.2 font-mono text-[10px]">
                ↓
              </kbd>{' '}
              Navigate
            </span>
            <span className="flex items-center gap-1">
              <kbd className="rounded border border-border/80 bg-secondary/80 px-1.5 py-0.2 font-mono text-[10px]">
                ↵
              </kbd>{' '}
              Select
            </span>
          </div>
          <span className="text-[11px] text-muted-foreground/80">
            Talvrin Universal Search
          </span>
        </div>
      </div>
    </div>,
    document.body
  )
}
