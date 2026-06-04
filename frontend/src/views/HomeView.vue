<template>
  <div class="chat-app">
    <!-- Top Header -->
    <header class="chat-header">
      <div class="header-left">
        <h1>AI Trading Agent</h1>
        <span class="model-badge">MiniMax-M2.7</span>
      </div>
      <div class="header-actions">
        <button class="icon-btn" @click="onClearChat" title="Clear Chat">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          </svg>
        </button>
        <button class="icon-btn" @click="onReset" title="New Session">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
      </div>
    </header>

    <!-- Messages Area -->
    <div class="messages-wrapper" ref="messagesContainer">
      <!-- Empty state -->
      <div v-if="messages.length === 0 && !running" class="empty-chat">
        <div class="empty-icon">🤖</div>
        <h2>How can I help you today?</h2>
        <p class="empty-desc">Analyze markets, execute trades, or research crypto signals.</p>
        <div class="quick-prompts">
          <button v-for="prompt in quickPrompts" :key="prompt" class="quick-prompt" @click="sendQuickPrompt(prompt)">
            {{ prompt }}
          </button>
        </div>
      </div>

      <!-- Messages -->
      <template v-else>
        <MessageCard v-for="(msg, idx) in messages" :key="idx" :msg="msg" />

        <!-- Loading / Streaming indicator -->
        <div v-if="running" class="message-row assistant streaming">
          <div class="message-avatar">
            <div class="avatar ai">AI</div>
          </div>
          <div class="message-content">
            <div class="message-bubble assistant loading-bubble">
              <div class="loading-indicator">
                <span class="loading-text">Thinking</span>
                <div class="loading-dots">
                  <span></span><span></span><span></span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Bottom Input -->
    <div class="chat-footer">
      <div class="input-wrapper">
        <textarea
          v-model="inputText"
          placeholder="Describe the browser task you want the AI to perform..."
          rows="1"
          :disabled="running"
          @keydown="handleKeydown"
          @input="autoResize"
          ref="inputRef"
        ></textarea>
        <button
          class="send-btn"
          :class="{ active: inputText.trim() && !running }"
          @click="onSubmit"
          :disabled="!inputText.trim() || running"
        >
          <svg v-if="!running" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
          </svg>
          <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <rect x="6" y="6" width="12" height="12" rx="2" />
          </svg>
        </button>
      </div>
      <div class="input-meta">
        <span class="hint">Press Enter to send, Shift+Enter for new line</span>
        <button v-if="running" class="cancel-btn" @click="onCancel">Cancel</button>
      </div>
    </div>

    <!-- Interactive Panel -->
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
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import InteractivePanel from '../components/InteractivePanel.vue'
import { useAgent, installBusHandlers } from '../composables/useAgent'
import { useWebSocket } from '../composables/useWebSocket'
import { on as busOn } from '../composables/useMessageBus'
import type { ExtendedChatMessage, ThinkingStep, ToolCall } from '../types'
import MessageCard from '../components/MessageCard.vue'

const agent = useAgent()
const { steps, running, screenshot, queuePending, liveUrl, cancelTask, resetTask } = agent
const { sendCommand, disconnect, clearSession, newSession, clearSessionId, connect } = useWebSocket()

const messages = ref<ExtendedChatMessage[]>([])
const currentThinkingSteps = ref<ThinkingStep[]>([])
const currentToolCalls = ref<ToolCall[]>([])
const inputText = ref('')
const inputRef = ref<HTMLTextAreaElement | null>(null)
const messagesContainer = ref<HTMLElement | null>(null)

const quickPrompts = [
  'Analyze BTC market sentiment',
  'Scan Binance Square for signals',
  'Show my open positions',
  'Execute bullish SOL signal',
]

const interactiveCommand = ref({
  type: '',
  message: '',
  screenshot: null as string | null,
})

let agentBusOffs: Array<() => void> = []
const busOffs: Array<() => void> = []

