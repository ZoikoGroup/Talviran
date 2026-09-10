import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Check,
  ChevronRight,
  Ellipsis,
  Folder,
  FolderMinus,
  MessageSquare,
  PanelLeft,
  PanelLeftClose,
  Pencil,
  Plus,
  Settings,
  SquarePen,
  Trash2,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { currentUser } from '@/data/user'
import PopoverMenu from '@/components/ui/popover-menu'
import brandIcon from '@/assets/brand/talvrin-icon.svg'
import wordmarkOnDark from '@/assets/brand/talvrin-wordmark-on-dark.svg'
import wordmarkOnLight from '@/assets/brand/talvrin-wordmark-on-light.svg'

export interface Chat {
  id: string
  title: string
  messages: unknown[]
  createdAt: number
  projectId: string | null
}

export interface Project {
  id: string
  name: string
}

interface SidebarProps {
  collapsed: boolean
  chats: Chat[]
  projects: Project[]
  activeId: string
  onSelect: (id: string) => void
  onNew: (projectId?: string | null) => void
  /** Returns the new project's id so it can be expanded straight away. */
  onNewProject: (name: string) => string
  /** `null` moves the chat back out to the flat history. */
  onMoveChat: (chatId: string, projectId: string | null) => void
  onRenameChat: (chatId: string, title: string) => void
  onDeleteChat: (chatId: string) => void
  onRenameProject: (projectId: string, name: string) => void
  /** Deleting a project keeps its chats — they return to the flat history. */
  onDeleteProject: (projectId: string) => void
  onCollapse: () => void
  onExpand: () => void
  onOpenSettings: () => void
}

const DAY = 86_400_000
const MENU_WIDTH = 210
const VIEW_KEY = 'talvrin-sidebar-view'

/**
 * Bucket chats the way a chat history reads: newest first, labelled by how
 * long ago the chat was started rather than by a raw date.
 */
function groupByRecency(chats: Chat[]) {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()

  const buckets: { label: string; from: number; chats: Chat[] }[] = [
    { label: 'Today', from: today, chats: [] },
    { label: 'Yesterday', from: today - DAY, chats: [] },
    { label: 'Previous 7 days', from: today - 7 * DAY, chats: [] },
    { label: 'Previous 30 days', from: today - 30 * DAY, chats: [] },
    { label: 'Older', from: -Infinity, chats: [] },
  ]

  for (const c of [...chats].sort((a, b) => b.createdAt - a.createdAt)) {
    buckets.find((b) => c.createdAt >= b.from)!.chats.push(c)
  }

  return buckets.filter((b) => b.chats.length > 0)
}

