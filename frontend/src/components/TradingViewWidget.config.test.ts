import { readFileSync } from 'fs'
import { dirname, join } from 'path'
import { fileURLToPath } from 'url'
import { describe, expect, it } from 'vitest'

// 2026-11-12 P0 remediation regression guard. The widget's embed config is
// built inline inside a useEffect via document.createElement('script') -
// rendering it through jsdom/React Testing Library to assert on the
// injected script's JSON would need new test-rendering infrastructure this
// repo doesn't have yet (see final report's remaining-limitations section).
// A direct source-text assertion is a smaller, still-meaningful guard
// against the exact regression this fix closed: `allow_symbol_change:
// true` let a user change the chart's displayed instrument from inside
// TradingView's own iframe UI, independent of this app's selected-instrument
// state and its header - confirmed as the root cause of a P0 chart-identity
// mismatch (NIFTY 50 in the header, AAPL's real data in the chart).
const SOURCE = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), 'TradingViewWidget.tsx'),
  'utf-8'
)

describe('TradingViewWidget embed config', () => {
  it('never re-enables allow_symbol_change', () => {
    expect(SOURCE).toContain('allow_symbol_change: false')
    expect(SOURCE).not.toContain('allow_symbol_change: true')
  })

  it('still forwards the caller-supplied symbol into the embed config', () => {
    expect(SOURCE).toMatch(/symbol:\s*tvSymbol/)
  })
})
