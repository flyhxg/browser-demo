import { describe, it, expect } from 'vitest'
import {
  TOOL_DEFAULTS,
  RESULT_SOURCE_HINTS,
  defaultSourceFor,
  hintForResultSource,
} from '../toolSources'

describe('toolSources', () => {
  it('TOOL_DEFAULTS covers every tool in the catalog', () => {
    const tools = ['get_price', 'get_market_cap', 'get_funding_rate', 'scrape_binance_square', 'analyze_sentiment']
    for (const t of tools) {
      expect(TOOL_DEFAULTS[t]).toBeDefined()
      expect(TOOL_DEFAULTS[t].label).toBeTruthy()
    }
  })

  it('defaultSourceFor returns the static hint for a known tool', () => {
    expect(defaultSourceFor('get_price')).toEqual({
      label: 'Binance Futures',
      url: 'https://www.binance.com/en/futures',
    })
  })

  it('defaultSourceFor falls back to the tool name for unknown tools', () => {
    expect(defaultSourceFor('some_future_tool')).toEqual({
      label: 'some_future_tool',
      url: '',
    })
  })

  it('hintForResultSource resolves known identifiers', () => {
    expect(hintForResultSource('binance_futures')?.label).toBe('Binance Futures')
    expect(hintForResultSource('coingecko')?.label).toBe('CoinGecko')
    expect(hintForResultSource('okx')?.label).toBe('OKX')
    expect(hintForResultSource('binance_square')?.label).toBe('Binance Square')
  })

  it('hintForResultSource returns null for simulated / browser / unknown / non-string', () => {
    expect(hintForResultSource('simulated')).toBeNull()
    expect(hintForResultSource('browser')).toBeNull()
    expect(hintForResultSource('weird_future_id')).toBeNull()
    expect(hintForResultSource(undefined)).toBeNull()
    expect(hintForResultSource(42)).toBeNull()
    expect(hintForResultSource({ label: 'x' })).toBeNull()
  })
})