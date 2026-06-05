import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import WorkflowView from '../WorkflowView.vue'

const stubTasks = [
  {
    id: 1,
    name: 'Signal Scanner',
    enabled: true,
    running: false,
    status: 'idle',
    interval_minutes: 5,
    last_run: null,
    next_run: null,
  },
  {
    id: 2,
    name: 'Polymarket Poller',
    enabled: false,
    running: false,
    status: 'paused',
    interval_minutes: 1,
    last_run: null,
    next_run: null,
  },
]

describe('WorkflowView multi-card list', () => {
  let fetchSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchSpy = vi.fn(async () => {
      return new Response(JSON.stringify({ tasks: stubTasks }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    })
    ;(globalThis as any).fetch = fetchSpy
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders one card per registered scheduler', async () => {
    const wrapper = mount(WorkflowView)
    await flushPromises()

    const cards = wrapper.findAll('.task-card')
    expect(cards).toHaveLength(2)
    wrapper.unmount()
  })

  it('shows both task names', async () => {
    const wrapper = mount(WorkflowView)
    await flushPromises()

    const html = wrapper.html()
    expect(html).toContain('Signal Scanner')
    expect(html).toContain('Polymarket Poller')
    wrapper.unmount()
  })

  it('help card mentions both schedulers', async () => {
    const wrapper = mount(WorkflowView)
    await flushPromises()

    const help = wrapper.find('.help-card')
    expect(help.exists()).toBe(true)
    const helpText = help.text()
    expect(helpText).toContain('Signal Scanner')
    expect(helpText).toContain('Polymarket Poller')
    wrapper.unmount()
  })

  it('fetches /api/workflow/tasks on mount', async () => {
    const wrapper = mount(WorkflowView)
    await flushPromises()

    expect(fetchSpy).toHaveBeenCalledWith('/api/workflow/tasks')
    wrapper.unmount()
  })
})
