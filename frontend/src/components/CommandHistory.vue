<template>
  <div class="command-history">
    <h3>Results</h3>
    <div class="history-list" ref="listEl">
      <div
        v-for="(item, idx) in history"
        :key="idx"
        class="history-item"
        :class="{ latest: idx === history.length - 1 }"
      >
        <div class="box-header">Command {{ idx + 1 }}</div>
        <p>{{ item.output }}</p>
        <div class="meta">
          <span>{{ item.steps }} steps</span>
          <span>{{ (item.duration_ms / 1000).toFixed(1) }}s</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import type { ResultData } from '../types'

const props = defineProps<{ history: ResultData[] }>()
const listEl = ref<HTMLElement | null>(null)

watch(() => props.history.length, async () => {
  await nextTick()
  if (listEl.value) {
    listEl.value.scrollTop = listEl.value.scrollHeight
  }
})
</script>

<style scoped>
.command-history {
  background: #18181b;
  border: 1px solid #27272a;
  border-radius: 10px;
  padding: 16px;
}
h3 { margin: 0 0 12px; font-size: 14px; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.5px; }
.history-list {
  max-height: 300px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.history-item {
  border-radius: 8px;
  padding: 12px;
  background: #0a0a0a;
  border: 1px solid #1c1c1e;
}
.history-item.latest {
  background: #052e16;
  border-color: #166534;
}
.box-header {
  font-weight: 700;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
  color: #71717a;
}
p { margin: 0; white-space: pre-wrap; font-size: 13px; line-height: 1.5; }
.meta {
  margin-top: 8px;
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #52525b;
}
</style>