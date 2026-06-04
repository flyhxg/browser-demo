<template>
  <div class="tool-call-block" :class="{ collapsed: !isExpanded }" @click="toggle">
    <div class="tool-call-header">
      <span class="tool-icon">🔧</span>
      <span class="tool-name">{{ toolCall.name }}</span>
      <a
        v-if="(toolCall.source?.url) || (resolvedSource.url && toolCall.name in TOOL_DEFAULTS)"
        class="tool-source"
        :href="toolCall.source?.url || resolvedSource.url"
        target="_blank"
        rel="noopener noreferrer"
        @click.stop
      >{{ toolCall.source?.label || resolvedSource.label }} ↗</a>
      <span v-else-if="toolCall.source?.label || resolvedSource.label" class="tool-source">{{ toolCall.source?.label || resolvedSource.label }}</span>
      <span v-if="toolCall.status === 'pending'" class="tool-spinner"></span>
      <span v-else-if="toolCall.status === 'completed'" class="tool-status completed">✓</span>
      <span v-else class="tool-status error">✗</span>
      <span class="toggle-icon" :class="{ expanded: isExpanded }">▶</span>
    </div>
    <div v-if="isExpanded" class="tool-details">
      <div v-if="toolCall.arguments" class="tool-arguments">
        <div class="detail-label">Arguments</div>
        <code>{{ JSON.stringify(toolCall.arguments, null, 2) }}</code>
      </div>
      <div v-if="toolCall.result" class="tool-result">
        <div class="detail-label">Result</div>
        <pre>{{ JSON.stringify(toolCall.result, null, 2) }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { ToolCall } from '../types'
import { TOOL_DEFAULTS, defaultSourceFor } from '../utils/toolSources'

const props = defineProps<{
  toolCall: ToolCall
  isComplete?: boolean
}>()

const resolvedSource = computed(() => props.toolCall.source ?? defaultSourceFor(props.toolCall.name))

const isExpanded = ref(!props.isComplete)
const userToggled = ref(false)

watch(
  () => props.isComplete,
  (complete) => {
    if (complete && !userToggled.value) {
      isExpanded.value = false
    }
  },
)

function toggle() {
  userToggled.value = true
  isExpanded.value = !isExpanded.value
}
</script>

<style scoped>
.tool-call-block {
  padding: 8px 12px;
  background: rgba(34, 197, 94, 0.08);
  border: 1px solid rgba(34, 197, 94, 0.2);
  border-radius: 8px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s;
}
.tool-call-block.collapsed {
  background: rgba(34, 197, 94, 0.04);
}
.tool-call-block:hover {
  background: rgba(34, 197, 94, 0.12);
}
.tool-call-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  color: #22c55e;
  user-select: none;
}
.tool-icon {
  font-size: 12px;
}
.tool-name {
  flex: 1;
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
.toggle-icon {
  font-size: 10px;
  transition: transform 0.2s;
  color: #22c55e;
}
.toggle-icon.expanded {
  transform: rotate(90deg);
}
.tool-details {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(34, 197, 94, 0.1);
}
.detail-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #22c55e;
  opacity: 0.7;
  margin-bottom: 4px;
}
.tool-arguments code {
  font-size: 11px;
  color: #a1a1aa;
  background: rgba(0,0,0,0.2);
  padding: 4px 8px;
  border-radius: 4px;
  display: block;
  overflow-x: auto;
}
.tool-result pre {
  font-size: 11px;
  color: #e4e4e7;
  background: rgba(0,0,0,0.2);
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
  margin: 0;
}
.tool-source {
  font-size: 10px;
  font-weight: 500;
  color: #22c55e;
  background: rgba(34, 197, 94, 0.1);
  padding: 1px 6px;
  border-radius: 8px;
  text-decoration: none;
  border: 1px solid rgba(34, 197, 94, 0.2);
  white-space: nowrap;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
}
a.tool-source:hover {
  background: rgba(34, 197, 94, 0.2);
}
</style>
