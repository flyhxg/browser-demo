import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAnalysisStore } from '../analysis'

describe('analysis store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('has default activeDimensions', () => {
    const store = useAnalysisStore()
    expect(store.activeDimensions.derivatives).toBe(true)
    expect(store.activeDimensions.sentiment).toBe(false)
  })
})
