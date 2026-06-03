<template>
  <div class="thinking-block collapsed" @click="toggle" v-if="show">
    <div class="thinking-header">
      <span class="thinking-icon">💡</span>
      <span class="thinking-label">Thinking</span>
      <span class="toggle-icon" :class="{ expanded: isExpanded }">▶</span>
    </div>
    <div v-if="isExpanded" class="thinking-steps">
      <div v-for="(step, idx) in steps" :key="idx" class="thinking-step">
        <span class="step-number">{{ step.step }}</span>
        <span class="step-description">{{ step.description }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ThinkingStep } from '../types'

const props = defineProps<{
  steps: ThinkingStep[]
}>()

const isExpanded = ref(false)
const show = computed(() => props.steps && props.steps.length > 0)

function toggle() {
  isExpanded.value = !isExpanded.value
}
</script>

<style scoped>
.thinking-block {
  padding: 8px 12px;
  background: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 8px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s;
}
.thinking-block:hover {
  background: rgba(99, 102, 241, 0.12);
}
.thinking-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #6366f1;
  user-select: none;
}
.thinking-icon {
  font-size: 12px;
}
.thinking-label {
  flex: 1;
}
.toggle-icon {
  font-size: 10px;
  transition: transform 0.2s;
  color: #6366f1;
}
.toggle-icon.expanded {
  transform: rotate(90deg);
}
.thinking-steps {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(99, 102, 241, 0.1);
}
.thinking-step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  font-size: 12px;
  color: #a1a1aa;
}
.step-number {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.15);
  color: #6366f1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 600;
  flex-shrink: 0;
}
.step-description {
  line-height: 1.4;
}
</style>
