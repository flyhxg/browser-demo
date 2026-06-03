<template>
  <div ref="chartRef" class="funding-chart" :style="{ width: props.width, height: props.height }"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import * as echarts from 'echarts'

interface Props {
  fundingRate: number
  width?: string
  height?: string
}

const props = withDefaults(defineProps<Props>(), {
  width: '100%',
  height: '200px',
})

const chartRef = ref<HTMLDivElement>()
let chartInstance: echarts.ECharts | null = null

function initChart() {
  if (!chartRef.value) return

  chartInstance = echarts.init(chartRef.value)
  updateChart()

  window.addEventListener('resize', () => {
    chartInstance?.resize()
  })
}

function updateChart() {
  if (!chartInstance) return

  const isNegative = props.fundingRate < 0
  const color = isNegative ? '#22c55e' : '#ef4444'
  const label = isNegative ? 'Shorts Pay Longs' : 'Longs Pay Shorts'

  const option: echarts.EChartsOption = {
    title: {
      text: 'Funding Rate Indicator',
      left: 'center',
      textStyle: { color: '#fff', fontSize: 14, fontWeight: 'bold' },
    },
    series: [
      {
        type: 'gauge',
        startAngle: 180,
        endAngle: 0,
        min: -0.02,
        max: 0.02,
        splitNumber: 4,
        axisLine: {
          lineStyle: {
            width: 20,
            color: [
              [0.25, '#22c55e'],
              [0.5, '#71717a'],
              [0.75, '#f59e0b'],
              [1, '#ef4444'],
            ],
          },
        },
        pointer: {
          itemStyle: { color: color },
          width: 6,
          length: '70%',
        },
        axisTick: {
          distance: -20,
          length: 8,
          lineStyle: { color: '#71717a', width: 1 },
        },
        splitLine: {
          distance: -20,
          length: 16,
          lineStyle: { color: '#71717a', width: 2 },
        },
        axisLabel: {
          color: '#71717a',
          fontSize: 10,
          formatter: (value: number) => `${(value * 100).toFixed(2)}%`,
        },
        detail: {
          valueAnimation: true,
          formatter: `{value|${(props.fundingRate * 100).toFixed(4)}%}\n{name|${label}}`,
          rich: {
            value: { fontSize: 24, fontWeight: 'bold', color: color, padding: [10, 0, 0, 0] },
            name: { fontSize: 12, color: '#71717a', padding: [5, 0, 0, 0] },
          },
        },
        data: [{ value: props.fundingRate }],
      },
    ],
  }

  chartInstance.setOption(option)
}

onMounted(() => {
  initChart()
})

watch(() => props.fundingRate, () => {
  updateChart()
})
</script>

<style scoped>
.funding-chart {
  border-radius: 8px;
  overflow: hidden;
}
</style>