export default function Sidebar({
  collapsed,
  chats,
  projects,
  activeId,
  onSelect,
  onNew,
  onNewProject,
  onMoveChat,
  onRenameChat,
  onDeleteChat,
  onRenameProject,
  onDeleteProject,
  onCollapse,
  onExpand,
  onOpenSettings,
}: SidebarProps) {
  // A chat only enters the history once it has actually been asked something,
  // so an untouched "New chat" never litters the list.
  const started = chats.filter((c) => c.messages.length > 0)
  const history = groupByRecency(started.filter((c) => c.projectId === null))

  const [openProjects, setOpenProjects] = useState<string[]>([])
  const [naming, setNaming] = useState(false)
  const [draftName, setDraftName] = useState('')
  const nameRef = useRef<HTMLInputElement>(null)

  // The row menu is positioned `fixed` from the trigger's rect so the
  // scrolling nav can't clip it. It targets either a chat or a project.
  type MenuTarget =
    | { kind: 'chat'; chat: Chat }
    | { kind: 'project'; project: Project }
  const [menu, setMenu] = useState<
    { target: MenuTarget; anchor: DOMRect; clear: DOMRect | null } | null
  >(null)
  const [confirming, setConfirming] = useState(false)
  // Row being renamed in place, keyed by id.
  const [renaming, setRenaming] = useState<{ id: string; value: string } | null>(
    null
  )
  // Chat currently being dragged, and the project row it is hovering.
  const [dragging, setDragging] = useState<Chat | null>(null)
  const [dropTarget, setDropTarget] = useState<string | null>(null)

  // Chats and projects are two views of the same panel, not two stacked
  // lists — the segmented switch below decides which one is showing.
  const [view, setView] = useState<'chats' | 'projects'>(() =>
    localStorage.getItem(VIEW_KEY) === 'projects' ? 'projects' : 'chats'
  )

  useEffect(() => {
    if (naming) nameRef.current?.focus()
  }, [naming])

  useEffect(() => {
    localStorage.setItem(VIEW_KEY, view)
  }, [view])

  /** Rail shortcut: open the panel already showing the right view. */
  const openView = (next: 'chats' | 'projects') => {
    setView(next)
    onExpand()
  }

  const closeMenu = useCallback(() => {
    setMenu(null)
    setConfirming(false)
  }, [])

  const commitProject = () => {
    const name = draftName.trim()
    if (name) {
      const id = onNewProject(name)
      setOpenProjects((prev) => [...prev, id])
      setDraftName('')
    }
    setNaming(false)
  }

  const toggleProject = (id: string) =>
    setOpenProjects((prev) =>
      prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]
    )

  const expandProject = (id: string) =>
    setOpenProjects((prev) => (prev.includes(id) ? prev : [...prev, id]))

  const move = (chatId: string, projectId: string | null) => {
    onMoveChat(chatId, projectId)
    if (projectId) expandProject(projectId)
    setMenu(null)
  }

  const menuKey = (t: MenuTarget) =>
    t.kind === 'chat' ? `chat:${t.chat.id}` : `project:${t.project.id}`

  /** Clicking the trigger of an already-open menu closes it, as it should. */
  const toggleMenu = (target: MenuTarget, el: HTMLElement) => {
    if (menu && menuKey(menu.target) === menuKey(target)) {
      closeMenu()
      return
    }
    setConfirming(false)
    setMenu({
      target,
      anchor: el.getBoundingClientRect(),
      // The row, so the menu doesn't sit on top of the item it acts on.
      clear: el.parentElement?.getBoundingClientRect() ?? null,
    })
  }

  const startRename = (id: string, value: string) => {
    setMenu(null)
    setConfirming(false)
    setRenaming({ id, value })
  }

  const commitRename = (kind: 'chat' | 'project') => {
    if (!renaming) return
    const value = renaming.value.trim()
    if (value) {
      if (kind === 'chat') onRenameChat(renaming.id, value)
      else onRenameProject(renaming.id, value)
    }
    setRenaming(null)
  }

  /** Shared inline editor for renaming a chat or a project in place. */
  const renameRow = (kind: 'chat' | 'project', nested = false) => (
    <div
      className={cn(
        'mb-0.5 flex items-center gap-1.5 rounded-full bg-sidebar-accent py-1 pr-2',
        nested ? 'pl-7' : 'pl-3'
      )}
    >
      {kind === 'project' ? (
        <Folder className="h-3.5 w-3.5 shrink-0 text-sidebar-muted" />
      ) : (
        <MessageSquare className="h-3.5 w-3.5 shrink-0 text-sidebar-muted" />
      )}
      <input
        autoFocus
        value={renaming?.value ?? ''}
        onChange={(e) =>
          setRenaming((r) => (r ? { ...r, value: e.target.value } : r))
        }
        onBlur={() => commitRename(kind)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commitRename(kind)
          if (e.key === 'Escape') setRenaming(null)
        }}
        className="min-w-0 flex-1 bg-transparent py-1 text-[13px] outline-none"
      />
      <button
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => commitRename(kind)}
        aria-label="Save name"
        className="shrink-0 text-sidebar-muted hover:text-sidebar-foreground"
      >
        <Check className="h-3.5 w-3.5" />
      </button>
      <button
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => setRenaming(null)}
        aria-label="Cancel rename"
        className="shrink-0 text-sidebar-muted hover:text-sidebar-foreground"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )

  const tab = collapsed ? -1 : 0
  const rail = collapsed ? 0 : -1

  const chatRow = (c: Chat, nested = false) => {
    if (renaming?.id === c.id) return <div key={c.id}>{renameRow('chat', nested)}</div>

    const selected = c.id === activeId
    const menuOpen = menu?.target.kind === 'chat' && menu.target.chat.id === c.id

    return (
      <div
        key={c.id}
        draggable
        onDragStart={(e) => {
          e.dataTransfer.setData('text/plain', c.id)
          e.dataTransfer.effectAllowed = 'move'
          setDragging(c)
        }}
        onDragEnd={() => {
          setDragging(null)
          setDropTarget(null)
        }}
        className={cn(
          'group relative flex items-center rounded-full transition-colors',
          selected
            ? 'bg-sidebar-active text-sidebar-foreground'
            : 'text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-foreground',
          dragging?.id === c.id && 'opacity-40'
        )}
      >
        <button
          onClick={() => onSelect(c.id)}
          tabIndex={tab}
          className={cn(
            'flex min-w-0 flex-1 items-center gap-2.5 py-[7px] pr-8 text-left text-[13.5px]',
            nested ? 'pl-8' : 'pl-3',
            selected && 'font-medium'
          )}
        >
          <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-70" />
          <span className="truncate">{c.title}</span>
        </button>

        <button
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => toggleMenu({ kind: 'chat', chat: c }, e.currentTarget)}
          tabIndex={tab}
          aria-label={`Options for "${c.title}"`}
          title="More options"
          className={cn(
            'absolute right-1 grid h-6 w-6 place-items-center rounded-full transition-opacity',
            'hover:bg-sidebar-foreground/10',
            menuOpen || selected
              ? 'opacity-100'
              : 'opacity-0 focus-visible:opacity-100 group-hover:opacity-100'
          )}
        >
          <Ellipsis className="h-3.5 w-3.5" />
        </button>
      </div>
    )
  }

  return (
    <aside
      className={cn(
        'relative flex shrink-0 flex-col overflow-hidden text-sidebar-foreground',
        // Acrylic: a translucent tint over a blurred, slightly saturated
        // backdrop, finished with a hairline edge so it reads as a pane.
        'bg-sidebar/60 backdrop-blur-2xl backdrop-saturate-150',
        'border-r border-sidebar-border/60',
        'transition-[width] duration-300 ease-out',
        collapsed ? 'w-[56px]' : 'w-[276px]'
      )}
    >
      {/* ---------------- Collapsed icon rail ---------------- */}
      <div
        className={cn(
          'absolute inset-y-0 left-0 flex w-[56px] flex-col items-center py-4',
          'transition-opacity duration-200',
          collapsed ? 'opacity-100' : 'pointer-events-none opacity-0'
        )}
      >
        {/* The mark doubles as the expand control — it swaps to the panel
            icon on hover, the way a collapsed rail usually behaves. */}
        <button
          onClick={onExpand}
          tabIndex={rail}
          aria-label="Expand sidebar"
          title="Expand sidebar"
          className="group relative grid h-[34px] w-[34px] shrink-0 place-items-center rounded-[10px] transition-colors hover:bg-sidebar-accent"
        >
          <img
            src={brandIcon}
            alt=""
            className="h-[30px] w-[30px] rounded-[9px] shadow-lg shadow-indigo-500/30 transition-opacity group-hover:opacity-0"
          />
          <PanelLeft className="absolute h-[18px] w-[18px] text-sidebar-muted opacity-0 transition-opacity group-hover:opacity-100" />
        </button>

        <div className="mt-5 flex flex-col items-center gap-1.5">
          {(
            [
              {
                key: 'new',
                label: 'New chat',
                Icon: SquarePen,
                onClick: () => onNew(null),
              },
              {
                key: 'projects',
                label: 'Projects',
                Icon: Folder,
                onClick: () => openView('projects'),
              },
              {
                key: 'recent',
                label: 'Recent chats',
                Icon: MessageSquare,
                onClick: () => openView('chats'),
              },
            ] as const
          ).map(({ key, label, Icon, onClick }) => (
            <button
              key={key}
              onClick={onClick}
              tabIndex={rail}
              aria-label={label}
              title={label}
              className="grid h-9 w-9 place-items-center rounded-[10px] text-sidebar-muted transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
            >
              <Icon className="h-[18px] w-[18px]" />
            </button>
          ))}
        </div>

        {/* The rail has no room for a footer, so the avatar is the way in. */}
        <button
          onClick={onOpenSettings}
          tabIndex={rail}
          aria-label="Settings"
          title="Settings"
          className="mt-auto grid h-8 w-8 shrink-0 place-items-center rounded-full bg-sidebar-accent text-[11px] font-semibold text-sidebar-muted transition-colors hover:text-sidebar-foreground"
        >
          {currentUser.initials}
        </button>
      </div>

      {/* ---------------- Expanded panel ---------------- */}
      <div
        className={cn(
          'flex w-[276px] flex-1 flex-col overflow-hidden transition-opacity duration-200',
          collapsed ? 'pointer-events-none opacity-0' : 'opacity-100'
        )}
      >
        {/* Brand + collapse */}
        {/* Single row: the lockup already carries the name, and its height
            is matched to the rail's mark so the logo barely moves when the
            sidebar collapses. */}
        <div className="flex items-center gap-2.5 px-4 pb-4 pt-4">
          <img
            src={wordmarkOnDark}
            alt="Talvrin"
            className="brand-on-dark h-8 w-auto shrink-0"
          />
          <img
            src={wordmarkOnLight}
            alt="Talvrin"
            className="brand-on-light h-8 w-auto shrink-0"
          />
          <button
            onClick={onCollapse}
            aria-label="Hide sidebar"
            tabIndex={tab}
            className="ml-auto grid h-8 w-8 shrink-0 place-items-center rounded-lg text-sidebar-muted transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
          >
            <PanelLeftClose className="h-[17px] w-[17px]" />
          </button>
        </div>

        <button
          onClick={() => onNew(null)}
          tabIndex={tab}
          className="mx-3 mb-3 flex items-center gap-2.5 rounded-full bg-sidebar-accent px-4 py-2.5 text-left text-[13.5px] font-medium transition-all hover:brightness-125 active:scale-[0.985]"
        >
          <Plus className="h-4 w-4" />
          New chat
        </button>

        {/* Segmented switch — chats and projects share the panel below. */}
        <div
          role="tablist"
          aria-label="Sidebar view"
          className="mx-3 mb-2 grid grid-cols-2 gap-1 rounded-full bg-sidebar-accent p-1"
        >
          {(
            [
              { key: 'chats', label: 'Chats', count: history.reduce((n, b) => n + b.chats.length, 0) },
              { key: 'projects', label: 'Projects', count: projects.length },
            ] as const
          ).map(({ key, label, count }) => (
            <button
              key={key}
              role="tab"
              aria-selected={view === key}
              onClick={() => setView(key)}
              tabIndex={tab}
              className={cn(
                'flex items-center justify-center gap-1.5 rounded-full py-1.5 text-[13px] transition-colors',
                view === key
                  ? 'bg-sidebar font-medium text-sidebar-foreground ring-1 ring-inset ring-sidebar-border'
                  : 'text-sidebar-muted hover:text-sidebar-foreground'
              )}
            >
              {label}
              {count > 0 && (
                <span className="text-[11px] tabular-nums opacity-60">{count}</span>
              )}
            </button>
          ))}
        </div>

        <nav className="scrollbar-slim flex-1 overflow-y-auto px-2 pb-2">
          {/* ---------------- Projects ---------------- */}
          {view === 'projects' && (
          <>
          <button
            onClick={() => (naming ? nameRef.current?.focus() : setNaming(true))}
            tabIndex={tab}
            className="mb-0.5 flex w-full items-center gap-2.5 rounded-full py-[7px] pl-3 pr-3 text-left text-[13.5px] text-sidebar-muted transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
          >
            <Plus className="h-4 w-4 shrink-0" />
            New project
          </button>

          {naming && (
            <div className="mb-0.5 flex items-center gap-1.5 rounded-lg bg-sidebar-accent px-2.5 py-1.5">
              <Folder className="h-3.5 w-3.5 shrink-0 text-sidebar-muted" />
              <input
                ref={nameRef}
                value={draftName}
                onChange={(e) => setDraftName(e.target.value)}
                onBlur={commitProject}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') commitProject()
                  if (e.key === 'Escape') {
                    setDraftName('')
                    setNaming(false)
                  }
                }}
                placeholder="Project name"
                className="min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-sidebar-muted/70"
              />
              {/* preventDefault on mousedown so the blur handler doesn't
                  commit-and-close before the click lands. */}
              <button
                onMouseDown={(e) => e.preventDefault()}
                onClick={commitProject}
                aria-label="Create project"
                className="text-sidebar-muted hover:text-sidebar-foreground"
              >
                <Check className="h-3.5 w-3.5" />
              </button>
              <button
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  setDraftName('')
                  setNaming(false)
                }}
                aria-label="Cancel"
                className="text-sidebar-muted hover:text-sidebar-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {projects.length === 0 && !naming && (
            <p className="px-3 pb-1 pt-1 text-[12px] leading-relaxed text-sidebar-muted/70">
              Group related chats — a curve, an issuer, a mandate.
            </p>
          )}

          {projects.map((p) => {
            const open = openProjects.includes(p.id)
            const inProject = started
              .filter((c) => c.projectId === p.id)
              .sort((a, b) => b.createdAt - a.createdAt)

            if (renaming?.id === p.id)
              return <div key={p.id}>{renameRow('project')}</div>

            const pMenuOpen =
              menu?.target.kind === 'project' && menu.target.project.id === p.id

            return (
              <div key={p.id}>
                <div
                  className={cn(
                    'group relative flex items-center rounded-full transition-colors',
                    dropTarget === p.id
                      ? 'bg-sidebar-active text-sidebar-foreground ring-1 ring-inset ring-primary/60'
                      : 'text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-foreground'
                  )}
                >
                <button
                  onClick={() => toggleProject(p.id)}
                  tabIndex={tab}
                  aria-expanded={open}
                  onDragOver={(e) => {
                    if (!dragging || dragging.projectId === p.id) return
                    e.preventDefault()
                    e.dataTransfer.dropEffect = 'move'
                    setDropTarget(p.id)
                  }}
                  onDragLeave={(e) => {
                    // Ignore the dragleave fired when crossing into a child.
                    if (e.currentTarget.contains(e.relatedTarget as Node)) return
                    setDropTarget((t) => (t === p.id ? null : t))
                  }}
                  onDrop={(e) => {
                    e.preventDefault()
                    const id = e.dataTransfer.getData('text/plain')
                    if (id) move(id, p.id)
                    setDropTarget(null)
                  }}
                  className="flex min-w-0 flex-1 items-center gap-2 py-[7px] pl-2.5 pr-8 text-left text-[13.5px]"
                >
                  <ChevronRight
                    className={cn(
                      'h-3.5 w-3.5 shrink-0 transition-transform duration-200',
                      open && 'rotate-90'
                    )}
                  />
                  <Folder className="h-3.5 w-3.5 shrink-0 opacity-70" />
                  <span className="truncate">{p.name}</span>
                  {inProject.length > 0 && (
                    <span className="ml-auto shrink-0 text-[11px] tabular-nums opacity-60">
                      {inProject.length}
                    </span>
                  )}
                </button>

                <button
                  onMouseDown={(e) => e.stopPropagation()}
                  onClick={(e) =>
                    toggleMenu({ kind: 'project', project: p }, e.currentTarget)
                  }
                  tabIndex={tab}
                  aria-label={`Options for "${p.name}"`}
                  title="More options"
                  className={cn(
                    'absolute right-1 grid h-6 w-6 place-items-center rounded-full transition-opacity',
                    'hover:bg-sidebar-foreground/10',
                    pMenuOpen
                      ? 'opacity-100'
                      : 'opacity-0 focus-visible:opacity-100 group-hover:opacity-100'
                  )}
                >
                  <Ellipsis className="h-3.5 w-3.5" />
                </button>
                </div>

                {open && (
                  <>
                    {inProject.map((c) => chatRow(c, true))}
                    <button
                      onClick={() => onNew(p.id)}
                      tabIndex={tab}
                      className="flex w-full items-center gap-2.5 rounded-full py-[7px] pl-8 pr-3 text-left text-[13px] text-sidebar-muted transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
                    >
                      <Plus className="h-3.5 w-3.5 shrink-0 opacity-70" />
                      New chat
                    </button>
                  </>
                )}
              </div>
            )
          })}

          {/* Drop zone for dragging a chat back out of its project. */}
          {dragging?.projectId && (
            <div
              onDragOver={(e) => {
                e.preventDefault()
                e.dataTransfer.dropEffect = 'move'
                setDropTarget('__root__')
              }}
              onDragLeave={() =>
                setDropTarget((t) => (t === '__root__' ? null : t))
              }
              onDrop={(e) => {
                e.preventDefault()
                const id = e.dataTransfer.getData('text/plain')
                if (id) move(id, null)
                setDropTarget(null)
              }}
              className={cn(
                'mt-2 flex items-center gap-2 rounded-lg border border-dashed px-3 py-2 text-[12.5px] transition-colors',
                dropTarget === '__root__'
                  ? 'border-primary/70 bg-sidebar-active text-sidebar-foreground'
                  : 'border-sidebar-border text-sidebar-muted'
              )}
            >
              <FolderMinus className="h-3.5 w-3.5 shrink-0" />
              Move out of project
            </div>
          )}

          </>
          )}

          {/* ---------------- Chat history ---------------- */}
          {view === 'chats' &&
            (history.length === 0 ? (
              <p className="px-3 pt-1 text-[12px] leading-relaxed text-sidebar-muted/70">
                No chats yet — ask something to start one.
              </p>
            ) : (
              history.map((bucket) => (
                <div key={bucket.label}>
                  <div className="px-3 pb-1 pt-3 text-[10.5px] font-semibold uppercase tracking-widest text-sidebar-muted">
                    {bucket.label}
                  </div>
                  {bucket.chats.map((c) => chatRow(c))}
                </div>
              ))
            ))}
        </nav>

        <div className="flex items-center gap-2.5 border-t border-sidebar-border p-3 text-[13.5px]">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-sidebar-accent text-[11px] font-semibold text-sidebar-muted">
            {currentUser.initials}
          </span>
          <span className="truncate">{currentUser.name}</span>
          <span className="ml-auto shrink-0 rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-primary">
            {currentUser.plan}
          </span>
          <button
            onClick={onOpenSettings}
            tabIndex={tab}
            aria-label="Settings"
            title="Settings"
            className="grid h-7 w-7 shrink-0 place-items-center rounded-lg text-sidebar-muted transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
          >
            <Settings className="h-[17px] w-[17px]" />
          </button>
        </div>
      </div>

      {/* ---------------- Row menu ---------------- */}
      {menu && (
        <PopoverMenu
          anchor={menu.anchor}
          clear={menu.clear}
          width={MENU_WIDTH}
          onClose={closeMenu}
          className="border-sidebar-border bg-sidebar"
        >
          {confirming ? (
            <>
              <p className="px-2.5 pb-2 pt-1 text-[12px] leading-relaxed text-sidebar-muted">
                {menu.target.kind === 'chat'
                  ? 'Delete this chat? This cannot be undone.'
                  : 'Delete this project? Its chats are kept and move back to Chats.'}
              </p>
              <div className="flex gap-1">
                <button
                  role="menuitem"
                  onClick={() => {
                    setConfirming(false)
                    setMenu(null)
                  }}
                  className="flex-1 rounded-lg px-2.5 py-1.5 text-[13px] text-sidebar-muted transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
                >
                  Cancel
                </button>
                <button
                  role="menuitem"
                  onClick={() => {
                    if (menu.target.kind === 'chat')
                      onDeleteChat(menu.target.chat.id)
                    else onDeleteProject(menu.target.project.id)
                    setConfirming(false)
                    setMenu(null)
                  }}
                  className="flex-1 rounded-lg bg-destructive/15 px-2.5 py-1.5 text-[13px] font-medium text-destructive transition-colors hover:bg-destructive/25"
                >
                  Delete
                </button>
              </div>
            </>
          ) : (
            <>
              {menu.target.kind === 'chat' && (
                <>
                  <div className="px-2.5 pb-1 pt-1 text-[10.5px] font-semibold uppercase tracking-widest text-sidebar-muted">
                    Move to project
                  </div>

                  {projects.length === 0 && (
                    <p className="px-2.5 pb-1.5 text-[12px] leading-relaxed text-sidebar-muted/70">
                      No projects yet — add one from the Projects tab.
                    </p>
                  )}

                  {projects.map((p) => {
                    const chat = menu.target.kind === 'chat' ? menu.target.chat : null
                    const current = chat?.projectId === p.id
                    return (
                      <button
                        key={p.id}
                        role="menuitem"
                        onClick={() => chat && !current && move(chat.id, p.id)}
                        className={cn(
                          'flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] transition-colors',
                          current
                            ? 'text-sidebar-foreground'
                            : 'text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-foreground'
                        )}
                      >
                        <Folder className="h-3.5 w-3.5 shrink-0 opacity-70" />
                        <span className="truncate">{p.name}</span>
                        {current && <Check className="ml-auto h-3.5 w-3.5 shrink-0" />}
                      </button>
                    )
                  })}

                  {menu.target.chat.projectId && (
                    <button
                      role="menuitem"
                      onClick={() =>
                        menu.target.kind === 'chat' && move(menu.target.chat.id, null)
                      }
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] text-sidebar-muted transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
                    >
                      <FolderMinus className="h-3.5 w-3.5 shrink-0 opacity-70" />
                      Remove from project
                    </button>
                  )}

                  <div className="my-1 h-px bg-sidebar-border" />
                </>
              )}

              <button
                role="menuitem"
                onClick={() =>
                  startRename(
                    menu.target.kind === 'chat'
                      ? menu.target.chat.id
                      : menu.target.project.id,
                    menu.target.kind === 'chat'
                      ? menu.target.chat.title
                      : menu.target.project.name
                  )
                }
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] text-sidebar-muted transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
              >
                <Pencil className="h-3.5 w-3.5 shrink-0 opacity-70" />
                Rename
              </button>

              <button
                role="menuitem"
                onClick={() => setConfirming(true)}
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] text-destructive transition-colors hover:bg-destructive/15"
              >
                <Trash2 className="h-3.5 w-3.5 shrink-0 opacity-80" />
                Delete
              </button>
            </>
          )}
        </PopoverMenu>
      )}

    </aside>
  )
}
