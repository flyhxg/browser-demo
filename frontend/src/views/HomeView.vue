<template>
  <div class="home">
    <div class="main-layout">
      <div class="left-panel">
        <ScreenshotView :screenshot="screenshot" :live-url="liveUrl" />
      </div>
      <div class="right-panel">
        <div class="queue-badge" v-if="queuePending > 0">
          {{ queuePending }} pending
        </div>
        <ChatHistory :messages="messages" />
        <StepLog :steps="steps" />
        <TaskInput
          :running="running"
          @submit="onSubmit"
          @cancel="onCancel"
          @reset="onReset"
        />
      </div>
    </div>
    <InteractivePanel
      :command-type="interactiveCommand.type"
      :command-message="interactiveCommand.message"
      :screenshot="interactiveCommand.screenshot"
      @input="handleInteractiveInput"
      @close="closeInteractivePanel"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import TaskInput from '../components/TaskInput.vue'
import StepLog from '../components/StepLog.vue'
import ScreenshotView from '../components/ScreenshotView.vue'
import ChatHistory from '../components/ChatHistory.vue'
import InteractivePanel from '../components/InteractivePanel.vue'
import { useAgent } from '../composables/useAgent'
import { useWebSocket } from '../composables/useWebSocket'
import type { AppConfig, ChatMessage } from '../types'

const { steps, running, screenshot, queuePending, liveUrl, cancelTask, resetTask, handleWsMessage } = useAgent()
const { lastMessage, sendCommand } = useWebSocket()

const messages = ref<ChatMessage[]>([])

const interactiveCommand = ref({
  type: '',
  message: '',
  screenshot: null as string | null,
})

watch(lastMessage, (msg) => {
  if (!msg) return
  if (msg.type === 'interactive') {
    const data = msg.data as unknown as { type: string; message: string; screenshot: string | null }
    interactiveCommand.value = {
      type: data.type,
      message: data.message,
      screenshot: data.screenshot || null,
    }
  } else {
    handleWsMessage(msg)
  }
})

watch(lastMessage, (msg) => {
  if (!msg) return
  if (msg.type === 'result') {
    const data = msg.data as { output: string; steps: number; duration_ms: number }
    messages.value.push({
      role: 'assistant',
      text: data.output,
      timestamp: new Date(),
    })
  }
})

async function loadConfig() {
  try {
    const resp = await fetch('/api/config')
    await resp.json() as AppConfig
  } catch { /* ignore */ }
}

function onSubmit(command: string) {
  running.value = true
  messages.value.push({
    role: 'user',
    text: command,
    timestamp: new Date(),
  })
  sendCommand(command)
}

async function onCancel() {
  await cancelTask()
}

async function onReset() {
  await resetTask()
  messages.value = []
}

async function handleInteractiveInput(data: { input: string; confirmed: boolean }) {
  try {
    await fetch('/api/interactive/input', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: 'current',
        input_data: data,
      }),
    })
  } catch { /* ignore */ }
}

function closeInteractivePanel() {
  interactiveCommand.value = { type: '', message: '', screenshot: null }
}

onMounted(loadConfig)
</script>

<style scoped>
.home {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.main-layout {
  flex: 1;
  display: grid;
  grid-template-columns: 60fr 40fr;
  gap: 0;
  overflow: hidden;
}
.left-panel {
  overflow: hidden;
  border-right: 1px solid #27272a;
}
.right-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.queue-badge {
  display: inline-block;
  background: #1c1c1e;
  color: #a1a1aa;
  border-radius: 20px;
  padding: 4px 12px;
  font-size: 12px;
  margin: 16px 16px 0;
}
@media (max-width: 768px) {
  .main-layout { grid-template-columns: 1fr; }
  .left-panel { height: 40vh; border-right: none; border-bottom: 1px solid #27272a; }
}
</style>