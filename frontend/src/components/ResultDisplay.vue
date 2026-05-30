<template>
  <div v-if="result || error" class="result-display">
    <div v-if="error" class="error-box">
      <h3>Error</h3>
      <p>{{ error.message }}</p>
    </div>
    <div v-else-if="result" class="result-box">
      <h3>Result</h3>
      <p>{{ result.output }}</p>
      <div class="meta">
        <span>Steps: {{ result.steps }}</span>
        <span>Duration: {{ (result.duration_ms / 1000).toFixed(1) }}s</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ResultData, ErrorData } from '../types'

defineProps<{ result: ResultData | null; error: ErrorData | null }>()
</script>

<style scoped>
.result-display { margin-top: 16px; }
.result-box, .error-box {
  border-radius: 8px;
  padding: 16px;
}
.result-box { background: #d4edda; border: 1px solid #c3e6cb; }
.error-box { background: #f8d7da; border: 1px solid #f5c6cb; }
h3 { margin: 0 0 8px; }
p { margin: 0; white-space: pre-wrap; }
.meta {
  margin-top: 8px;
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #666;
}
</style>