busOffs.push(
  busOn('interactive', (data) => {
    interactiveCommand.value = {
      type: data.type,
      message: data.message,
      screenshot: data.screenshot || null,
    }
  }),
  busOn('thinking', (data) => {
    currentThinkingSteps.value.push(data)
  }),
  busOn('tool_call_start', (data) => {
    currentToolCalls.value.push({
      name: data.tool,
      arguments: data.arguments,
      status: 'pending',
    })
  }),
  busOn('tool_call_result', (data) => {
    const tc = currentToolCalls.value.find((t) => t.name === data.tool && t.status === 'pending')
    if (tc) {
      tc.status = 'completed'
      tc.result = data.result
    }
  })
)

busOffs.push(
  busOn('result', (data) => {
    messages.value.push({
      role: 'assistant',
      text: data.output,
      timestamp: new Date(),
      thinkingSteps: [...currentThinkingSteps.value],
      toolCalls: [...currentToolCalls.value],
    })
    scrollToBottom()
  }),
  busOn('history', (data) => {
    messages.value = data.messages.map((m) => ({
      role: m.role === 'user' ? 'user' : 'assistant',
      text: m.content,
      timestamp: new Date(m.created_at || Date.now()),
    }))
    scrollToBottom()
  })
)

watch(steps, () => {
  scrollToBottom()
})

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function autoResize(e: Event) {
  const el = e.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

function sendQuickPrompt(prompt: string) {
  inputText.value = prompt
  onSubmit()
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    onSubmit()
  }
}

function onSubmit() {
  const text = inputText.value.trim()
  if (!text || running.value) return

  messages.value.push({
    role: 'user',
    text,
    timestamp: new Date(),
  })

  sendCommand(text)
  inputText.value = ''
  currentThinkingSteps.value = []
  currentToolCalls.value = []
  running.value = true
  nextTick(() => {
    const el = inputRef.value
    if (el) {
      el.style.height = 'auto'
    }
  })
  scrollToBottom()
}

async function onCancel() {
  await cancelTask()
}

async function onClearChat() {
  // Clear messages for current session but keep the session itself
  clearSession()
  // Clear local UI messages
  messages.value = []
}

async function onReset() {
  await resetTask()
  messages.value = []
  // Create a new session
  newSession()
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

onMounted(async () => {
  agentBusOffs = installBusHandlers(agent)
  try {
    await fetch('/api/config')
  } catch { /* ignore */ }
})

onUnmounted(() => {
  busOffs.forEach((off) => off())
  agentBusOffs.forEach((off) => off())
})
</script>

<style scoped>
.chat-app {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  min-width: 0;
  width: 100%;
  overflow: hidden;
  background: #0a0a0f;
}

/* Header */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid #1e1e24;
  background: #111114;
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.header-left h1 {
  font-size: 15px;
  font-weight: 600;
  color: #fff;
  margin: 0;
}
.model-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 20px;
  background: rgba(99, 102, 241, 0.15);
  color: #6366f1;
  font-weight: 500;
}
.header-actions {
  display: flex;
  gap: 8px;
}
.icon-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid #27272a;
  background: transparent;
  color: #a1a1aa;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.icon-btn:hover {
  background: #1a1a1f;
  color: #e4e4e7;
  border-color: #3f3f46;
}

/* Messages Wrapper */
.messages-wrapper {
  flex: 1;
  overflow-y: auto;
  padding: 24px 0;
  min-height: 0;
  width: 100%;
}

/* Empty State */
.empty-chat {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 40px;
  min-height: 400px;
}
.empty-icon {
  font-size: 56px;
  margin-bottom: 24px;
}
.empty-chat h2 {
  font-size: 22px;
  font-weight: 600;
  color: #fff;
  margin: 0 0 8px;
}
.empty-desc {
  font-size: 14px;
  color: #71717a;
  margin-bottom: 32px;
  max-width: 400px;
}
.quick-prompts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  max-width: 500px;
}
.quick-prompt {
  padding: 10px 16px;
  border: 1px solid #27272a;
  border-radius: 10px;
  background: #111114;
  color: #a1a1aa;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.quick-prompt:hover {
  border-color: #6366f1;
  color: #6366f1;
  background: rgba(99, 102, 241, 0.05);
}

