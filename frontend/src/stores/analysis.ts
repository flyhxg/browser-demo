import { ref } from 'vue'
import { defineStore } from 'pinia'

export interface AnalysisReport {
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

export const useAnalysisStore = defineStore('analysis', () => {
  const currentReport = ref<AnalysisReport | null>(null)
  const reports = ref<AnalysisReport[]>([])
  const loading = ref(false)
  const activeDimensions = ref<Record<string, boolean>>({
    derivatives: true,
    onchain: true,
    unlock: false,
    technical: false,
    sentiment: false,
  })

  async function analyzeShort(symbol: string, dims?: string[]) {
    loading.value = true
    try {
      const dimensions = dims || Object.entries(activeDimensions.value)
        .filter(([, v]) => v)
        .map(([k]) => k)
      const response = await fetch('/api/analyze/short', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, dimensions }),
      })
      const report: AnalysisReport = await response.json()
      currentReport.value = report
      reports.value.unshift(report)
      cacheReport(report)
      return report
    } finally {
      loading.value = false
    }
  }

  async function compareTokens(symbols: string[], dims?: string[]) {
    loading.value = true
    try {
      const dimensions = dims || Object.entries(activeDimensions.value)
        .filter(([, v]) => v)
        .map(([k]) => k)
      const response = await fetch('/api/analyze/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbols, dimensions }),
      })
      return await response.json()
    } finally {
      loading.value = false
    }
  }

  function cacheReport(report: AnalysisReport) {
    const key = `analysis_${report.symbol}_${report.timestamp}`
    localStorage.setItem(key, JSON.stringify(report))
  }

  function setDimensions(dims: Record<string, boolean>) {
    activeDimensions.value = { ...activeDimensions.value, ...dims }
  }

  return {
    currentReport,
    reports,
    loading,
    activeDimensions,
    analyzeShort,
    compareTokens,
    cacheReport,
    setDimensions,
  }
})
