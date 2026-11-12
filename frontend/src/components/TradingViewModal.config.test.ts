import { readFileSync } from 'fs'
import { dirname, join } from 'path'
import { fileURLToPath } from 'url'
import { describe, expect, it } from 'vitest'

// 2026-11-12 P0 remediation regression guard - source-text assertion for
// the same reason TradingViewWidget.config.test.ts gives: a full mount/
// remount assertion needs jsdom + React Testing Library, which this repo
// doesn't have set up yet. Guards against the key={symbol} prop being
// dropped, which would silently reintroduce "switching the selected
// instrument while the modal stays open can leave the PREVIOUS
// instrument's real chart on screen under the NEW instrument's header" -
// confirmed live via Playwright during this remediation (see final
// report).
const SOURCE = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), 'TradingViewModal.tsx'),
  'utf-8'
)

describe('TradingViewModal <TradingViewWidget> remount guarantee', () => {
  it('keys the embedded widget by symbol so a symbol change forces a full remount', () => {
    const start = SOURCE.indexOf('<TradingViewWidget')
    const end = SOURCE.indexOf('/>', start)
    const widgetBlock = SOURCE.slice(start, end)
    expect(widgetBlock).toMatch(/key=\{symbol\}/)
  })
})
