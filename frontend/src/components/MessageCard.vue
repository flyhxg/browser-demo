<template>
  <div class="message-row" :class="msg.role">
    <div class="message-avatar">
      <div v-if="msg.role === 'user'" class="avatar user">U</div>
      <div v-else class="avatar ai">AI</div>
    </div>
    <div class="message-content">
      <div class="message-bubble" :class="msg.role">
        <ThinkingBlock v-if="msg.thinkingSteps?.length && !msg.text" :steps="msg.thinkingSteps" />
        <ToolCallBlock v-for="(tc, idx) in msg.toolCalls" :key="idx" :toolCall="tc" />
        <p class="message-text">{{ msg.text }}</p>
      </div>
      <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ExtendedChatMessage } from '../types'
import ThinkingBlock from './ThinkingBlock.vue'
import ToolCallBlock from './ToolCallBlock.vue'

defineProps<{
  msg: ExtendedChatMessage
}>()

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
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
.message-row:last-child { margin-bottom: 0; }
.message-row.user { flex-direction: row-reverse; }
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.message-avatar { flex-shrink: 0; }
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
.avatar.user { background: #6366f1; color: #fff; }
.avatar.ai { background: #1a1a1f; border: 1px solid #27272a; color: #a1a1aa; }
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
.message-text { margin: 0; white-space: pre-wrap; font-size: 15px; }
.message-time { font-size: 11px; color: #52525b; margin-top: 2px; }
.message-row.user .message-time { text-align: right; }
</style>
