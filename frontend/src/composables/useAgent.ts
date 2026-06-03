import { ref } from 'vue'
import type { StepData, ResultData, ErrorData, TaskOptions, LiveUrlData, QueueStatusData, ThinkingStep, ToolCall, ThinkingData, ToolCallStartData, ToolCallResultData } from '../types'

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

  function handleWsMessage(msg: { type: string; data: unknown }) {
    if (msg.type === 'step') {
      const stepData = msg.data as StepData
      const idx = steps.value.findIndex((s) => s.step === stepData.step)
      if (idx >= 0) {
        steps.value[idx] = { ...steps.value[idx], ...stepData }
      } else {
        steps.value.push(stepData)
      }
      if (stepData.screenshot) {
        screenshot.value = stepData.screenshot
      }
    } else if (msg.type === 'result') {
      const resultData = msg.data as ResultData
      result.value = resultData
      commandHistory.value.push(resultData)
      running.value = false
      steps.value = steps.value.map((s) => ({ ...s, status: 'done' as const }))
    } else if (msg.type === 'error') {
      error.value = msg.data as ErrorData
      running.value = false
    } else if (msg.type === 'cancelled') {
      running.value = false
    } else if (msg.type === 'live_url') {
      liveUrl.value = (msg.data as LiveUrlData).url
    } else if (msg.type === 'queue_status') {
      queuePending.value = (msg.data as QueueStatusData).pending
    } else if (msg.type === 'thinking') {
      const data = msg.data as ThinkingData
      thinkingSteps.value.push({ step: data.step, description: data.description })
    } else if (msg.type === 'tool_call_start') {
      const data = msg.data as ToolCallStartData
      toolCalls.value.push({ name: data.tool, arguments: data.arguments, status: 'pending' })
    } else if (msg.type === 'tool_call_result') {
      const data = msg.data as ToolCallResultData
      const tc = toolCalls.value.find(t => t.name === data.tool)
      if (tc) {
        tc.status = 'completed'
        tc.result = data.result
      }
    }
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
    handleWsMessage,
    reset,
  }
}
