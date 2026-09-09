import { useRef, useEffect } from 'react'
import { ArrowUp, Plus } from './icons.jsx'

export default function Composer({ value, onChange, onSend, disabled }) {
  const ref = useRef(null)

  // Auto-grow the textarea with its content.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 208) + 'px'
  }, [value])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  return (
    <div className="composer-wrap">
      <div className="composer">
        <button className="composer-btn" aria-label="Attach a document" title="Attach a document">
          <Plus size={17} />
        </button>

        <textarea
          ref={ref}
          rows={1}
          value={value}
          placeholder="Ask about an instrument, convention or calculation…"
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
        />

        <button
          className="send"
          onClick={onSend}
          disabled={disabled || !value.trim()}
          aria-label="Send message"
        >
          <ArrowUp size={16} />
        </button>
      </div>

      <div className="disclaimer">
        Source-linked facts and reproducible calculations.{' '}
        <b>Talvrin does not give investment advice.</b> Prototype — no backend connected.
      </div>
    </div>
  )
}
