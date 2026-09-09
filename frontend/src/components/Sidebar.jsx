export default function Sidebar({ collapsed, threads, activeId, onSelect, onNew }) {
  return (
    <aside className={collapsed ? 'sidebar collapsed' : 'sidebar'}>
      <div className="sidebar-head">
        <div className="brand-mark">T</div>
        <div>
          <div className="brand-name">Talvrin</div>
          <div className="brand-sub">Public markets research</div>
        </div>
      </div>

      <button className="new-chat" onClick={onNew}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M12 5v14M5 12h14" />
        </svg>
        New research thread
      </button>

      <div className="thread-label">Recent</div>
      <nav className="thread-list">
        {threads.map((t) => (
          <button
            key={t.id}
            className={t.id === activeId ? 'thread active' : 'thread'}
            onClick={() => onSelect(t.id)}
          >
            {t.title}
          </button>
        ))}
      </nav>

      <div className="sidebar-foot">
        <div className="avatar">VK</div>
        <div>
          <div>Vignesh K.</div>
          <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>Free plan</div>
        </div>
      </div>
    </aside>
  )
}
