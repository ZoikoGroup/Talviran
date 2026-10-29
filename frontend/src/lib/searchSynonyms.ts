// Comprehensive Financial Synonyms and Symbol Aliases dictionary
// Maps common investor terms, ticker shorthands, abbreviations, and colloquial names to canonical asset keywords
export const ASSET_SYNONYM_MAP: Record<string, string[]> = {
  // Cryptocurrencies
  btc: ['bitcoin', 'btc/usd', 'ibit'],
  bitcoin: ['btc', 'btc/usd', 'ibit'],
  eth: ['ethereum', 'eth/usd', 'etha'],
  ethereum: ['eth', 'eth/usd', 'etha'],
  sol: ['solana', 'sol/usd'],
  solana: ['sol', 'sol/usd'],
  xrp: ['ripple', 'xrp/usd'],
  ripple: ['xrp', 'xrp/usd'],
  bnb: ['binance coin', 'bnb/usd'],
  doge: ['dogecoin'],
  dogecoin: ['doge'],
  ada: ['cardano'],
  cardano: ['ada'],
  avax: ['avalanche'],
  crypto: ['btc/usd', 'eth/usd', 'sol/usd', 'xrp/usd'],

  // Indian Equities & Bluechips
  tata: ['tatasteel', 'tcs', 'tatamotors', 'tcs:nse'],
  tatasteel: ['tata steel', 'tatasteel'],
  'tata steel': ['tatasteel'],
  tcs: ['tata consultancy', 'tcs:nse'],
  'tata consultancy': ['tcs', 'tcs:nse'],
  tatamotors: ['tata motors'],
  'tata motors': ['tatamotors'],
  reliance: ['reliance industries', 'jio', 'reliance'],
  ril: ['reliance industries', 'reliance'],
  jio: ['reliance', 'jio-ipo'],
  infy: ['infosys', 'infy:nse'],
  infosys: ['infy', 'infy:nse'],
  hdfc: ['hdfc bank', 'hdfcbank'],
  hdfcbank: ['hdfc bank', 'hdfc'],
  icici: ['icici bank', 'icicibank'],
  sbi: ['state bank of india', 'sbin'],
  sbin: ['state bank of india', 'sbi'],
  itc: ['itc limited'],
  bharti: ['bharti airtel', 'airtel'],
  airtel: ['bharti airtel'],
  lnt: ['larsen & toubro', 'lt'],
  lt: ['larsen & toubro'],
  bse: ['bombay stock exchange', 'sensex'],
  nse: ['national stock exchange', 'nifty'],
  nifty: ['nifty 50', 'nse'],
  sensex: ['bse sensex', 'bse'],

  // US Tech & Megacaps
  aapl: ['apple', 'apple inc'],
  apple: ['aapl'],
  msft: ['microsoft', 'microsoft corp'],
  microsoft: ['msft'],
  goog: ['alphabet', 'google', 'googl'],
  googl: ['alphabet', 'google', 'goog'],
  google: ['alphabet', 'googl', 'goog'],
  alphabet: ['google', 'googl'],
  amzn: ['amazon', 'amazon.com'],
  amazon: ['amzn'],
  nvda: ['nvidia', 'nvidia corp'],
  nvidia: ['nvda'],
  tsla: ['tesla', 'tesla inc'],
  tesla: ['tsla'],
  meta: ['facebook', 'meta platforms'],
  facebook: ['meta', 'meta platforms'],
  avgo: ['broadcom'],
  broadcom: ['avgo'],
  asml: ['asml holding'],
  amd: ['advanced micro devices'],
  arm: ['arm holdings'],
  tsmc: ['taiwan semiconductor', 'tsm'],
  tsm: ['taiwan semiconductor'],

  // Sovereign Debt, Gilts, Treasuries & Yields
  gilt: ['uk 10y gilt', 'gilt', 'dmo', 'nominal spot curve'],
  gilts: ['uk 10y gilt', 'gilt', 'dmo'],
  treasury: ['us 10y', 'us 2y', 'us 30y', 'treasury yield curve', 't-bill', 't-note'],
  treasuries: ['us 10y', 'us 2y', 'us 30y', 'treasury yield curve'],
  bund: ['germany 10y', 'bundesbank', 'german bund'],
  bunds: ['germany 10y', 'bundesbank'],
  bobl: ['germany 5y bobl'],
  shatz: ['germany 2y schatz'],
  jgb: ['japan 10y jgb', 'japan 30y'],
  oat: ['france 10y oat'],
  btp: ['italy 10y btp'],
  bono: ['spain 10y bono'],

  // Commodities & Precious Metals
  gold: ['xau/usd', 'gold', 'lbma gold'],
  xau: ['gold', 'xau/usd'],
  silver: ['xag/usd', 'silver'],
  xag: ['silver', 'xag/usd'],
  crude: ['wti crude', 'brent crude', 'oil'],
  oil: ['wti crude', 'brent crude', 'crude'],
  wti: ['wti crude oil'],
  brent: ['brent crude oil'],
  gas: ['natural gas'],
  copper: ['copper'],

  // FX & Currencies
  cable: ['gbp/usd', 'british pound'],
  gbp: ['gbp/usd', 'pound', 'sterling'],
  sterling: ['gbp/usd', 'british pound'],
  eur: ['eur/usd', 'euro'],
  euro: ['eur/usd'],
  jpy: ['usd/jpy', 'yen', 'japanese yen'],
  yen: ['usd/jpy'],
  inr: ['usd/inr', 'rupee', 'indian rupee'],
  rupee: ['usd/inr', 'indian rupee'],
  chf: ['usd/chf', 'swiss franc'],
  aud: ['aud/usd', 'australian dollar'],
  cad: ['usd/cad', 'canadian dollar'],
  cny: ['usd/cny', 'yuan', 'chinese yuan'],
  dxy: ['us dollar index', 'dxy'],
  dollar: ['usd', 'dxy', 'us dollar'],
}

