import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import WorkflowView from '../WorkflowView.vue'
import type { TaskStatus } from '../WorkflowView.vue'

const stubTasks: TaskStatus[] = [
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

function makeFetchSpy(overrides: Record<string, () => Response> = {}) {
  return vi.fn(async (url: string, _init?: RequestInit) => {
    const handler = overrides[url]
    if (handler) return handler()
    return new Response(JSON.stringify({ tasks: stubTasks }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  })
}

describe('WorkflowView multi-card list', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('renders one card per registered scheduler', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(makeFetchSpy())
    const wrapper = mount(WorkflowView)
    await flushPromises()

    const cards = wrapper.findAll('.task-card')
    expect(cards).toHaveLength(2)
    wrapper.unmount()
  })

  it('shows both task names', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(makeFetchSpy())
    const wrapper = mount(WorkflowView)
    await flushPromises()

    const html = wrapper.html()
    expect(html).toContain('Signal Scanner')
    expect(html).toContain('Polymarket Poller')
    wrapper.unmount()
  })

  it('help card mentions both schedulers', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(makeFetchSpy())
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
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(makeFetchSpy())
    const wrapper = mount(WorkflowView)
    await flushPromises()

    expect(fetchSpy).toHaveBeenCalledWith('/api/workflow/tasks')
    wrapper.unmount()
  })

  it('toggle action disables only the toggled card', async () => {
    // Make the toggle endpoint slow so we can observe the in-flight state.
    let resolveToggle: ((v: Response) => void) | null = null
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
      makeFetchSpy({
        '/api/workflow/tasks/1/toggle': () => new Promise<Response>((r) => { resolveToggle = r }),
      }),
    )
    const wrapper = mount(WorkflowView)
    await flushPromises()

    // Initially neither card is in "Working..." state.
    expect(wrapper.text()).not.toContain('Working…')

    // Click the toggle on the first card (Signal Scanner).
    const firstCard = wrapper.findAll('.task-card')[0]
    await firstCard.find('.btn-primary').trigger('click')
    await flushPromises()

    // The first card shows "Working…"; the second does not.
    const firstText = firstCard.text()
    const secondCard = wrapper.findAll('.task-card')[1]
    const secondText = secondCard.text()
    expect(firstText).toContain('Working…')
    expect(secondText).not.toContain('Working…')

    // Complete the request and unmount cleanly.
    resolveToggle!(new Response(JSON.stringify({ status: 'toggled' }), { status: 200 }))
    await flushPromises()
    wrapper.unmount()
  })

  it('per-card fetch error renders only in the affected card', async () => {
    // /api/workflow/tasks/1/toggle fails; /api/workflow/tasks/2/toggle succeeds.
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
      makeFetchSpy({
        '/api/workflow/tasks/1/toggle': () =>
          new Response(JSON.stringify({ detail: 'simulated 500' }), { status: 500 }),
        '/api/workflow/tasks/2/toggle': () =>
          new Response(JSON.stringify({ status: 'toggled' }), { status: 200 }),
      }),
    )
    const wrapper = mount(WorkflowView)
    await flushPromises()

    // Trigger both toggles concurrently.
    const cards = wrapper.findAll('.task-card')
    await Promise.all([
      cards[0].find('.btn-primary').trigger('click'),
      cards[1].find('.btn-primary').trigger('click'),
    ])
    await flushPromises()

    const firstErrors = cards[0].findAll('.action-error')
    const secondErrors = cards[1].findAll('.action-error')
    expect(firstErrors).toHaveLength(1)
    expect(firstErrors[0].text()).toContain('simulated 500')
    expect(secondErrors).toHaveLength(0)

    wrapper.unmount()
  })
})
