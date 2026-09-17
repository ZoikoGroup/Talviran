import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import Sidebar, { type Chat, type Project } from '@/components/Sidebar'
import Message from '@/components/Message'
import Composer from '@/components/Composer'
import SettingsPage from '@/components/SettingsPage'
import TalvrinMoonChat from '@/components/ui/talvrin-moon-chat'
import { buildReply, type ChatMessage } from '@/data/mockReply'
import { mockChats, mockProjects } from '@/data/mockWorkspace'
import { DEFAULT_MODEL, type ModelId } from '@/data/models'
import { useTheme } from '@/theme/ThemeContext'
import { ApiError, createChat, postResearch } from '@/lib/api'
import brandIcon from '@/assets/brand/talvrin-icon.svg'

interface ChatRecord extends Chat {
  messages: ChatMessage[]
  /** The real server-side conversation this local chat is backed by, once
   * it exists. Created lazily on the first message sent in a given chat -
   * a brand-new chat the user never types in never needs a backend row. */
  backendId?: string
}

// Set VITE_USE_MOCK=true for an offline dev fallback; never true in a
// production build even if the flag leaks into one (import.meta.env.PROD
// is baked in at build time, not runtime-configurable).
const USE_MOCK = !import.meta.env.PROD && import.meta.env.VITE_USE_MOCK === 'true'

function errorMessageFor(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === 'RATE_LIMITED') {
      return 'Too many requests right now. Please wait a moment and try again.'
    }
    if (err.code === 'POLICY_BLOCKED') return 'This response is not currently permitted.'
    return err.message
  }
  return "Talvrin couldn't reach the backend. Please check your connection and try again."
}

const uid = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2) + Date.now().toString(36)

const newChat = (projectId: string | null = null): ChatRecord => ({
  id: uid(),
  title: 'New chat',
  messages: [],
  createdAt: Date.now(),
  projectId,
})

// No backend yet, so the history and projects live in localStorage — a chat
// history that empties on reload isn't a history.
const STORE = 'talvrin-workspace'

interface Stored {
  chats: ChatRecord[]
  projects: Project[]
  /** Set once the demo history has been planted, so it never returns. */
  seeded: boolean
}

const loadWorkspace = (): Stored => {
  let chats: ChatRecord[] = []
  let projects: Project[] = []
  let seeded = false

  try {
    const raw = localStorage.getItem(STORE)
    if (raw) {
      // `threads` is the pre-rename key — read it so an existing workspace
      // isn't wiped by the rename.
      const parsed = JSON.parse(raw) as Partial<Stored> & {
        threads?: ChatRecord[]
      }
      const found = parsed.chats ?? parsed.threads
      if (Array.isArray(found)) chats = found
      if (Array.isArray(parsed.projects)) projects = parsed.projects
      seeded = parsed.seeded === true
    }
  } catch {
    // Corrupt or unavailable storage just means a fresh workspace.
  }

  // Plant the demo history exactly once per browser. It sits alongside
  // anything already here rather than replacing it — and because the flag is
  // then persisted, it never comes back, so it can't resurrect after a
  // workspace is genuinely in use.
  if (!seeded) {
    return {
      // Seeds sit *behind* a fresh empty chat, so the app opens on the hero
      // rather than mid-conversation.
      chats: [
        newChat(),
        ...mockChats(),
        ...chats.filter((c) => c.messages.length > 0),
      ],
      projects: [...projects, ...mockProjects()],
      seeded: true,
    }
  }

  return {
    chats: chats.length > 0 ? chats : [newChat()],
    projects,
    seeded: true,
  }
}

