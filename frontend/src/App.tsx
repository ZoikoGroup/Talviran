import { useState, useRef, useEffect } from 'react'
import { Menu } from 'lucide-react'
import Sidebar, { type Thread } from '@/components/Sidebar'
import Message from '@/components/Message'
import Composer from '@/components/Composer'
import TalvrinMoonChat from '@/components/ui/talvrin-moon-chat'
import { Button } from '@/components/ui/button'
import { buildReply, type ChatMessage } from '@/data/mockReply'

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
  const [collapsed, setCollapsed] = useState(false)
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
    <div className="flex h-full overflow-hidden">
      <Sidebar
        collapsed={collapsed}
        threads={threads}
        activeId={activeId}
        onSelect={setActiveId}
        onNew={startThread}
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
      />

      <main className="relative flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2.5 border-b border-border bg-background/80 px-3.5 backdrop-blur-xl">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setCollapsed((c) => !c)}
            className="h-9 w-9 text-muted-foreground hover:text-foreground"
          >
            <Menu className="h-[18px] w-[18px]" />
            <span className="sr-only">Toggle sidebar</span>
          </Button>

          <span className="text-sm font-medium">Research</span>

          <div className="ml-auto flex items-center gap-2">
            <span className="flex items-center gap-1.5 rounded-full border border-border bg-secondary px-2.5 py-1 text-[11.5px] font-medium text-muted-foreground">
              <span className="h-1.5 w-1.5 rounded-full bg-fresh ring-[3px] ring-fresh/20" />
              Data current
            </span>
            <span className="rounded-full border border-border bg-secondary px-2.5 py-1 text-[11.5px] font-medium text-muted-foreground">
              UK gilts · US Treasuries
            </span>
          </div>
        </header>

        {isEmpty ? (
          <TalvrinMoonChat
            value={draft}
            onChange={setDraft}
            onSend={send}
            disabled={thinking}
          />
        ) : (
          <>
            <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-slim">
              <div className="mx-auto max-w-3xl px-6 pb-3 pt-8">
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
