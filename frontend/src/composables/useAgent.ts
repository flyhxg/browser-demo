import { ref } from 'vue'
import type { Ref } from 'vue'
import type { StepData, ResultData, ErrorData, TaskOptions, ThinkingStep, ToolCall } from '../types'
import { on as busOn } from './useMessageBus'

export function useAgent() {
  const steps = ref<StepData[]>([])
  const result = ref<ResultData | null>(null)
  const error = ref<ErrorData | null>(null)
  const running = ref(false)
  const screenshot = ref<string | null>(null)
  const queuePending = ref(0)
  const liveUrl = ref<string | null>(null)
  const commandHistory = ref<ResultData[]>([])
  const thinkingSteps = ref<ThinkingStep[]>([])
  const toolCalls = ref<ToolCall[]>([])

  function reset() {
    steps.value = []
    result.value = null
    error.value = null
    running.value = false
    screenshot.value = null
    queuePending.value = 0
    liveUrl.value = null
    commandHistory.value = []
    thinkingSteps.value = []
    toolCalls.value = []
  }

  async function startTask(options: TaskOptions) {
    reset()
    running.value = true
    try {
      const resp = await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(options),
      })
      if (!resp.ok) {
        const data = await resp.json()
        running.value = false
        error.value = { message: data.detail || 'Failed to start task', step: 0 }
        return
      }
    } catch {
      running.value = false
      error.value = { message: 'Network error: cannot reach server', step: 0 }
    }
  }

  async function cancelTask() {
    try {
      await fetch('/api/tasks/cancel', { method: 'POST' })
    } catch {
      // best effort
    }
    running.value = false
  }

  async function resetTask() {
    try {
      await fetch('/api/tasks/reset', { method: 'POST' })
    } catch {
      // best effort
    }
    running.value = false
    error.value = null
  }

  return {
    steps,
    result,
    error,
    running,
    screenshot,
    queuePending,
    liveUrl,
    commandHistory,
    thinkingSteps,
    toolCalls,
    startTask,
    cancelTask,
    resetTask,
    reset,
  }
}

export interface AgentBusTarget {
  steps: Ref<StepData[]>
  result: Ref<ResultData | null>
  error: Ref<ErrorData | null>
  running: Ref<boolean>
  screenshot: Ref<string | null>
  queuePending: Ref<number>
  liveUrl: Ref<string | null>
  commandHistory: Ref<ResultData[]>
  thinkingSteps: Ref<ThinkingStep[]>
  toolCalls: Ref<ToolCall[]>
}

/**
 * Subscribe agent state to the 9 chat-related WebSocket event types.
 * Returns an array of unsubscribe functions; caller is responsible
 * for invoking them on unmount.
 *
 * Production callers: HomeView.vue (calls in onMounted, off in onUnmounted).
 * Test callers: useAgent.spec.ts (calls once per test, then clear() in
 * beforeEach ensures isolation).
 */
export function installBusHandlers(agent: AgentBusTarget): Array<() => void> {
  return [
    busOn('step', (data) => {
      const idx = agent.steps.value.findIndex((s) => s.step === data.step)
      if (idx >= 0) {
        agent.steps.value[idx] = { ...agent.steps.value[idx], ...data }
      } else {
        agent.steps.value.push(data)
      }
      if (data.screenshot) agent.screenshot.value = data.screenshot
    }),
    busOn('result', (data) => {
      agent.result.value = data
      agent.commandHistory.value.push(data)
      agent.running.value = false
      agent.steps.value = agent.steps.value.map((s) => ({ ...s, status: 'done' as const }))
    }),
    busOn('error', (data) => {
      agent.error.value = data
      agent.running.value = false
    }),
    busOn('cancelled', () => {
      agent.running.value = false
    }),
    busOn('live_url', (data) => {
      agent.liveUrl.value = data.url
    }),
    busOn('queue_status', (data) => {
      agent.queuePending.value = data.pending
    }),
    busOn('thinking', (data) => {
      agent.thinkingSteps.value.push({ step: data.step, description: data.description })
    }),
    busOn('tool_call_start', (data) => {
      agent.toolCalls.value.push({ name: data.tool, arguments: data.arguments, status: 'pending' })
    }),
    busOn('tool_call_result', (data) => {
      const tc = agent.toolCalls.value.find((t) => t.name === data.tool)
      if (tc) {
        tc.status = 'completed'
        tc.result = data.result
      }
    }),
  ]
}
