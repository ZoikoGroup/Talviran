import { useState, useRef, useEffect } from 'react'
import Sidebar from './components/Sidebar.jsx'
import Message from './components/Message.jsx'
import EmptyState from './components/EmptyState.jsx'
import Composer from './components/Composer.jsx'
import { buildReply } from './mockReply.js'

let nextId = 1
const newThread = () => ({ id: nextId++, title: 'New thread', messages: [] })

export default function App() {
  const [threads, setThreads] = useState([newThread()])
  const [activeId, setActiveId] = useState(1)
  const [draft, setDraft] = useState('')
  const [thinking, setThinking] = useState(false)
  const [collapsed, setCollapsed] = useState(false)

  const scrollRef = useRef(null)
  const active = threads.find((t) => t.id === activeId) ?? threads[0]

  // Keep the newest message in view.
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
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
      title: t.messages.length === 0 ? content.slice(0, 38) : t.title,
      messages: [...t.messages, { role: 'user', text: content }],
    }))

    // Placeholder latency so the typing indicator is visible.
    setTimeout(() => {
      const reply = buildReply(content)
      patchActive((t) => ({
        ...t,
        messages: [...t.messages, { role: 'assistant', ...reply }],
      }))
      setThinking(false)
    }, 700)
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
      />

      <main className="main">
        <header className="topbar">
          <button
            className="icon-btn"
            onClick={() => setCollapsed((c) => !c)}
            aria-label="Toggle sidebar"
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <span className="topbar-title">Research</span>
          <span className="badge">UK gilts · US Treasuries</span>
        </header>

        <div className="scroll" ref={scrollRef}>
          {active.messages.length === 0 ? (
            <EmptyState onPick={send} />
          ) : (
            <div className="thread-body">
              {active.messages.map((m, i) => (
                <Message key={i} {...m} />
              ))}

              {thinking && (
                <div className="msg">
                  <div className="msg-avatar bot">T</div>
                  <div className="msg-body">
                    <div className="msg-role">Talvrin</div>
                    <div className="typing"><span /><span /><span /></div>
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
