<template>
  <div class="short-analysis-view">
    <h1>Short-Selling Analysis</h1>
    <TokenSelector @select="onTokenSelect" />
    <DimensionToggles v-model="activeDimensions" />
    <button @click="runAnalysis" :disabled="!selectedSymbol || store.loading">
      {{ store.loading ? 'Analyzing...' : 'Analyze' }}
    </button>
    <AnalysisReport v-if="store.currentReport" :report="store.currentReport" />
    <ComparisonChart v-if="comparisonTokens.length" :tokens="comparisonTokens" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useAnalysisStore } from '@/stores/analysis'
import TokenSelector from '@/components/TokenSelector.vue'
import DimensionToggles from '@/components/DimensionToggles.vue'
import AnalysisReport from '@/components/AnalysisReport.vue'
import ComparisonChart from '@/components/ComparisonChart.vue'

const store = useAnalysisStore()
const selectedSymbol = ref('')
const activeDimensions = ref<Record<string, boolean>>({
  derivatives: true,
  onchain: true,
  unlock: false,
  technical: false,
  sentiment: false,
})
const comparisonTokens = ref<any[]>([])

function onTokenSelect(token: { symbol: string }) {
  selectedSymbol.value = token.symbol.toUpperCase()
}

async function runAnalysis() {
  if (!selectedSymbol.value) return
  const dims = Object.entries(activeDimensions.value)
    .filter(([, v]) => v)
    .map(([k]) => k)
  await store.analyzeShort(selectedSymbol.value, dims)
}
</script>

<style scoped>
.short-analysis-view { padding: 24px; }
</style>
