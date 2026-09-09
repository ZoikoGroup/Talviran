import { useState } from 'react'
import { Shield, Link, Doc, Book, Table, Chevron, Info } from './icons.jsx'

const CITE_ICON = { doc: Doc, book: Book, link: Link }

/** Render **bold** spans without pulling in a markdown dependency. */
function RichText({ children }) {
  const parts = String(children).split(/(\*\*[^*]+\*\*)/g)
  return parts.map((p, i) =>
    p.startsWith('**') && p.endsWith('**')
      ? <strong key={i}>{p.slice(2, -2)}</strong>
      : <span key={i}>{p}</span>
  )
}

function FactTable({ title, rows }) {
  return (
    <div className="facts">
      <div className="facts-head">
        <Table size={13} />
        {title}
      </div>
      {rows.map(([k, v]) => (
        <div className="fact-row" key={k}>
          <div className="fact-key">{k}</div>
          <div className="fact-val">{v}</div>
        </div>
      ))}
    </div>
  )
}

function Evidence({ citations }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="evidence">
      <button className="evidence-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <Shield size={14} />
        Evidence
        <span className="count">
          {citations.length} source{citations.length === 1 ? '' : 's'}
          <Chevron size={13} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .18s' }} />
        </span>
      </button>

      {open && (
        <div className="evidence-body">
          {citations.map((c, i) => {
            const CiteIcon = CITE_ICON[c.kind] ?? Link
            return (
              <div className="cite" key={i}>
                <span className="cite-icon"><CiteIcon size={13} /></span>
                <span className="cite-main">
                  <div className="cite-label">{c.label}</div>
                  {c.meta && <div className="cite-meta">{c.meta}</div>}
                </span>
                <span className={`pill ${c.pill.toLowerCase()}`}>{c.pill}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function Message({ role, text, facts, citations = [], note }) {
  if (role === 'user') {
    return (
      <div className="msg user">
        <div className="bubble">{text}</div>
      </div>
    )
  }

  return (
    <div className="msg bot">
      <div className="bot-mark">T</div>
      <div className="bot-body">
        <div className="bot-name">Talvrin</div>
        <div className="prose"><RichText>{text}</RichText></div>

        {facts && <FactTable {...facts} />}
        {citations.length > 0 && <Evidence citations={citations} />}

        {note && (
          <div className="note">
            <Info size={14} />
            <span>{note}</span>
          </div>
        )}
      </div>
    </div>
  )
}
