import { describe, expect, it } from 'vitest'
import {
  GLOBAL_MARKET_ASSETS,
  isVerifiedLiveAsset,
  UNVERIFIED_SOURCE_LABEL,
  UNVERIFIED_FRESHNESS_LABEL,
  UNVERIFIED_STATUS_LABEL,
} from './globalAssets'

// 2026-11-12 P0 remediation regression tests - guards against this catalog
// silently going back to labeling unconnected instruments as CANONICAL /
// RECONCILED (the original NIFTY 50 defect: a frozen literal price shown
// with real-sounding provenance and no backend connector at all).

describe('isVerifiedLiveAsset', () => {
  it('is false for NIFTY 50 - the exact instrument from the original P0 report', () => {
    expect(isVerifiedLiveAsset('NIFTY 50')).toBe(false)
  })

  it('is true for the genuinely connected pilot equities and sovereign tenors', () => {
    expect(isVerifiedLiveAsset('AAPL')).toBe(true)
    expect(isVerifiedLiveAsset('MSFT')).toBe(true)
    expect(isVerifiedLiveAsset('BP.L')).toBe(true)
    expect(isVerifiedLiveAsset('AZN.L')).toBe(true)
    expect(isVerifiedLiveAsset('UK 10Y Gilt')).toBe(true)
    expect(isVerifiedLiveAsset('US 10Y Treasury')).toBe(true)
    expect(isVerifiedLiveAsset('GBP/USD')).toBe(true)
  })

  it('is false for every other asset class this platform has no connector for', () => {
    for (const symbol of ['S&P 500', 'Gold (XAU/USD)', 'BTC/USD', 'FTSE 100', 'BSE SENSEX', 'NVDA']) {
      expect(isVerifiedLiveAsset(symbol)).toBe(false)
    }
  })
})

describe('GLOBAL_MARKET_ASSETS honesty labeling', () => {
  it('never claims CANONICAL/RECONCILED for an unverified instrument', () => {
    const offenders = GLOBAL_MARKET_ASSETS.filter(
      (a) => !isVerifiedLiveAsset(a.symbol) && a.bitemporalStatus !== UNVERIFIED_STATUS_LABEL
    )
    expect(offenders.map((a) => a.symbol)).toEqual([])
  })

  it('NIFTY 50 specifically carries the honest unverified labels, not a fabricated source', () => {
    const nifty = GLOBAL_MARKET_ASSETS.find((a) => a.symbol === 'NIFTY 50')
    expect(nifty).toBeDefined()
    expect(nifty?.source).toBe(UNVERIFIED_SOURCE_LABEL)
    expect(nifty?.freshness).toBe(UNVERIFIED_FRESHNESS_LABEL)
    expect(nifty?.bitemporalStatus).toBe(UNVERIFIED_STATUS_LABEL)
    // The price itself stays (still useful for search/discovery) - only the
    // provenance claim is corrected.
    expect(nifty?.price).toBe('25,014.60')
  })

  it('AAPL keeps its real source attribution, not the unverified placeholder', () => {
    const aapl = GLOBAL_MARKET_ASSETS.find((a) => a.symbol === 'AAPL')
    expect(aapl).toBeDefined()
    expect(aapl?.source).not.toBe(UNVERIFIED_SOURCE_LABEL)
    expect(aapl?.bitemporalStatus).not.toBe(UNVERIFIED_STATUS_LABEL)
  })

  it('every catalog entry still has its underlying price/sparkline data untouched', () => {
    // The remediation must only ever correct the three provenance fields -
    // never delete or invent price/sparkline data.
    for (const asset of GLOBAL_MARKET_ASSETS) {
      expect(typeof asset.price).toBe('string')
      expect(asset.price.length).toBeGreaterThan(0)
      expect(Array.isArray(asset.sparkline)).toBe(true)
    }
  })
})
