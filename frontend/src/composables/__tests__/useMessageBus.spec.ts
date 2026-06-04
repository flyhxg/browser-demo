import { describe, it, expect, beforeEach, vi } from 'vitest'
import { on, off, emit, clear, _handlerCount } from '../useMessageBus'

describe('useMessageBus', () => {
  beforeEach(() => {
    clear()
  })

  it('emit invokes a registered handler with the data payload', () => {
    const handler = vi.fn()
    on('hot_tokens_update', handler)
    const tokens = [{ symbol: 'BTCUSDT', price: 50000 }] as unknown as Parameters<typeof handler>[0]
    emit({ type: 'hot_tokens_update', data: tokens })
    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler).toHaveBeenCalledWith(tokens)
  })

  it('emit with no registered handlers is a no-op (does not throw)', () => {
    expect(() => emit({ type: 'hot_tokens_update', data: [] })).not.toThrow()
  })

  it('off unsubscribes a handler so it no longer fires', () => {
    const handler = vi.fn()
    const unsubscribe = on('hot_tokens_update', handler)
    emit({ type: 'hot_tokens_update', data: [] })
    expect(handler).toHaveBeenCalledTimes(1)
    unsubscribe()
    emit({ type: 'hot_tokens_update', data: [] })
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('off() called directly with the handler also unsubscribes', () => {
    const handler = vi.fn()
    on('step', handler)
    off('step', handler)
    emit({ type: 'step', data: { step: 1, action: 'a', target: 't', status: 'done', screenshot: null } })
    expect(handler).not.toHaveBeenCalled()
  })

  it('multiple handlers on the same type all fire', () => {
    const h1 = vi.fn()
    const h2 = vi.fn()
    on('result', h1)
    on('result', h2)
    const payload = { output: 'ok', steps: 3, duration_ms: 1200 }
    emit({ type: 'result', data: payload })
    expect(h1).toHaveBeenCalledWith(payload)
    expect(h2).toHaveBeenCalledWith(payload)
  })

  it('handlers only fire for their subscribed type', () => {
    const stepHandler = vi.fn()
    const resultHandler = vi.fn()
    on('step', stepHandler)
    on('result', resultHandler)
    emit({ type: 'result', data: { output: 'ok', steps: 1, duration_ms: 100 } })
    expect(stepHandler).not.toHaveBeenCalled()
    expect(resultHandler).toHaveBeenCalledTimes(1)
  })

  it('clear() removes all handlers across all types', () => {
    const a = vi.fn()
    const b = vi.fn()
    on('step', a)
    on('result', b)
    clear()
    emit({ type: 'step', data: { step: 1, action: 'a', target: 't', status: 'done', screenshot: null } })
    emit({ type: 'result', data: { output: 'ok', steps: 1, duration_ms: 100 } })
    expect(a).not.toHaveBeenCalled()
    expect(b).not.toHaveBeenCalled()
    expect(_handlerCount()).toBe(0)
  })

  it('handler throwing does not prevent sibling handlers from firing', () => {
    const ok = vi.fn()
    on('result', () => {
      throw new Error('boom')
    })
    on('result', ok)
    expect(() =>
      emit({ type: 'result', data: { output: 'ok', steps: 1, duration_ms: 100 } })
    ).toThrow('boom')
    expect(ok).toHaveBeenCalledTimes(1)
  })

  it('100 subscribe/unsubscribe cycles leave zero handlers', () => {
    for (let i = 0; i < 100; i++) {
      const handler = () => {}
      const off1 = on('step', handler)
      const off2 = on('result', handler)
      off1()
      off2()
    }
    expect(_handlerCount()).toBe(0)
  })
})
