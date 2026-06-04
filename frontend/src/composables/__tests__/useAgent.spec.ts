import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { useAgent, installBusHandlers } from '../useAgent'
import { emit, clear } from '../useMessageBus'

describe('useAgent bus dispatch', () => {
  let offs: Array<() => void> = []

  function freshAgent() {
    const agent = useAgent()
    offs = installBusHandlers(agent)
    return agent
  }

  beforeEach(() => {
    clear()
  })

  afterEach(() => {
    offs.forEach((off) => off())
    offs = []
  })

  it('step event pushes a new step', async () => {
    const agent = freshAgent()
    emit({
      type: 'step',
      data: { step: 1, action: 'goto', target: 'binance.com', status: 'running', screenshot: null },
    })
    await nextTick()
    expect(agent.steps.value).toHaveLength(1)
    expect(agent.steps.value[0].step).toBe(1)
  })

  it('repeated step event with same step number updates in place', async () => {
    const agent = freshAgent()
    emit({ type: 'step', data: { step: 1, action: 'a', target: 't', status: 'running', screenshot: null } })
    emit({ type: 'step', data: { step: 1, action: 'a', target: 't', status: 'done', screenshot: null } })
    await nextTick()
    expect(agent.steps.value).toHaveLength(1)
    expect(agent.steps.value[0].status).toBe('done')
  })

  it('result event sets result and clears running', async () => {
    const agent = freshAgent()
    agent.running.value = true
    emit({ type: 'result', data: { output: 'done', steps: 3, duration_ms: 500 } })
    await nextTick()
    expect(agent.result.value).toEqual({ output: 'done', steps: 3, duration_ms: 500 })
    expect(agent.running.value).toBe(false)
  })

  it('error event sets error and clears running', async () => {
    const agent = freshAgent()
    agent.running.value = true
    emit({ type: 'error', data: { message: 'oops', step: 2 } })
    await nextTick()
    expect(agent.error.value).toEqual({ message: 'oops', step: 2 })
    expect(agent.running.value).toBe(false)
  })

  it('cancelled event clears running', async () => {
    const agent = freshAgent()
    agent.running.value = true
    emit({ type: 'cancelled', data: null })
    await nextTick()
    expect(agent.running.value).toBe(false)
  })

  it('live_url event sets liveUrl', async () => {
    const agent = freshAgent()
    emit({ type: 'live_url', data: { url: 'https://example.com/live' } })
    await nextTick()
    expect(agent.liveUrl.value).toBe('https://example.com/live')
  })

  it('queue_status event sets queuePending', async () => {
    const agent = freshAgent()
    emit({ type: 'queue_status', data: { pending: 3 } })
    await nextTick()
    expect(agent.queuePending.value).toBe(3)
  })

  it('thinking event appends to thinkingSteps', async () => {
    const agent = freshAgent()
    emit({ type: 'thinking', data: { step: 1, description: 'analyzing' } })
    emit({ type: 'thinking', data: { step: 2, description: 'planning' } })
    await nextTick()
    expect(agent.thinkingSteps.value).toEqual([
      { step: 1, description: 'analyzing' },
      { step: 2, description: 'planning' },
    ])
  })

  it('tool_call_start then tool_call_result transitions status pending → completed', async () => {
    const agent = freshAgent()
    emit({ type: 'tool_call_start', data: { tool: 'fetch', arguments: { url: 'x' } } })
    emit({ type: 'tool_call_result', data: { tool: 'fetch', result: { ok: true } } })
    await nextTick()
    expect(agent.toolCalls.value).toHaveLength(1)
    expect(agent.toolCalls.value[0].status).toBe('completed')
    expect(agent.toolCalls.value[0].result).toEqual({ ok: true })
  })

  it('tool_call_start attaches defaultSourceFor(tc.name) as tc.source', async () => {
    const agent = freshAgent()
    emit({ type: 'tool_call_start', data: { tool: 'get_price', arguments: { symbol: 'BTC' } } })
    await nextTick()
    expect(agent.toolCalls.value[0].source).toEqual({
      label: 'Binance Futures',
      url: 'https://www.binance.com/en/futures',
    })
  })

  it('tool_call_start honors server-supplied source when present', async () => {
    const agent = freshAgent()
    emit({
      type: 'tool_call_start',
      data: { tool: 'get_price', arguments: {}, source: { label: 'Custom', url: 'https://x' } },
    })
    await nextTick()
    expect(agent.toolCalls.value[0].source).toEqual({ label: 'Custom', url: 'https://x' })
  })

  it('tool_call_result with known result.source overwrites the chip', async () => {
    const agent = freshAgent()
    emit({ type: 'tool_call_start', data: { tool: 'get_price', arguments: {} } })
    emit({ type: 'tool_call_result', data: { tool: 'get_price', result: { source: 'coingecko' } } })
    await nextTick()
    expect(agent.toolCalls.value[0].source).toEqual({
      label: 'CoinGecko',
      url: 'https://www.coingecko.com',
    })
  })

  it('tool_call_result with unknown result.source keeps start-time chip', async () => {
    const agent = freshAgent()
    emit({ type: 'tool_call_start', data: { tool: 'scrape_binance_square', arguments: {} } })
    emit({
      type: 'tool_call_result',
      data: { tool: 'scrape_binance_square', result: { source: 'simulated' } },
    })
    await nextTick()
    expect(agent.toolCalls.value[0].source).toEqual({
      label: 'Binance Square',
      url: 'https://www.binance.com/en/square',
    })
  })

  it('tool_call_start with empty-label server source falls back to default', async () => {
    const agent = freshAgent()
    emit({
      type: 'tool_call_start',
      data: { tool: 'get_price', arguments: {}, source: { label: '', url: '' } },
    })
    await nextTick()
    expect(agent.toolCalls.value[0].source).toEqual({
      label: 'Binance Futures',
      url: 'https://www.binance.com/en/futures',
    })
  })
})