/* Messages */
.message-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  animation: fadeIn 0.3s ease;
  width: 100%;
  margin: 0 0 20px;
  padding: 0 24px;
  box-sizing: border-box;
}
.message-row:last-child {
  margin-bottom: 0;
}
.message-row.user {
  flex-direction: row-reverse;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.message-avatar {
  flex-shrink: 0;
}
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
}
.avatar.user {
  background: #6366f1;
  color: #fff;
}
.avatar.ai {
  background: #1a1a1f;
  border: 1px solid #27272a;
  color: #a1a1aa;
}
.message-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 100%;
}
.message-bubble {
  padding: 14px 18px;
  border-radius: 14px;
  font-size: 15px;
  line-height: 1.6;
  word-wrap: break-word;
}
.message-bubble.user {
  background: #6366f1;
  color: #fff;
  border-bottom-right-radius: 4px;
}
.message-bubble.assistant {
  background: #111114;
  border: 1px solid #1e1e24;
  color: #e4e4e7;
  border-bottom-left-radius: 4px;
}
.message-text {
  margin: 0;
  white-space: pre-wrap;
  font-size: 15px;
}
.message-time {
  font-size: 11px;
  color: #52525b;
  margin-top: 2px;
}
.message-row.user .message-time {
  text-align: right;
}

/* Typing Indicator */
.typing-indicator {
  display: flex;
  gap: 6px;
  padding: 4px 0;
}
.typing-indicator span {
  width: 8px;
  height: 8px;
  background: #6366f1;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out;
}
.typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
.typing-indicator span:nth-child(2) { animation-delay: -0.16s; }
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}

/* Loading Indicator */
.loading-bubble {
  display: flex;
  align-items: center;
}
.loading-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
.loading-text {
  font-size: 14px;
  color: #a1a1aa;
  font-weight: 500;
}
.loading-dots {
  display: flex;
  gap: 4px;
}
.loading-dots span {
  width: 6px;
  height: 6px;
  background: #6366f1;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out;
}
.loading-dots span:nth-child(1) { animation-delay: -0.32s; }
.loading-dots span:nth-child(2) { animation-delay: -0.16s; }

/* Footer Input */
.chat-footer {
  padding: 16px 24px 24px;
  border-top: 1px solid #1e1e24;
  background: #111114;
  flex-shrink: 0;
  width: 100%;
}
.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  background: #0a0a0f;
  border: 1px solid #27272a;
  border-radius: 16px;
  padding: 8px 8px 8px 16px;
  transition: border-color 0.2s;
  width: 100%;
}
.input-wrapper:focus-within {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}
textarea {
  flex: 1;
  border: none;
  background: transparent;
  color: #e4e4e7;
  font-size: 15px;
  font-family: inherit;
  line-height: 1.5;
  resize: none;
  max-height: 120px;
  min-height: 52px;
  padding: 8px 0;
  outline: none;
}
textarea::placeholder {
  color: #52525b;
}
.send-btn {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  border: none;
  background: #27272a;
  color: #52525b;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}
.send-btn.active {
  background: #6366f1;
  color: #fff;
}
.send-btn:hover:not(:disabled) {
  transform: scale(1.05);
}
.send-btn:disabled {
  cursor: not-allowed;
}
.input-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  max-width: 800px;
  margin-left: auto;
  margin-right: auto;
}
.hint {
  font-size: 11px;
  color: #52525b;
}
.cancel-btn {
  padding: 4px 12px;
  border: 1px solid #ef4444;
  border-radius: 6px;
  background: transparent;
  color: #ef4444;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.cancel-btn:hover {
  background: rgba(239, 68, 68, 0.1);
}

/* Responsive */
@media (max-width: 768px) {
  .message-content { max-width: 85%; }
}
</style>