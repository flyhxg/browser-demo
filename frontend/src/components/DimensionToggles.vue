<template>
  <div class="dimension-toggles">
    <label v-for="dim in dimensions" :key="dim.key" class="toggle-label">
      <input type="checkbox" v-model="modelValue[dim.key]" />
      {{ dim.label }}
    </label>
  </div>
</template>

<script setup lang="ts">
const dimensions = [
  { key: 'derivatives', label: 'Derivatives' },
  { key: 'onchain', label: 'On-Chain' },
  { key: 'unlock', label: 'Unlock / FDV' },
  { key: 'technical', label: 'Technical' },
  { key: 'sentiment', label: 'Sentiment' },
]
const modelValue = defineModel<Record<string, boolean>>({ required: true })
</script>

<style scoped>
.dimension-toggles { display: flex; gap: 12px; flex-wrap: wrap; }
.toggle-label { cursor: pointer; }
</style>
