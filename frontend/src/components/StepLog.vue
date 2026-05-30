<template>
  <div class="step-log">
    <h3>Steps</h3>
    <div v-if="steps.length === 0" class="empty">No steps yet</div>
    <div v-for="step in steps" :key="step.step" class="step-item">
      <span class="step-num">{{ step.step }}</span>
      <span :class="['status', step.status]">{{ statusIcon(step.status) }}</span>
      <span class="action">{{ step.action }}</span>
      <span v-if="step.target" class="target">{{ step.target }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { StepData } from '../types'

defineProps<{ steps: StepData[] }>()

function statusIcon(status: string): string {
  switch (status) {
    case 'running': return '...'
    case 'done': return 'done'
    case 'error': return 'error'
    default: return '-'
  }
}
</script>

<style scoped>
.step-log {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 12px;
  max-height: 300px;
  overflow-y: auto;
}
h3 { margin: 0 0 8px; }
.empty { color: #999; font-style: italic; }
.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid #f0f0f0;
}
.step-num { font-weight: 600; min-width: 24px; }
.status { font-size: 12px; padding: 2px 6px; border-radius: 3px; }
.status.running { background: #fff3cd; color: #856404; }
.status.done { background: #d4edda; color: #155724; }
.status.error { background: #f8d7da; color: #721c24; }
.action { font-weight: 500; }
.target { color: #666; font-size: 13px; }
</style>
