import { Book, Calc, Scale, Bell } from './icons.jsx'

const SUGGESTIONS = [
  {
    icon: Book,
    tint: '#6366f1',
    title: 'Explain the 4¼% Treasury Gilt 2036',
    sub: 'Canonical terms with source-linked facts',
  },
  {
    icon: Calc,
    tint: '#0ea5e9',
    title: 'What is accrued interest on a gilt?',
    sub: 'Market convention, explained plainly',
  },
  {
    icon: Scale,
    tint: '#a855f7',
    title: 'Compare a 10-year gilt vs a Treasury',
    sub: 'Side by side, on metrics you choose',
  },
  {
    icon: Bell,
    tint: '#10b981',
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
        Ask about an instrument, a market convention or a calculation. Every material
        fact carries its source — and Talvrin never gives investment advice.
      </p>

      <div className="suggestions">
        {SUGGESTIONS.map(({ icon: Ico, tint, title, sub }) => (
          <button className="suggestion" key={title} onClick={() => onPick(title)}>
            <span
              className="sug-icon"
              style={{ background: tint + '1f', color: tint }}
            >
              <Ico size={15} />
            </span>
            <span>
              <span className="sug-title">{title}</span>
              <span className="sug-sub">{sub}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
