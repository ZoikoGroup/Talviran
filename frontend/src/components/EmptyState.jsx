const SUGGESTIONS = [
  {
    title: 'Explain the 4¼% Treasury Gilt 2036',
    sub: 'Terms, coupon dates and source-linked facts',
  },
  {
    title: 'What is accrued interest on a gilt?',
    sub: 'Market convention, explained plainly',
  },
  {
    title: 'Compare a 10-year gilt vs a 10-year Treasury',
    sub: 'Side-by-side, metrics you choose',
  },
  {
    title: 'Alert me if a yield crosses 4.5%',
    sub: 'Set an objective monitoring rule',
  },
]

export default function EmptyState({ onPick }) {
  return (
    <div className="empty">
      <div className="empty-mark">T</div>
      <h1>What would you like to research?</h1>
      <p>
        Ask about an instrument, a market convention or a calculation. Every
        material fact comes with its source — and Talvrin never gives investment
        advice.
      </p>

      <div className="suggestions">
        {SUGGESTIONS.map((s) => (
          <button className="suggestion" key={s.title} onClick={() => onPick(s.title)}>
            <div className="suggestion-title">{s.title}</div>
            <div className="suggestion-sub">{s.sub}</div>
          </button>
        ))}
      </div>
    </div>
  )
}
