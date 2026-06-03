<template>
  <div class="tool-call-block">
    <div class="tool-call-header">
      <span class="tool-icon">🔧</span>
      <span class="tool-name">{{ toolCall.name }}</span>
      <span v-if="toolCall.status === 'pending'" class="tool-spinner"></span>
      <span v-else-if="toolCall.status === 'completed'" class="tool-status completed">✓</span>
      <span v-else class="tool-status error">✗</span>
    </div>
    <div v-if="toolCall.arguments" class="tool-arguments">
      <code>{{ JSON.stringify(toolCall.arguments, null, 2) }}</code>
    </div>
    <div v-if="toolCall.result" class="tool-result">
      <pre>{{ JSON.stringify(toolCall.result, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ToolCall } from '../types'

defineProps<{
  toolCall: ToolCall
}>()
</script>

<style scoped>
.tool-call-block {
  padding: 12px 16px;
  background: rgba(34, 197, 94, 0.08);
  border: 1px solid rgba(34, 197, 94, 0.2);
  border-radius: 10px;
  margin-bottom: 12px;
}
.tool-call-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #22c55e;
}
.tool-icon {
  font-size: 14px;
}
.tool-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(34, 197, 94, 0.3);
  border-top-color: #22c55e;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.tool-status.completed { color: #22c55e; }
.tool-status.error { color: #ef4444; }
.tool-arguments code {
  font-size: 12px;
  color: #a1a1aa;
  background: rgba(0,0,0,0.2);
  padding: 4px 8px;
  border-radius: 4px;
  display: block;
  overflow-x: auto;
}
.tool-result pre {
  font-size: 12px;
  color: #e4e4e7;
  background: rgba(0,0,0,0.2);
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
  margin: 0;
}
</style>
