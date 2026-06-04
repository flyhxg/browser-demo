export interface SourceHint {
  label: string
  url: string
}

export const TOOL_DEFAULTS: Record<string, SourceHint> = {
  get_price:             { label: 'Binance Futures', url: 'https://www.binance.com/en/futures' },
  get_market_cap:        { label: 'CoinGecko',       url: 'https://www.coingecko.com' },
  get_funding_rate:      { label: 'OKX',             url: 'https://www.okx.com' },
  scrape_binance_square: { label: 'Binance Square',  url: 'https://www.binance.com/en/square' },
  analyze_sentiment:     { label: 'LLM',             url: '' },
}

export const RESULT_SOURCE_HINTS: Record<string, SourceHint> = {
  binance_futures: { label: 'Binance Futures', url: 'https://www.binance.com/en/futures' },
  coingecko:       { label: 'CoinGecko',       url: 'https://www.coingecko.com' },
  okx:             { label: 'OKX',             url: 'https://www.okx.com' },
  binance_square:  { label: 'Binance Square',  url: 'https://www.binance.com/en/square' },
}

export function defaultSourceFor(tool: string): SourceHint {
  return TOOL_DEFAULTS[tool] ?? { label: tool, url: '' }
}

export function hintForResultSource(id: unknown): SourceHint | null {
  if (typeof id !== 'string') return null
  return RESULT_SOURCE_HINTS[id] ?? null
}