/**
 * Normalizes query string: strips special punctuation, handles compact forms.
 * e.g., 'tata-steel' -> 'tatasteel', 'tata steel' -> 'tatasteel'
 */
export function normalizeSearchToken(str: string): string {
  return str.toLowerCase().replace(/[^a-z0-9]/g, '')
}

/**
 * Checks if a candidate asset matches a search query using multi-tier fuzzy & synonym resolution:
 * 1. Direct case-insensitive substring on symbol, name, or source.
 * 2. Normalized alphanumeric match (e.g. "tatasteel" matches "Tata Steel Limited" and "TATASTEEL").
 * 3. Short-form & synonym expansion (e.g. "btc" matches "Bitcoin / US Dollar", "reliance" matches "RIL").
 * 4. Word-boundary token matches (all tokens in multi-word query match some part).
 */
export function matchAssetSearch(
  asset: { symbol: string; name: string; source?: string; assetClass?: string },
  rawQuery: string
): boolean {
  const query = rawQuery.trim().toLowerCase()
  if (!query) return true

  const symbolLower = asset.symbol.toLowerCase()
  const nameLower = asset.name.toLowerCase()
  const sourceLower = (asset.source || '').toLowerCase()
  const assetClassLower = (asset.assetClass || '').toLowerCase()

  // 1. Direct standard substring
  if (
    symbolLower.includes(query) ||
    nameLower.includes(query) ||
    sourceLower.includes(query) ||
    assetClassLower.includes(query)
  ) {
    return true
  }

  // 2. Normalized compact match (strips spaces, dashes, slashes)
  const normQ = normalizeSearchToken(query)
  if (normQ.length >= 2) {
    const normSymbol = normalizeSearchToken(asset.symbol)
    const normName = normalizeSearchToken(asset.name)
    if (normSymbol.includes(normQ) || normName.includes(normQ)) {
      return true
    }
  }

  // 3. Synonym and short-form alias match
  const synonyms = ASSET_SYNONYM_MAP[query] || ASSET_SYNONYM_MAP[normQ]
  if (synonyms) {
    for (const syn of synonyms) {
      const synLower = syn.toLowerCase()
      const normSyn = normalizeSearchToken(syn)
      if (
        symbolLower.includes(synLower) ||
        nameLower.includes(synLower) ||
        normalizeSearchToken(asset.symbol).includes(normSyn) ||
        normalizeSearchToken(asset.name).includes(normSyn)
      ) {
        return true
      }
    }
  }

  // 4. Reverse / word-boundary token matches
  const words = query.split(/\s+/).filter(Boolean)
  if (words.length > 1) {
    const allWordsMatch = words.every((w) => {
      const nw = normalizeSearchToken(w)
      if (
        symbolLower.includes(w) ||
        nameLower.includes(w) ||
        normalizeSearchToken(asset.symbol).includes(nw) ||
        normalizeSearchToken(asset.name).includes(nw)
      ) {
        return true
      }
      const wordSyns = ASSET_SYNONYM_MAP[w] || ASSET_SYNONYM_MAP[nw]
      if (wordSyns) {
        return wordSyns.some((ws) => symbolLower.includes(ws) || nameLower.includes(ws))
      }
      return false
    })
    if (allWordsMatch) return true
  }

  return false
}
