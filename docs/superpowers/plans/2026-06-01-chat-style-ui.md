# ChatGPT-Style UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current single-shot UI with a ChatGPT-style persistent chat interface: left panel shows the live browser preview, right panel shows chat history with message bubbles and a collapsible step log.

**Architecture:** Left-right split layout managed by HomeView.vue. ChatHistory composable manages a `messages[]` array (user + assistant). WebSocket `result` events map to assistant messages, user commands map to user messages. ScreenshotView lives in the left panel (shown only when `liveUrl` is set). StepLog is a collapsible panel below ChatHistory.

**Tech Stack:** Vue 3 Composition API, TypeScript, CSS.

---

## File Map

| File | Responsibility |
|------|-----------------|
| `frontend/src/components/ChatMessage.vue` | NEW: single message bubble (user right/blue or assistant left/gray) with timestamp |
| `frontend/src/components/ChatHistory.vue` | NEW: scrollable container for messages[], auto-scrolls to bottom |
| `frontend/src/views/HomeView.vue` | REFACTOR: left-right split layout, manages messages state, wires WS events |
| `frontend/src/composables/useAgent.ts` | UPDATE: emit user/assistant messages on result events |
| `frontend/src/composables/useWebSocket.ts` | UNCHANGED |
| `frontend/src/components/ScreenshotView.vue` | UNCHANGED |
| `frontend/src/components/StepLog.vue` | UNCHANGED |
| `frontend/src/components/TaskInput.vue` | UNCHANGED (just `@submit` emit) |
| `frontend/src/types/index.ts` | UPDATE: add `ChatMessage` type |

---

## Task 1: Add ChatMessage type to types/index.ts

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add ChatMessage interface**

Add before or after existing interfaces:
```typescript
export interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  timestamp: Date
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): add ChatMessage interface"
```

---

## Task 2: Create ChatMessage.vue

**Files:**
- Create: `frontend/src/components/ChatMessage.vue`

- [ ] **Step 1: Write the component**

```vue
<template>
  <div class="message" :class="message.role">
    <div class="bubble">
      <p class="text">{{ message.text }}</p>
      <span class="time">{{ formattedTime }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ChatMessage } from '../types'

const props = defineProps<{ message: ChatMessage }>()

const formattedTime = computed(() => {
  return props.message.timestamp.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })
})
</script>

<style scoped>
.message {
  display: flex;
  margin-bottom: 16px;
}
.message.user {
  justify-content: flex-end;
}
.message.assistant {
  justify-content: flex-start;
}
.bubble {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: 12px;
  position: relative;
}
.message.user .bubble {
  background: #6366F1;
  color: #fff;
  border-bottom-right-radius: 4px;
}
.message.assistant .bubble {
  background: #2D2D2F;
  color: #E4E4E7;
  border-bottom-left-radius: 4px;
}
.text {
  margin: 0;
  white-space: pre-wrap;
  font-size: 14px;
  line-height: 1.5;
}
.time {
  display: block;
  font-size: 11px;
  margin-top: 4px;
  opacity: 0.6;
}
.message.user .time { text-align: right; }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ChatMessage.vue
git commit -m "feat(chat): add ChatMessage component"
```

---

## Task 3: Create ChatHistory.vue

**Files:**
- Create: `frontend/src/components/ChatHistory.vue`

- [ ] **Step 1: Write the component**

```vue
<template>
  <div class="chat-history" ref="listEl">
    <div
      v-for="(msg, idx) in messages"
      :key="idx"
    >
      <ChatMessage :message="msg" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import ChatMessage from './ChatMessage.vue'
import type { ChatMessage } from '../types'

const props = defineProps<{ messages: ChatMessage[] }>()
const listEl = ref<HTMLElement | null>(null)

watch(() => props.messages.length, async () => {
  await nextTick()
  if (listEl.value) {
    listEl.value.scrollTop = listEl.value.scrollHeight
  }
})
</script>

<style scoped>
.chat-history {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ChatHistory.vue
git commit -m "feat(chat): add ChatHistory scrollable container component"
```

---

## Task 4: Refactor HomeView.vue to left-right split layout

**Files:**
- Modify: `frontend/src/views/HomeView.vue`

- [ ] **Step 1: Replace the entire template with new layout**

```html
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
```

- [ ] **Step 2: Update the script section**

Replace the `<script setup>` section:
```vue
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
  if (msg) {
    if (msg.type === 'interactive') {
      interactiveCommand.value = {
        type: msg.data.type,
        message: msg.data.message,
        screenshot: msg.data.screenshot || null,
      }
    } else {
      handleWsMessage(msg)
    }
  }
})

watch(lastMessage, (msg) => {
  if (!msg) return
  if (msg.type === 'result') {
    messages.value.push({
      role: 'assistant',
      text: (msg.data as any).output,
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
```

- [ ] **Step 3: Replace the style section**

```css
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
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/HomeView.vue
git commit -m "refactor(home): ChatGPT-style left-right split layout"
```

---

## Task 5: Update StepLog.vue to be collapsible

**Files:**
- Modify: `frontend/src/components/StepLog.vue`

- [ ] **Step 1: Read StepLog.vue in full**

```bash
cat frontend/src/components/StepLog.vue
```

- [ ] **Step 2: Add collapse toggle to template**

Add a header with click-to-collapse:
```html
<div class="step-log">
  <div class="step-log-header" @click="collapsed = !collapsed">
    <span>Steps</span>
    <span class="toggle">{{ collapsed ? '▶' : '▼' }}</span>
  </div>
  <div v-if="!collapsed" class="step-log-content">
    ... existing content ...
  </div>
</div>
```

- [ ] **Step 3: Add collapsed ref and toggle logic**

```typescript
const collapsed = ref(false)
```

- [ ] **Step 4: Add styles**

```css
.step-log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  padding: 8px 0;
  font-size: 14px;
  color: #a1a1aa;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.step-log-header:hover { color: #E4E4E7; }
.toggle { font-size: 10px; }
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StepLog.vue
git commit -m "feat(steplog): add collapsible panel"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Left panel Browser View (60%) — Task 4
- [x] Right panel ChatHistory + StepLog + Input — Task 4
- [x] ChatMessage bubbles with timestamp — Tasks 2, 3
- [x] User messages right/blue, AI left/gray — Task 2
- [x] StepLog collapsible — Task 5
- [x] Queue badge in right panel — Task 4
- [x] Browser View shown only when liveUrl set — ScreenshotView already has this, unchanged
- [x] Auto-scroll to bottom on new message — Task 3
- [x] Memory-only storage (messages in ref) — Task 4

**Placeholder scan:**
- [x] No "TBD", "TODO" in any step
- [x] All code blocks show actual code
- [x] All file paths are exact

**Type consistency:**
- [x] `ChatMessage.role` matches `'user' | 'assistant'`
- [x] `ChatMessage` used consistently across ChatMessage.vue, ChatHistory.vue, HomeView.vue
- [x] `messages.value.push()` in HomeView matches `ChatMessage` type