<template>
  <div class="home">
    <TaskInput
      :running="running"
      @execute="onExecute"
      @cancel="onCancel"
    />
    <div class="execution-area">
      <div class="left">
        <StepLog :steps="steps" />
      </div>
      <div class="right">
        <ScreenshotView :screenshot="screenshot" />
      </div>
    </div>
    <ResultDisplay :result="result" :error="error" />
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import TaskInput from '../components/TaskInput.vue'
import StepLog from '../components/StepLog.vue'
import ScreenshotView from '../components/ScreenshotView.vue'
import ResultDisplay from '../components/ResultDisplay.vue'
import { useAgent } from '../composables/useAgent'
import { useWebSocket } from '../composables/useWebSocket'

const { steps, result, error, running, screenshot, startTask, cancelTask, handleWsMessage } = useAgent()
const { lastMessage } = useWebSocket()

watch(lastMessage, (msg) => {
  if (msg) handleWsMessage(msg)
})

async function onExecute(task: string, provider: string) {
  await startTask(task, provider)
}

async function onCancel() {
  await cancelTask()
}
</script>

<style scoped>
.home { max-width: 1000px; margin: 0 auto; padding: 24px; }
.execution-area {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}
@media (max-width: 768px) {
  .execution-area { grid-template-columns: 1fr; }
}
</style>
