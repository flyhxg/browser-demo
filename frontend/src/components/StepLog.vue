<template>
  <div class="step-log">
    <div class="step-log-header" @click="collapsed = !collapsed">
      <span>Steps</span>
      <span class="toggle">{{ collapsed ? '▶' : '▼' }}</span>
    </div>
    <div v-if="!collapsed">
      <div v-if="steps.length === 0" class="empty">Waiting for task...</div>
      <div v-for="step in steps" :key="step.step" class="step-item">
        <span class="step-num">{{ step.step }}</span>
        <span :class="['status-dot', step.status]"></span>
        <span class="action">{{ step.action }}</span>
        <span v-if="step.target" class="target">{{ step.target }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { StepData } from '../types'

defineProps<{ steps: StepData[] }>()
const collapsed = ref(false)
</script>

<style scoped>
.step-log {
  background: #18181b;
  border: 1px solid #27272a;
  border-radius: 10px;
  padding: 16px;
  max-height: 400px;
  overflow-y: auto;
}
.step-log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  padding-bottom: 12px;
  font-size: 14px;
  color: #a1a1aa;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  user-select: none;
}
.step-log-header:hover { color: #E4E4E7; }
.toggle { font-size: 10px; }
.empty { color: #52525b; font-style: italic; text-align: center; padding: 32px; }
.step-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid #1f1f23;
}
.step-item:last-child { border-bottom: none; }
.step-num { font-weight: 700; min-width: 28px; color: #71717a; font-size: 13px; }
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-dot.running { background: #eab308; animation: pulse 1.5s infinite; }
.status-dot.done { background: #22c55e; }
.status-dot.error { background: #ef4444; }
.action { font-weight: 500; font-size: 14px; }
.target { color: #71717a; font-size: 13px; }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>