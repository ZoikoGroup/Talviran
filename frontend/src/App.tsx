import { useState, useRef, useEffect } from 'react'
import { PanelLeft } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import Sidebar, { type Chat, type Project } from '@/components/Sidebar'
import Message from '@/components/Message'
import Composer from '@/components/Composer'
import SettingsPage from '@/components/SettingsPage'
import TalvrinMoonChat from '@/components/ui/talvrin-moon-chat'
import { buildReply, type ChatMessage } from '@/data/mockReply'
import { DEFAULT_MODEL, type ModelId } from '@/data/models'
import { useTheme } from '@/theme/ThemeContext'
import {
  ApiError,
  createChat,
  createProject as apiCreateProject,
  deleteChat as apiDeleteChat,
  deleteProject as apiDeleteProject,
  getChat,
  listChats,
  listProjects,
  patchChat,
  patchProject,
  postResearch,
  type ChatMessageWire,
} from '@/lib/api'
import brandIcon from '@/assets/brand/talvrin-icon.svg'
import wordmarkOnDark from '@/assets/brand/talvrin-wordmark-on-dark.svg'
import wordmarkOnLight from '@/assets/brand/talvrin-wordmark-on-light.svg'

interface ChatRecord extends Chat {
  messages: ChatMessage[]
  /** The real server-side conversation this local chat is backed by, once
   * it exists. Created lazily on the first message sent in a given chat -
   * a brand-new chat the user never types in never needs a backend row. */
  backendId?: string
  /** True once `messages` reflects this chat's real backend content (or the
   * chat has none yet, e.g. a fresh draft). A row fetched from `listChats()`
   * starts false — its history is only pulled down when it's opened. */
  messagesLoaded: boolean
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
  hasMessages: false,
  messages: [],
  messagesLoaded: true,
  createdAt: Date.now(),
  projectId,
})

/** A stored message only ever carries a role and plain text — the rich
 * facts table / citations a fresh answer renders with are computed at
 * request time and never written back, so a reloaded history necessarily
 * shows past assistant turns as plain text. */
const toDisplayMessage = (m: ChatMessageWire): ChatMessage => ({
  role: m.role.toLowerCase() === 'user' ? 'user' : 'assistant',
  text: m.content,
})

