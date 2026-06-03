import { describe, it, expect } from 'vitest'
import { useWebSocket } from '../useWebSocket'

describe('useWebSocket', () => {
  it('exports useWebSocket', () => {
    expect(typeof useWebSocket).toBe('function')
  })
})
