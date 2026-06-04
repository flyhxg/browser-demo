<template>
  <div class="thinking-block" :class="{ collapsed: !isExpanded }" @click="toggle" v-if="show">
    <div class="thinking-header">
      <span class="thinking-icon">💭</span>
      <span class="thinking-label">Thinking</span>
      <span class="step-count">{{ steps.length }} step{{ steps.length === 1 ? '' : 's' }}</span>
      <span class="toggle-icon" :class="{ expanded: isExpanded }">▶</span>
    </div>
    <div v-if="isExpanded" class="thinking-steps">
      <div v-for="(step, idx) in steps" :key="idx" class="thinking-step">
        <span class="step-dot"></span>
        <span class="step-number">{{ step.step }}</span>
        <span class="step-description">{{ step.description }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { ThinkingStep } from '../types'

const props = defineProps<{
  steps: ThinkingStep[]
  isComplete?: boolean
}>()

const isExpanded = ref(!props.isComplete)
const userToggled = ref(false)
const show = computed(() => props.steps && props.steps.length > 0)

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
.thinking-block.collapsed {
  background: rgba(99, 102, 241, 0.04);
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
.step-count {
  font-size: 10px;
  font-weight: 500;
  color: #818cf8;
  background: rgba(99, 102, 241, 0.1);
  padding: 1px 6px;
  border-radius: 8px;
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
  position: relative;
}
.thinking-step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
  color: #a1a1aa;
  position: relative;
}
.thinking-step:not(:last-child) .step-dot::after {
  content: '';
  position: absolute;
  top: 14px;
  left: 3px;
  width: 1px;
  height: calc(100% - 8px);
  background: rgba(99, 102, 241, 0.3);
}
.step-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #6366f1;
  flex-shrink: 0;
  margin-left: 2px;
  position: relative;
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
  flex: 1;
}
</style>
