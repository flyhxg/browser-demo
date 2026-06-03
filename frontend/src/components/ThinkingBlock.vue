<template>
  <div class="thinking-block">
    <div class="thinking-header">
      <span class="thinking-icon">💡</span>
      <span class="thinking-label">Thinking</span>
    </div>
    <div class="thinking-steps">
      <div v-for="(step, idx) in steps" :key="idx" class="thinking-step">
        <span class="step-number">{{ step.step }}</span>
        <span class="step-description">{{ step.description }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ThinkingStep } from '../types'

defineProps<{
  steps: ThinkingStep[]
}>()
</script>

<style scoped>
.thinking-block {
  padding: 12px 16px;
  background: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 10px;
  margin-bottom: 12px;
}
.thinking-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #6366f1;
}
.thinking-icon {
  font-size: 14px;
}
.thinking-step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
  color: #a1a1aa;
}
.step-number {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.15);
  color: #6366f1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}
.step-description {
  line-height: 1.4;
}
</style>
