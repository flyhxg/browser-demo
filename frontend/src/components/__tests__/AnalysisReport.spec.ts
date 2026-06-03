import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AnalysisReport from '../AnalysisReport.vue'

describe('AnalysisReport', () => {
  it('renders symbol', () => {
    const wrapper = mount(AnalysisReport, {
      props: {
        report: {
          symbol: 'BTC',
          timestamp: '2026-06-04T00:00:00Z',
          dimensions: {},
          llm_analysis: { summary: 'test', strengths: [], risks: [], confidence: 0.5, recommendation: 'neutral' }
        }
      }
    })
    expect(wrapper.text()).toContain('BTC')
  })
})