export default function App() {
  const navigate = useNavigate()
  const [stored] = useState(loadWorkspace)
  const [chats, setChats] = useState<ChatRecord[]>(stored.chats)
  const [projects, setProjects] = useState<Project[]>(stored.projects)
  // Derived from the chats actually in state — never a hardcoded id, which
  // would drift from them under StrictMode's double-invoked initialiser.
  const [activeId, setActiveId] = useState<string>(() => chats[0].id)
  const [draft, setDraft] = useState('')
  const [attachments, setAttachments] = useState<File[]>([])
  const [model, setModel] = useState<ModelId>(
    () => (localStorage.getItem('talvrin-model') as ModelId) || DEFAULT_MODEL
  )
  const [thinking, setThinking] = useState(false)
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem('talvrin-sidebar') === 'collapsed'
  )
  const { theme, setTheme } = useTheme()
  const [showSettings, setShowSettings] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)
  const active = chats.find((c) => c.id === activeId) ?? chats[0]
  const isEmpty = active.messages.length === 0

  // Persist the workspace so history and projects survive a reload.
  useEffect(() => {
    try {
      localStorage.setItem(STORE, JSON.stringify({ chats, projects, seeded: true }))
    } catch {
      // Quota or private mode — the session still works, it just won't persist.
    }
  }, [chats, projects])

  useEffect(() => {
    localStorage.setItem('talvrin-model', model)
  }, [model])

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

  const patchActive = (fn: (c: ChatRecord) => ChatRecord) =>
    setChats((prev) => prev.map((c) => (c.id === activeId ? fn(c) : c)))

  const appendAssistantMessage = (chatId: string, message: ChatMessage) =>
    setChats((prev) =>
      prev.map((c) => (c.id === chatId ? { ...c, messages: [...c.messages, message] } : c))
    )

  const send = (text?: string) => {
    const content = (text ?? draft).trim()
    if (!content || thinking) return

    const chatId = activeId
    const before = chats.find((c) => c.id === chatId)
    const isFirstMessage = !before || before.messages.length === 0

    setDraft('')
    setAttachments([])
    setThinking(true)

    patchActive((c) => ({
      ...c,
      // First message becomes the chat title in the sidebar.
      title: c.messages.length === 0 ? content.slice(0, 40) : c.title,
      messages: [...c.messages, { role: 'user', text: content }],
    }))

    if (USE_MOCK) {
      // Placeholder latency so the typing indicator is visible.
      setTimeout(() => {
        appendAssistantMessage(chatId, { role: 'assistant', model, ...buildReply(content) })
        setThinking(false)
      }, 750)
      return
    }

    void (async () => {
      try {
        let backendId = before?.backendId
        if (!backendId) {
          const created = await createChat(
            model,
            isFirstMessage ? content.slice(0, 40) : before?.title
          )
          backendId = created.id
          setChats((prev) => prev.map((c) => (c.id === chatId ? { ...c, backendId } : c)))
        }

        const answer = await postResearch(backendId, content)
        appendAssistantMessage(chatId, {
          role: 'assistant',
          model,
          text: answer.text,
          facts: answer.facts,
          citations: answer.citations,
          note: answer.note,
          messageId: answer.messageId,
        })
      } catch (err) {
        if (err instanceof ApiError && err.code === 'UNAUTHENTICATED') {
          navigate('/login', { replace: true })
          return
        }
        appendAssistantMessage(chatId, {
          role: 'assistant',
          model,
          text: errorMessageFor(err),
          facts: null,
          citations: [],
          note: null,
        })
      } finally {
        setThinking(false)
      }
    })()
  }

  const startChat = (projectId: string | null = null) => {
    const c = newChat(projectId)
    setChats((prev) => [c, ...prev])
    setActiveId(c.id)
    setDraft('')
    setAttachments([])
  }

  // Creating a project drops you straight into an empty chat inside it.
  const addProject = (name: string) => {
    const project: Project = { id: uid(), name }
    setProjects((prev) => [...prev, project])
    startChat(project.id)
    return project.id
  }

  /** Wipes the workspace and starts a single empty chat. */
  const clearWorkspace = () => {
    const fresh = newChat()
    setChats([fresh])
    setProjects([])
    setActiveId(fresh.id)
    setDraft('')
    setAttachments([])
  }

  /** Move a chat into a project, or back out to the flat history (`null`). */
  const moveChat = (chatId: string, projectId: string | null) =>
    setChats((prev) =>
      prev.map((c) => (c.id === chatId ? { ...c, projectId } : c))
    )

  const renameChat = (chatId: string, title: string) =>
    setChats((prev) => prev.map((c) => (c.id === chatId ? { ...c, title } : c)))

  const deleteChat = (chatId: string) => {
    const next = chats.filter((c) => c.id !== chatId)
    // The app always needs somewhere to type, so never leave zero chats.
    if (next.length === 0) {
      const fresh = newChat()
      setChats([fresh])
      setActiveId(fresh.id)
      return
    }
    setChats(next)
    if (chatId === activeId) setActiveId(next[0].id)
  }

  const renameProject = (projectId: string, name: string) =>
    setProjects((prev) =>
      prev.map((p) => (p.id === projectId ? { ...p, name } : p))
    )

  /** Deleting a project keeps its chats — they fall back to the flat history. */
  const deleteProject = (projectId: string) => {
    setProjects((prev) => prev.filter((p) => p.id !== projectId))
    setChats((prev) =>
      prev.map((c) => (c.projectId === projectId ? { ...c, projectId: null } : c))
    )
  }

  return (
    <div className="relative flex h-full overflow-hidden bg-background">
      {/* Painted first so the sidebar's backdrop-filter samples it. */}
      <div aria-hidden className="app-ambient" />

      <Sidebar
        collapsed={collapsed}
        chats={chats}
        projects={projects}
        activeId={activeId}
        onSelect={(id) => {
          setActiveId(id)
          setShowSettings(false)
        }}
        onNew={(projectId) => {
          startChat(projectId ?? null)
          setShowSettings(false)
        }}
        onNewProject={addProject}
        onMoveChat={moveChat}
        onRenameChat={renameChat}
        onDeleteChat={deleteChat}
        onRenameProject={renameProject}
        onDeleteProject={deleteProject}
        onCollapse={() => setCollapsed(true)}
        onExpand={() => setCollapsed(false)}
        onOpenSettings={() => setShowSettings(true)}
      />

      <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        {showSettings ? (
          <SettingsPage
            onBack={() => setShowSettings(false)}
            theme={theme}
            onThemeChange={setTheme}
            stats={{
              chats: chats.filter((c) => c.messages.length > 0).length,
              projects: projects.length,
              messages: chats.reduce((n, c) => n + c.messages.length, 0),
            }}
            onClearWorkspace={clearWorkspace}
          />
        ) : isEmpty ? (
          <TalvrinMoonChat
            value={draft}
            onChange={setDraft}
            onSend={send}
            disabled={thinking}
            theme={theme}
            attachments={attachments}
            onAttach={(files) => setAttachments((prev) => [...prev, ...files])}
            onRemoveAttachment={(i) =>
              setAttachments((prev) => prev.filter((_, n) => n !== i))
            }
            model={model}
            onModelChange={setModel}
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
                    <img src={brandIcon} alt="" className="h-7 w-7 shrink-0 rounded-lg" />
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
              attachments={attachments}
              onAttach={(files) => setAttachments((prev) => [...prev, ...files])}
              onRemoveAttachment={(i) =>
                setAttachments((prev) => prev.filter((_, n) => n !== i))
              }
              model={model}
              onModelChange={setModel}
            />
          </>
        )}
      </main>
    </div>
  )
}
