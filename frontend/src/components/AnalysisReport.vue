<template>
  <div class="analysis-report" v-if="report">
    <h2>{{ report.symbol }} Analysis</h2>
    <p class="summary">{{ report.llm_analysis.summary }}</p>
    <div class="dimensions">
      <div v-for="(data, dim) in report.dimensions" :key="dim" class="dimension-card">
        <h3>{{ dim }}</h3>
        <pre>{{ JSON.stringify(data, null, 2) }}</pre>
      </div>
    </div>
    <div class="recommendation">
      <strong>Recommendation:</strong> {{ report.llm_analysis.recommendation }}
      <br />
      <strong>Confidence:</strong> {{ report.llm_analysis.confidence }}
    </div>
  </div>
</template>

<script setup lang="ts">
interface AnalysisReportProps {
  symbol: string
  timestamp: string
  dimensions: Record<string, any>
  llm_analysis: {
    summary: string
    strengths: string[]
    risks: string[]
    confidence: number
    recommendation: string
  }
}
defineProps<{ report: AnalysisReportProps }>()
</script>

<style scoped>
.analysis-report { padding: 16px; border: 1px solid #ddd; border-radius: 8px; }
.dimension-card { margin-top: 12px; padding: 8px; background: #f9f9f9; border-radius: 4px; }
.recommendation { margin-top: 16px; font-size: 1.1em; }
</style>
