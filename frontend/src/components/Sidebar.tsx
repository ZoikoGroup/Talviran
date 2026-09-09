import { Plus, MessageSquare, Sun, Moon, Settings, PanelLeftClose } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface Thread {
  id: number
  title: string
  messages: unknown[]
}

interface SidebarProps {
  collapsed: boolean
  threads: Thread[]
  activeId: number
  onSelect: (id: number) => void
  onNew: () => void
  onCollapse: () => void
  theme: 'dark' | 'light'
  onToggleTheme: () => void
}

export default function Sidebar({
  collapsed,
  threads,
  activeId,
  onSelect,
  onNew,
  onCollapse,
  theme,
  onToggleTheme,
}: SidebarProps) {
  const started = threads.filter((t) => t.messages.length > 0)

  return (
    <aside
      // `w-0 + overflow-hidden` when collapsed rather than a negative margin:
      // the panel actually leaves the layout, so nothing bleeds at the edge
      // and its contents can't be tabbed into while hidden.
      aria-hidden={collapsed}
      className={cn(
        'flex shrink-0 flex-col overflow-hidden border-r bg-sidebar',
        'transition-[width] duration-300 ease-out',
        collapsed ? 'w-0 border-r-0' : 'w-[276px] border-border'
      )}
    >
      <div className="flex w-[276px] flex-1 flex-col overflow-hidden">
        {/* Brand + collapse */}
        <div className="flex items-center gap-2.5 px-4 pb-3.5 pt-4">
          <div className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-[9px] bg-gradient-to-br from-indigo-500 to-purple-500 text-sm font-bold text-white shadow-lg shadow-indigo-500/30">
            T
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[15.5px] font-semibold leading-tight tracking-tight">
              Talvrin
            </div>
            <div className="mt-0.5 truncate text-[11.5px] text-muted-foreground">
              Public markets research
            </div>
          </div>
          <button
            onClick={onCollapse}
            aria-label="Hide sidebar"
            tabIndex={collapsed ? -1 : 0}
            className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <PanelLeftClose className="h-[17px] w-[17px]" />
          </button>
        </div>

        <button
          onClick={onNew}
          tabIndex={collapsed ? -1 : 0}
          className="mx-3 mb-4 flex items-center gap-2.5 rounded-xl border border-border bg-background/60 px-3.5 py-2.5 text-left text-[13.5px] font-medium transition-all hover:bg-accent active:scale-[0.985]"
        >
          <Plus className="h-4 w-4" />
          New research thread
        </button>

        <nav className="scrollbar-slim flex-1 overflow-y-auto px-2 pb-2">
          {started.length > 0 && (
            <>
              <div className="px-3 pb-1.5 pt-3 text-[10.5px] font-semibold uppercase tracking-widest text-muted-foreground/70">
                Today
              </div>
              {started.map((t) => (
                <button
                  key={t.id}
                  onClick={() => onSelect(t.id)}
                  tabIndex={collapsed ? -1 : 0}
                  className={cn(
                    'flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13.5px] transition-colors',
                    t.id === activeId
                      ? 'bg-accent font-medium text-foreground'
                      : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground'
                  )}
                >
                  <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-60" />
                  <span className="truncate">{t.title}</span>
                </button>
              ))}
            </>
          )}
        </nav>

        <div className="flex flex-col gap-0.5 border-t border-border p-3">
          <button
            onClick={onToggleTheme}
            tabIndex={collapsed ? -1 : 0}
            className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13.5px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            {theme === 'dark' ? (
              <Sun className="h-4 w-4" />
            ) : (
              <Moon className="h-4 w-4" />
            )}
            {theme === 'dark' ? 'Light mode' : 'Dark mode'}
          </button>

          <button
            tabIndex={collapsed ? -1 : 0}
            className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13.5px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <Settings className="h-4 w-4" />
            Settings
          </button>

          <div className="mt-0.5 flex items-center gap-2.5 border-t border-border pt-2.5 text-[13.5px]">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent text-[11px] font-semibold text-muted-foreground">
              VK
            </span>
            <span className="truncate">Vignesh K.</span>
            <span className="ml-auto shrink-0 rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-primary">
              FREE
            </span>
          </div>
        </div>
      </div>
    </aside>
  )
}
