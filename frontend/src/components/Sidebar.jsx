import { Plus, Chat, Sun, Moon, Settings } from './icons.jsx'

export default function Sidebar({ collapsed, threads, activeId, onSelect, onNew, theme, onToggleTheme }) {
  const started = threads.filter((t) => t.messages.length > 0)
  const fresh = threads.filter((t) => t.messages.length === 0)

  return (
    <aside className={collapsed ? 'sidebar collapsed' : 'sidebar'}>
      <div className="brand">
        <div className="brand-mark">T</div>
        <div>
          <div className="brand-name">Talvrin</div>
          <div className="brand-sub">Public markets research</div>
        </div>
      </div>

      <button className="new-thread" onClick={onNew}>
        <Plus size={15} />
        New research thread
      </button>

      <nav className="thread-list">
        {fresh.length > 0 && (
          <>
            <div className="group-label">Draft</div>
            {fresh.map((t) => (
              <button
                key={t.id}
                className={t.id === activeId ? 'thread active' : 'thread'}
                onClick={() => onSelect(t.id)}
              >
                <Chat size={14} />
                <span>{t.title}</span>
              </button>
            ))}
          </>
        )}

        {started.length > 0 && (
          <>
            <div className="group-label">Today</div>
            {started.map((t) => (
              <button
                key={t.id}
                className={t.id === activeId ? 'thread active' : 'thread'}
                onClick={() => onSelect(t.id)}
              >
                <Chat size={14} />
                <span>{t.title}</span>
              </button>
            ))}
          </>
        )}
      </nav>

      <div className="sidebar-foot">
        <button className="foot-row" onClick={onToggleTheme}>
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          {theme === 'dark' ? 'Light mode' : 'Dark mode'}
        </button>

        <button className="foot-row">
          <Settings size={16} />
          Settings
        </button>

        <div className="foot-row" style={{ cursor: 'default' }}>
          <span className="avatar">VK</span>
          <span>Vignesh K.</span>
          <span className="plan-tag">FREE</span>
        </div>
      </div>
    </aside>
  )
}