export default function App() {
  const navigate = useNavigate()
  const [draftChat] = useState(() => newChat())
  const [chats, setChats] = useState<ChatRecord[]>([draftChat])
  const [projects, setProjects] = useState<Project[]>([])
  const [activeId, setActiveId] = useState<string>(draftChat.id)
  const [draft, setDraft] = useState('')
  const [attachments, setAttachments] = useState<File[]>([])
  const [model, setModel] = useState<ModelId>(
    () => (localStorage.getItem('talvrin-model') as ModelId) || DEFAULT_MODEL
  )
  const [thinking, setThinking] = useState(false)
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem('talvrin-sidebar') === 'collapsed'
  )
  // Below `lg` the sidebar is an off-canvas drawer, closed by default —
  // unlike `collapsed`, this is session state, not a device preference.
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const { theme, setTheme } = useTheme()
  const [showSettings, setShowSettings] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)
  const active = chats.find((c) => c.id === activeId) ?? chats[0]
  const isLoadingActive = Boolean(active.backendId) && !active.messagesLoaded
  const isEmpty = !isLoadingActive && active.messages.length === 0

  // Load this account's real chats and projects once, on mount. There is no
  // account-keying logic here — the session cookie already scopes every one
  // of these requests server-side (RLS), so whoever is signed in only ever
  // sees their own rows. The app always opens on a fresh draft chat (the
  // hero screen) rather than resuming whatever was last open, so the sidebar
  // history is the only place a previous conversation reappears.
  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const [chatRows, projectRows] = await Promise.all([listChats(), listProjects()])
        if (cancelled) return
        const loaded: ChatRecord[] = chatRows.map((c) => ({
          id: c.id,
          backendId: c.id,
          title: c.title ?? 'New chat',
          hasMessages: true,
          messages: [],
          messagesLoaded: false,
          createdAt: new Date(c.createdAt).getTime(),
          projectId: c.projectId,
        }))
        setChats((prev) => [...prev, ...loaded])
        setProjects(projectRows.map((p) => ({ id: p.id, name: p.name })))
      } catch (err) {
        if (!cancelled && err instanceof ApiError && err.code === 'UNAUTHENTICATED') {
          navigate('/login', { replace: true })
        }
        // Any other failure (network hiccup) just leaves history empty for
        // this load — the composer still works, and reloading retries.
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

  /** Opens a chat, pulling down its real transcript the first time — a
   * sidebar row only ever carries metadata until it's actually opened. */
  const selectChat = (id: string) => {
    setActiveId(id)
    setShowSettings(false)

    const target = chats.find((c) => c.id === id)
    if (!target?.backendId || target.messagesLoaded) return

    void (async () => {
      try {
        const detail = await getChat(target.backendId!)
        setChats((prev) =>
          prev.map((c) =>
            c.id === id
              ? {
                  ...c,
                  messagesLoaded: true,
                  title: detail.title ?? c.title,
                  messages: detail.messages.map(toDisplayMessage),
                }
              : c
          )
        )
      } catch (err) {
        if (err instanceof ApiError && err.code === 'UNAUTHENTICATED') {
          navigate('/login', { replace: true })
          return
        }
        // Leave messagesLoaded false so reselecting the chat retries.
      }
    })()
  }

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
      hasMessages: true,
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
            isFirstMessage ? content.slice(0, 40) : before?.title,
            before?.projectId ?? null
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

  // Creating a project drops you straight into an empty chat inside it. The
  // project itself — unlike a chat — is created on the backend immediately,
  // since an empty project is still meaningful and needs to survive a reload.
  const addProject = async (name: string): Promise<string> => {
    const project = await apiCreateProject(name)
    setProjects((prev) => [...prev, { id: project.id, name: project.name }])
    startChat(project.id)
    return project.id
  }

  /** Deletes every real chat and project this account has, then starts a
   * single empty draft. Genuinely permanent now that chats and projects are
   * backend-persisted rather than a local cache. */
  const clearWorkspace = () => {
    const chatIds = chats.filter((c) => c.backendId).map((c) => c.backendId!)
    const projectIds = projects.map((p) => p.id)
    const fresh = newChat()
    setChats([fresh])
    setProjects([])
    setActiveId(fresh.id)
    setDraft('')
    setAttachments([])
    void Promise.all([
      ...chatIds.map((id) => apiDeleteChat(id).catch(() => {})),
      ...projectIds.map((id) => apiDeleteProject(id).catch(() => {})),
    ])
  }

  /** Downloads everything this account has, pulling down any chat whose
   * transcript hasn't been opened (and so isn't loaded) yet. */
  const exportWorkspace = async () => {
    const started = chats.filter((c) => c.hasMessages)
    const full = await Promise.all(
      started.map(async (c) => {
        if (c.messagesLoaded || !c.backendId) return c
        try {
          const detail = await getChat(c.backendId)
          return { ...c, messages: detail.messages.map(toDisplayMessage) }
        } catch {
          return c
        }
      })
    )
    const payload = {
      exportedAt: new Date().toISOString(),
      projects,
      chats: full.map((c) => ({
        id: c.backendId ?? c.id,
        title: c.title,
        projectId: c.projectId,
        messages: c.messages,
      })),
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `talvrin-workspace-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  /** Move a chat into a project, or back out to the flat history (`null`). */
  const moveChat = (chatId: string, projectId: string | null) => {
    setChats((prev) => prev.map((c) => (c.id === chatId ? { ...c, projectId } : c)))
    const target = chats.find((c) => c.id === chatId)
    if (target?.backendId) void patchChat(target.backendId, { projectId }).catch(() => {})
  }

  const renameChat = (chatId: string, title: string) => {
    setChats((prev) => prev.map((c) => (c.id === chatId ? { ...c, title } : c)))
    const target = chats.find((c) => c.id === chatId)
    if (target?.backendId) void patchChat(target.backendId, { title }).catch(() => {})
  }

  const deleteChat = (chatId: string) => {
    const target = chats.find((c) => c.id === chatId)
    const next = chats.filter((c) => c.id !== chatId)
    // The app always needs somewhere to type, so never leave zero chats.
    if (next.length === 0) {
      const fresh = newChat()
      setChats([fresh])
      setActiveId(fresh.id)
    } else {
      setChats(next)
      if (chatId === activeId) setActiveId(next[0].id)
    }
    if (target?.backendId) void apiDeleteChat(target.backendId).catch(() => {})
  }

  const renameProject = (projectId: string, name: string) => {
    setProjects((prev) => prev.map((p) => (p.id === projectId ? { ...p, name } : p)))
    void patchProject(projectId, name).catch(() => {})
  }

  /** Deleting a project keeps its chats — they fall back to the flat history. */
  const deleteProject = (projectId: string) => {
    setProjects((prev) => prev.filter((p) => p.id !== projectId))
    setChats((prev) =>
      prev.map((c) => (c.projectId === projectId ? { ...c, projectId: null } : c))
    )
    void apiDeleteProject(projectId).catch(() => {})
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
        onSelect={selectChat}
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
        mobileOpen={mobileNavOpen}
        onMobileClose={() => setMobileNavOpen(false)}
      />

      <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Mobile-only top bar: the sidebar is off-canvas below `lg`, so this
            is the only way to reach it once a chat is open. Hidden on
            desktop, where the sidebar is already a permanent column. */}
        <div className="flex shrink-0 items-center gap-1 border-b border-border/60 px-2 py-2 lg:hidden">
          <button
            onClick={() => setMobileNavOpen(true)}
            aria-label="Open sidebar"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <PanelLeft className="h-[18px] w-[18px]" />
          </button>
          <img src={wordmarkOnDark} alt="Talvrin" className="brand-on-dark ml-1 h-[22px] w-auto" />
          <img src={wordmarkOnLight} alt="Talvrin" className="brand-on-light ml-1 h-[22px] w-auto" />
        </div>

        {/* Sized against what's left after the mobile top bar above, not the
            whole of `main` — each branch below fills this via its own
            flex-1/h-full, and without this wrapper that percentage would
            resolve against main's full height and overflow by the bar's
            height under `overflow-hidden`. */}
        <div className="flex min-h-0 flex-1 flex-col">
        {showSettings ? (
          <SettingsPage
            onBack={() => setShowSettings(false)}
            theme={theme}
            onThemeChange={setTheme}
            stats={{
              chats: chats.filter((c) => c.hasMessages).length,
              projects: projects.length,
              messages: chats.reduce((n, c) => n + c.messages.length, 0),
            }}
            onClearWorkspace={clearWorkspace}
            onExportWorkspace={exportWorkspace}
          />
        ) : isLoadingActive ? (
          <div className="flex flex-1 items-center justify-center text-[13.5px] text-muted-foreground">
            Loading conversation…
          </div>
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
              <div className="mx-auto max-w-3xl px-4 pb-3 pt-6 sm:px-6 lg:pt-16">
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
        </div>
      </main>
    </div>
  )
}
