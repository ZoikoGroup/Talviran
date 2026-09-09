import { Plus, MessageSquare, Sun, Moon, Settings } from 'lucide-react'
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
  theme: 'dark' | 'light'
  onToggleTheme: () => void
}

export default function Sidebar({
  collapsed,
  threads,
  activeId,
  onSelect,
  onNew,
  theme,
  onToggleTheme,
}: SidebarProps) {
  const started = threads.filter((t) => t.messages.length > 0)

  const ThreadButton = ({ t }: { t: Thread }) => (
    <button
      onClick={() => onSelect(t.id)}
      className={cn(
        'flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13.5px] transition-colors',
        t.id === activeId
          ? 'bg-accent font-medium text-foreground'
          : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
      )}
    >
      <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-60" />
      <span className="truncate">{t.title}</span>
    </button>
  )

  return (
    <aside
      className={cn(
        'flex w-[276px] shrink-0 flex-col border-r border-border bg-card transition-[margin] duration-300',
        collapsed && '-ml-[276px]'
      )}
    >
      <div className="flex items-center gap-2.5 px-4 pb-3.5 pt-4">
        <div className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-[9px] bg-gradient-to-br from-indigo-500 to-purple-500 text-sm font-bold text-white shadow-lg shadow-indigo-500/30">
          T
        </div>
        <div>
          <div className="text-[15.5px] font-semibold leading-tight tracking-tight">
            Talvrin
          </div>
          <div className="mt-0.5 text-[11.5px] text-muted-foreground/70">
            Public markets research
          </div>
        </div>
      </div>

      <button
        onClick={onNew}
        className="mx-3 mb-4 flex items-center gap-2.5 rounded-xl border border-border bg-secondary px-3.5 py-2.5 text-left text-[13.5px] font-medium transition-all hover:bg-accent active:scale-[0.985]"
      >
        <Plus className="h-4 w-4" />
        New research thread
      </button>

      <nav className="flex-1 overflow-y-auto px-2 pb-2 scrollbar-slim">
        {started.length > 0 && (
          <>
            <div className="px-3 pb-1.5 pt-3 text-[10.5px] font-semibold uppercase tracking-widest text-muted-foreground/60">
              Today
            </div>
            {started.map((t) => (
              <ThreadButton key={t.id} t={t} />
            ))}
          </>
        )}
      </nav>

      <div className="flex flex-col gap-0.5 border-t border-border p-3">
        <button
          onClick={onToggleTheme}
          className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13.5px] transition-colors hover:bg-secondary"
        >
          {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          {theme === 'dark' ? 'Light mode' : 'Dark mode'}
        </button>

        <button className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13.5px] transition-colors hover:bg-secondary">
          <Settings className="h-4 w-4" />
          Settings
        </button>

        <div className="flex items-center gap-2.5 px-2.5 py-2 text-[13.5px]">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-secondary text-[11px] font-semibold text-muted-foreground">
            VK
          </span>
          <span>Vignesh K.</span>
          <span className="ml-auto rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-primary">
            FREE
          </span>
        </div>
      </div>
    </aside>
  )
}
