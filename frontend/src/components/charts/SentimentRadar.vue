<template>
  <div ref="chartRef" class="sentiment-radar" :style="{ width: props.width, height: props.height }"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import * as echarts from 'echarts'

interface Props {
  crowdednessScore: number
  squeezeRisk: number
  reboundPotential: number
  heatScore: number
  fundingRate: number
  width?: string
  height?: string
}

const props = withDefaults(defineProps<Props>(), {
  width: '100%',
  height: '300px',
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

  const data = [
    props.crowdednessScore,
    props.squeezeRisk,
    props.reboundPotential,
    props.heatScore,
    Math.min(Math.abs(props.fundingRate) * 100, 1), // Scale funding rate
  ]

  const option: echarts.EChartsOption = {
    title: {
      text: 'Short-Selling Risk Profile',
      left: 'center',
      textStyle: { color: '#fff', fontSize: 14, fontWeight: 'bold' },
    },
    tooltip: {
      trigger: 'item',
      backgroundColor: '#1a1a1f',
      borderColor: '#27272a',
      textStyle: { color: '#e4e4e7' },
      formatter: (params: any) => {
        const names = ['Crowdedness', 'Squeeze Risk', 'Rebound Potential', 'Heat Score', 'Funding Intensity']
        const vals = [props.crowdednessScore, props.squeezeRisk, props.reboundPotential, props.heatScore, Math.min(Math.abs(props.fundingRate) * 100, 1)]
        return `<div style="font-size:13px;font-weight:600">${params.name}</div>
                <div>${names[params.dataIndex]}: ${(vals[params.dataIndex] * 100).toFixed(1)}%</div>`
      },
    },
    radar: {
      indicator: [
        { name: 'Crowdedness', max: 1 },
        { name: 'Squeeze Risk', max: 1 },
        { name: 'Rebound', max: 1 },
        { name: 'Heat', max: 1 },
        { name: 'Funding', max: 1 },
      ],
      shape: 'polygon',
      splitNumber: 4,
      axisName: {
        color: '#71717a',
        fontSize: 11,
      },
      splitLine: {
        lineStyle: { color: '#27272a' },
      },
      splitArea: {
        areaStyle: {
          color: ['#111114', '#1a1a1f'],
          opacity: 0.5,
        },
      },
      axisLine: {
        lineStyle: { color: '#27272a' },
      },
    },
    series: [
      {
        name: 'Risk Profile',
        type: 'radar',
        data: [
          {
            value: data,
            name: 'Current',
            areaStyle: {
              color: 'rgba(239, 68, 68, 0.3)',
            },
            lineStyle: {
              color: '#ef4444',
              width: 2,
            },
            itemStyle: {
              color: '#ef4444',
            },
          },
        ],
      },
    ],
  }

  chartInstance.setOption(option)
}

onMounted(() => {
  initChart()
})

watch(() => [props.crowdednessScore, props.squeezeRisk, props.reboundPotential, props.heatScore, props.fundingRate], () => {
  updateChart()
}, { deep: true })
</script>

<style scoped>
.sentiment-radar {
  border-radius: 8px;
  overflow: hidden;
}
</style>
