export default function Message({ role, text, citations = [], note }) {
  const isUser = role === 'user'

  return (
    <div className="msg">
      <div className={isUser ? 'msg-avatar user' : 'msg-avatar bot'}>
        {isUser ? 'VK' : 'T'}
      </div>

      <div className="msg-body">
        <div className="msg-role">{isUser ? 'You' : 'Talvrin'}</div>
        <div className="msg-text">{text}</div>

        {citations.length > 0 && (
          <div className="evidence">
            <div className="evidence-head">Evidence</div>
            {citations.map((c, i) => (
              <div className="cite" key={i}>
                <span className="cite-dot" />
                <span>{c.label}</span>
                <span className="cite-tag">{c.tag}</span>
              </div>
            ))}
          </div>
        )}

        {note && (
          <div style={{ marginTop: 10, fontSize: 11.5, color: 'var(--text-faint)', fontStyle: 'italic' }}>
            {note}
          </div>
        )}
      </div>
    </div>
  )
}
