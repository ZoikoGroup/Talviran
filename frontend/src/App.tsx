import { useState, useRef, useEffect } from 'react'
import { PanelLeft } from 'lucide-react'
import Sidebar, { type Thread } from '@/components/Sidebar'
import Message from '@/components/Message'
import Composer from '@/components/Composer'
import TalvrinMoonChat from '@/components/ui/talvrin-moon-chat'
import { buildReply, type ChatMessage } from '@/data/mockReply'
import { cn } from '@/lib/utils'

interface ChatThread extends Thread {
  messages: ChatMessage[]
}

let nextId = 1
const newThread = (): ChatThread => ({
  id: nextId++,
  title: 'New thread',
  messages: [],
})

export default function App() {
  const [threads, setThreads] = useState<ChatThread[]>([newThread()])
  const [activeId, setActiveId] = useState(1)
  const [draft, setDraft] = useState('')
  const [thinking, setThinking] = useState(false)
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem('talvrin-sidebar') === 'collapsed'
  )
  const [theme, setTheme] = useState<'dark' | 'light'>(
    () => (localStorage.getItem('talvrin-theme') as 'dark' | 'light') || 'dark'
  )

  const scrollRef = useRef<HTMLDivElement>(null)
  const active = threads.find((t) => t.id === activeId) ?? threads[0]
  const isEmpty = active.messages.length === 0

  // Theme drives the `.light` class that overrides the CSS variables.
  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light')
    localStorage.setItem('talvrin-theme', theme)
  }, [theme])

  // Remember whether the sidebar was left open or closed.
  useEffect(() => {
    localStorage.setItem('talvrin-sidebar', collapsed ? 'collapsed' : 'open')
  }, [collapsed])

  // Keep the newest message in view.
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [active.messages.length, thinking])

  const patchActive = (fn: (t: ChatThread) => ChatThread) =>
    setThreads((prev) => prev.map((t) => (t.id === activeId ? fn(t) : t)))

  const send = (text?: string) => {
    const content = (text ?? draft).trim()
    if (!content || thinking) return

    setDraft('')
    setThinking(true)

    patchActive((t) => ({
      ...t,
      // First message becomes the thread title in the sidebar.
      title: t.messages.length === 0 ? content.slice(0, 40) : t.title,
      messages: [...t.messages, { role: 'user', text: content }],
    }))

    // Placeholder latency so the typing indicator is visible.
    setTimeout(() => {
      patchActive((t) => ({
        ...t,
        messages: [
          ...t.messages,
          { role: 'assistant', ...buildReply(content) },
        ],
      }))
      setThinking(false)
    }, 750)
  }

  const startThread = () => {
    const t = newThread()
    setThreads((prev) => [t, ...prev])
    setActiveId(t.id)
    setDraft('')
  }

  return (
    <div className="flex h-full overflow-hidden bg-background">
      <Sidebar
        collapsed={collapsed}
        threads={threads}
        activeId={activeId}
        onSelect={setActiveId}
        onNew={startThread}
        onCollapse={() => setCollapsed(true)}
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
      />

      <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Floating reopen control. Only interactive while the sidebar is
            hidden, so it never doubles up with the sidebar's own collapse
            button. */}
        <button
          onClick={() => setCollapsed(false)}
          aria-label="Show sidebar"
          className={cn(
            'absolute left-3 top-3 z-30 grid h-9 w-9 place-items-center rounded-lg',
            'border border-border/70 bg-card/70 text-muted-foreground backdrop-blur-md',
            'transition-opacity hover:bg-accent hover:text-foreground',
            collapsed
              ? 'pointer-events-auto opacity-100'
              : 'pointer-events-none opacity-0'
          )}
        >
          <PanelLeft className="h-[17px] w-[17px]" />
        </button>

        {isEmpty ? (
          <TalvrinMoonChat
            value={draft}
            onChange={setDraft}
            onSend={send}
            disabled={thinking}
            theme={theme}
          />
        ) : (
          <>
            <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-slim">
              <div className="mx-auto max-w-3xl px-6 pb-3 pt-16">
                {active.messages.map((m, i) => (
                  <Message key={i} {...m} />
                ))}

                {thinking && (
                  <div className="mb-7 flex gap-3.5">
                    <div className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-purple-500 text-[11.5px] font-bold text-white">
                      T
                    </div>
                    <div className="pt-0.5">
                      <div className="mb-1.5 text-[13px] font-semibold">Talvrin</div>
                      <div className="flex gap-1.5 pt-1.5">
                        {[0, 1, 2].map((i) => (
                          <span
                            key={i}
                            className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60"
                            style={{ animationDelay: `${i * 0.16}s` }}
                          />
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <Composer
              value={draft}
              onChange={setDraft}
              onSend={() => send()}
              disabled={thinking}
            />
          </>
        )}
      </main>
    </div>
  )
}
