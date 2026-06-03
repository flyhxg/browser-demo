<template>
  <div v-if="result || error" class="result-display">
    <div v-if="error" class="error-box">
      <div class="box-header">Error</div>
      <p>{{ error.message }}</p>
    </div>
    <div v-if="result" class="result-box" :class="{ 'with-error': error }">
      <div class="box-header">Result</div>
      <p>{{ result.output }}</p>
      <div class="meta">
        <span>{{ result.steps }} steps</span>
        <span>{{ (result.duration_ms / 1000).toFixed(1) }}s</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ResultData, ErrorData } from '../types'

defineProps<{ result: ResultData | null; error: ErrorData | null }>()
</script>

<style scoped>
.result-display { margin-top: 20px; }
.result-box, .error-box {
  border-radius: 10px;
  padding: 20px;
}
.result-box { background: #052e16; border: 1px solid #166534; }
.result-box.with-error { background: #1a1a0a; border: 1px solid #4a4a1a; }
.error-box { background: #2a0a0a; border: 1px solid #7f1d1d; }
.box-header {
  font-weight: 700;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
  color: #a1a1aa;
}
p { margin: 0; white-space: pre-wrap; font-size: 14px; line-height: 1.6; }
.meta {
  margin-top: 12px;
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #71717a;
}
</style>
