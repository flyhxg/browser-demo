import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { _handlerCount, clear } from '../../composables/useMessageBus'
import HomeView from '../HomeView.vue'

// Stub the global WebSocket so useWebSocket() does not throw on mount.
class FakeWebSocket {
  url: string
  readyState = 0
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(url: string) {
    this.url = url
    setTimeout(() => {
      this.readyState = 1
      this.onopen?.()
    }, 0)
  }
  send() {}
  close() {
    this.readyState = 3
    this.onclose?.()
  }
}
;(globalThis as any).WebSocket = FakeWebSocket

describe('HomeView bus mount/unmount', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    clear()
  })

  afterEach(() => {
    clear()
  })

  it('handler count returns to 0 after 100 mount/unmount cycles', async () => {
    for (let i = 0; i < 100; i++) {
      const wrapper = mount(HomeView)
      await wrapper.vm.$nextTick()
      wrapper.unmount()
    }
    // Allow Vue to flush pending unmount hooks
    await new Promise((r) => setTimeout(r, 0))
    expect(_handlerCount()).toBe(0)
  })
})
