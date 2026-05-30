import { ref, computed } from 'vue'
import type { StepData, ResultData, ErrorData } from '../types'

export function useAgent() {
  const steps = ref<StepData[]>([])
  const result = ref<ResultData | null>(null)
  const error = ref<ErrorData | null>(null)
  const running = ref(false)
  const screenshot = ref<string | null>(null)

  const activeProvider = computed(() =>
    steps.value.length > 0 ? 'running' : ''
  )

  function reset() {
    steps.value = []
    result.value = null
    error.value = null
    running.value = false
    screenshot.value = null
  }

  async function startTask(task: string, provider: string) {
    reset()
    running.value = true
    const resp = await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task, provider }),
    })
    if (!resp.ok) {
      const data = await resp.json()
      running.value = false
      error.value = { message: data.detail || 'Failed to start task', step: 0 }
      return
    }
  }

  async function cancelTask() {
    await fetch('/api/tasks/cancel', { method: 'POST' })
    running.value = false
  }

  function handleWsMessage(msg: { type: string; data: unknown }) {
    if (msg.type === 'step') {
      const stepData = msg.data as StepData
      // Update existing step or add new
      const idx = steps.value.findIndex((s) => s.step === stepData.step)
      if (idx >= 0) {
        steps.value[idx] = stepData
      } else {
        steps.value.push(stepData)
      }
      if (stepData.screenshot) {
        screenshot.value = stepData.screenshot
      }
    } else if (msg.type === 'result') {
      result.value = msg.data as ResultData
      running.value = false
      // Mark all steps as done
      steps.value.forEach((s) => (s.status = 'done'))
    } else if (msg.type === 'error') {
      error.value = msg.data as ErrorData
      running.value = false
    } else if (msg.type === 'cancelled') {
      running.value = false
    }
  }

  return {
    steps,
    result,
    error,
    running,
    screenshot,
    activeProvider,
    startTask,
    cancelTask,
    handleWsMessage,
    reset,
  }
}
