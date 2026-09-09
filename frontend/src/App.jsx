import { useState, useRef, useEffect } from 'react'
import Sidebar from './components/Sidebar.jsx'
import Message from './components/Message.jsx'
import EmptyState from './components/EmptyState.jsx'
import Composer from './components/Composer.jsx'
import { Menu } from './components/icons.jsx'
import { buildReply } from './mockReply.js'

let nextId = 1
const newThread = () => ({ id: nextId++, title: 'New thread', messages: [] })

export default function App() {
  const [threads, setThreads] = useState([newThread()])
  const [activeId, setActiveId] = useState(1)
  const [draft, setDraft] = useState('')
  const [thinking, setThinking] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const [theme, setTheme] = useState(
    () => localStorage.getItem('talvrin-theme') || 'dark'
  )

  const scrollRef = useRef(null)
  const active = threads.find((t) => t.id === activeId) ?? threads[0]

  // Theme is applied on the root element so CSS variables can switch.
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('talvrin-theme', theme)
  }, [theme])

  // Keep the newest message in view.
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [active?.messages.length, thinking])

  const patchActive = (fn) =>
    setThreads((prev) => prev.map((t) => (t.id === activeId ? fn(t) : t)))

  const send = (text) => {
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
        messages: [...t.messages, { role: 'assistant', ...buildReply(content) }],
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
    <div className="app">
      <Sidebar
        collapsed={collapsed}
        threads={threads}
        activeId={activeId}
        onSelect={setActiveId}
        onNew={startThread}
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
      />

      <main className="main">
        <header className="topbar">
          <button
            className="icon-btn"
            onClick={() => setCollapsed((c) => !c)}
            aria-label="Toggle sidebar"
          >
            <Menu size={18} />
          </button>

          <span className="topbar-title">Research</span>

          <div className="topbar-right">
            <span className="chip">
              <span className="chip-dot" />
              Data current
            </span>
            <span className="chip">UK gilts · US Treasuries</span>
          </div>
        </header>

        <div className="scroll" ref={scrollRef}>
          {active.messages.length === 0 ? (
            <EmptyState onPick={send} />
          ) : (
            <div className="stream">
              {active.messages.map((m, i) => (
                <Message key={i} {...m} />
              ))}

              {thinking && (
                <div className="msg bot">
                  <div className="bot-mark">T</div>
                  <div className="bot-body">
                    <div className="bot-name">Talvrin</div>
                    <div className="typing"><i /><i /><i /></div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <Composer
          value={draft}
          onChange={setDraft}
          onSend={() => send()}
          disabled={thinking}
        />
      </main>
    </div>
  )
}
