import { useRef, useEffect } from 'react'

export default function Composer({ value, onChange, onSend, disabled }) {
  const ref = useRef(null)

  // Auto-grow the textarea with its content.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 200) + 'px'
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
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 19V5M5 12l7-7 7 7" />
          </svg>
        </button>
      </div>

      <div className="disclaimer">
        Talvrin provides source-linked facts and reproducible calculations.{' '}
        <strong>It does not give investment advice.</strong> Prototype — no backend connected.
      </div>
    </div>
  )
}
