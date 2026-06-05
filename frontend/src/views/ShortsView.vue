<template>
  <div class="shorts-view">
    <!-- Header -->
    <div class="sv-header">
      <div class="sv-title">
        <span class="sv-icon">📉</span>
        <h1>Short Selling</h1>
      </div>
      <p class="sv-subtitle">Heat-ranked tokens with 做空评级 & short-squeeze analysis</p>
    </div>

    <!-- Actions Bar -->
    <div class="actions-bar">
      <button class="btn-primary" @click="fetchHotTokens" :disabled="htLoading">
        {{ htLoading ? 'Loading...' : 'Refresh Hot Tokens' }}
      </button>
      <button class="btn-outline" @click="startScanner" :disabled="scannerRunning">
        {{ scannerRunning ? 'Scanner Running' : 'Start Scanner' }}
      </button>
      <button class="btn-outline" @click="stopScanner" :disabled="!scannerRunning">
        Stop Scanner
      </button>
      <div class="auto-trade-toggle">
        <label class="toggle-label">
          <input type="checkbox" v-model="autoTradeEnabled" @change="toggleAutoTrade" />
          <span class="toggle-text">Auto Trade</span>
          <span class="toggle-status" :class="autoTradeEnabled ? 'on' : 'off'">
            {{ autoTradeEnabled ? 'ON' : 'OFF' }}
          </span>
        </label>
      </div>
    </div>

    <!-- Hot Tokens Table -->
    <div v-if="hotTokens.length === 0 && !htLoading" class="empty-state">
      <div class="empty-icon">🔥</div>
      <div class="empty-title">No hot tokens yet</div>
      <div class="empty-desc">Start the scanner to discover hot tokens.</div>
    </div>
    <div v-else class="hot-tokens-table">
      <table>
        <thead>
          <tr>
            <th>排名</th><th>币种</th><th>板块</th><th>价格</th><th>24h涨跌</th>
            <th>24h成交</th><th>资金费率</th><th>热度</th><th>做空评级</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(token, idx) in hotTokens" :key="token.symbol">
            <td>{{ idx + 1 }}</td>
            <td>{{ token.symbol }}</td>
            <td class="sector-cell">{{ token.sector || '其他' }}</td>
            <td>${{ token.price?.toFixed(2) }}</td>
            <td :class="token.price_change_24h >= 0 ? 'profit' : 'loss'">
              {{ token.price_change_24h >= 0 ? '+' : '' }}{{ token.price_change_24h?.toFixed(2) }}%
            </td>
            <td>{{ (token.volume_usd / 1e6).toFixed(1) }}M</td>
            <td :class="(token.funding_rate || 0) < 0 ? 'profit' : 'loss'">
              {{ (token.funding_rate * 100)?.toFixed(4) }}%
            </td>
            <td>{{ token.heat_score?.toFixed(2) }}</td>
            <td :class="['grade-cell', 'grade-' + (token.short_grade || 'B').toLowerCase()]">
              {{ token.short_grade || '-' }}
            </td>
            <td>
              <button class="btn-outline" @click="openAnalysis(token)">分析</button>
              <button class="btn-accent" @click="tradeHotToken(token.symbol)">交易</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Token Analysis Modal -->
    <div v-if="selectedToken" class="analysis-modal" @click.self="closeAnalysis">
      <div class="analysis-panel">
        <div class="analysis-header">
          <div class="header-left">
            <h2>{{ selectedToken.symbol }}</h2>
            <span class="header-sector" v-if="selectedToken.sector">{{ selectedToken.sector }}</span>
            <span class="header-price">${{ (selectedToken.price || 0).toFixed(4) }}</span>
            <span :class="['header-change', (selectedToken.price_change_24h >= 0 ? 'up' : 'down')]">
              {{ selectedToken.price_change_24h >= 0 ? '+' : '' }}{{ (selectedToken.price_change_24h || 0).toFixed(2) }}% (24h)
            </span>
          </div>
          <button class="btn-close" @click="closeAnalysis">&times;</button>
        </div>

        <!-- 做空决策条 -->
        <div class="decision-bar" :class="shortRatingClass">
          <div class="decision-grade">
            <div class="grade-label">做空评级</div>
            <div class="grade-value">{{ shortGradeLabel }}</div>
          </div>
          <div class="decision-divider"></div>
          <div class="decision-direction">
            <div class="direction-label">操作建议</div>
            <div class="direction-value">{{ directionText }}</div>
          </div>
          <div class="decision-divider"></div>
          <div class="decision-leverage">
            <div class="leverage-label">建议杠杆</div>
            <div class="leverage-value">{{ recommendedLeverage }}x</div>
          </div>
        </div>

        <div class="analysis-content">
          <!-- 核心指标四卡 -->
          <div class="analysis-metrics">
            <div class="metric-card" :class="fundingColorClass">
              <div class="metric-label">资金费率 (8h)</div>
              <div class="metric-value">
                {{ ((selectedToken.funding_rate || 0) * 100).toFixed(4) }}%
              </div>
              <div class="metric-hint">{{ fundingHintText }}</div>
            </div>
            <div class="metric-card">
              <div class="metric-label">空头拥挤度</div>
              <div class="metric-value">
                {{ ((selectedToken.crowdedness_score || 0) * 100).toFixed(0) }}%
              </div>
              <div class="metric-hint">{{ crowdHintText }}</div>
            </div>
            <div class="metric-card" :class="squeezeClass">
              <div class="metric-label">轧空风险</div>
              <div class="metric-value">
                {{ ((selectedToken.squeeze_risk || 0) * 100).toFixed(0) }}%
              </div>
              <div class="metric-hint">{{ squeezeHintText }}</div>
            </div>
            <div class="metric-card">
              <div class="metric-label">反弹潜力</div>
              <div class="metric-value">
                {{ ((selectedToken.rebound_potential || 0) * 100).toFixed(0) }}%
              </div>
              <div class="metric-hint">价格回弹空间估算</div>
            </div>
          </div>

          <!-- 图表区 -->
          <div class="analysis-charts">
            <div class="chart-row">
              <FundingRateChart
                :funding-rate="selectedToken.funding_rate"
                width="100%"
                height="280px"
              />
              <SentimentRadar
                :crowdedness-score="selectedToken.crowdedness_score || 0"
                :squeeze-risk="selectedToken.squeeze_risk || 0"
                :rebound-potential="selectedToken.rebound_potential || 0"
                :heat-score="selectedToken.heat_score"
                :funding-rate="selectedToken.funding_rate"
                width="100%"
                height="280px"
              />
            </div>
          </div>

          <!-- 详细数据条 -->
          <div class="detail-strip">
            <div class="strip-item">
              <span class="strip-label">板块</span>
              <span class="strip-value">{{ selectedToken.sector || '其他' }}</span>
            </div>
            <div class="strip-item">
              <span class="strip-label">市值(估)</span>
              <span class="strip-value">${{ marketCapText }}</span>
            </div>
            <div class="strip-item">
              <span class="strip-label">24h成交量</span>
              <span class="strip-value">${{ ((selectedToken.volume_usd || 0) / 1e6).toFixed(1) }}M</span>
            </div>
            <div class="strip-item">
              <span class="strip-label">持仓量</span>
              <span class="strip-value">${{ oiUsdText }}</span>
            </div>
            <div class="strip-item">
              <span class="strip-label">多空比</span>
              <span class="strip-value">{{ (selectedToken.long_short_ratio || 0).toFixed(2) }}</span>
            </div>
            <div class="strip-item">
              <span class="strip-label">24h高/低</span>
              <span class="strip-value">${{ (selectedToken.high_24h || 0).toFixed(2) }} / ${{ (selectedToken.low_24h || 0).toFixed(2) }}</span>
            </div>
            <div class="strip-item">
              <span class="strip-label">近期趋势</span>
              <span :class="['strip-value', (selectedToken.consecutive_up_days || 0) >= 0 ? 'profit' : 'loss']">
                {{ consecutiveDaysText }}
              </span>
            </div>
            <div class="strip-item">
              <span class="strip-label">热度</span>
              <span class="strip-value">{{ (selectedToken.heat_score || 0).toFixed(2) }}</span>
            </div>
          </div>

          <!-- 做空参考 -->
          <div class="short-reference">
            <div class="ref-card">
              <div class="ref-label">建议止损价</div>
              <div class="ref-value">${{ (selectedToken.stop_loss_price || 0).toFixed(4) }}</div>
            </div>
            <div class="ref-card">
              <div class="ref-label">建议止盈价</div>
              <div class="ref-value profit">${{ (selectedToken.take_profit_price || 0).toFixed(4) }}</div>
            </div>
            <div class="ref-card">
              <div class="ref-label">24h振幅(ATR)</div>
              <div class="ref-value">${{ (selectedToken.atr || 0).toFixed(4) }}</div>
            </div>
            <div class="ref-card">
              <div class="ref-label">资金费率年化</div>
              <div class="ref-value">{{ ((selectedToken.funding_annualized || 0)).toFixed(1) }}%</div>
            </div>
          </div>

          <!-- 交易建议 -->
          <div v-if="analysisLoading" class="analysis-loading">正在生成交易建议...</div>
          <div v-else-if="tokenAnalysis" class="analysis-recommendation">
            <h3>📋 交易建议</h3>
            <p class="recommendation-text">{{ tokenAnalysis.recommendation }}</p>
            <div class="signal-badges">
              <span v-if="tokenAnalysis.signals?.funding_extreme" class="signal-badge warning">⚠ 极端资金费率</span>
              <span v-if="tokenAnalysis.signals?.overcrowded_short" class="signal-badge danger">🔥 空头过度拥挤</span>
              <span v-if="tokenAnalysis.signals?.squeeze_alert" class="signal-badge alert">💥 轧空警报</span>
              <span v-if="tokenAnalysis.signals?.high_rebound_potential" class="signal-badge success">📈 反弹空间大</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { on as busOn } from '../composables/useMessageBus'
import SentimentRadar from '../components/charts/SentimentRadar.vue'
import FundingRateChart from '../components/charts/FundingRateChart.vue'

interface HotToken {
  symbol: string
  price: number
  price_change_24h: number
  volume_24h: number
  volume_usd: number
  funding_rate: number
  long_short_ratio: number
  open_interest: number
  liquidation_price: number
  heat_score: number
  // Short analysis fields
  crowdedness_score?: number
  squeeze_risk?: number
  short_risk_rating?: string
  rebound_potential?: number
  // Trade execution reference
  high_24h?: number
  low_24h?: number
  atr?: number
  oi_usd?: number
  recommended_leverage?: number
  stop_loss_price?: number
  take_profit_price?: number
  funding_annualized?: number
  short_grade?: string
  // Trend & market context
  market_cap?: number
  consecutive_up_days?: number
  trend_strength?: number
  sector?: string
}

const hotTokens = ref<HotToken[]>([])
const htLoading = ref(false)
const scannerRunning = ref(false)
const autoTradeEnabled = ref(false)
const selectedToken = ref<HotToken | null>(null)
const tokenAnalysis = ref<any>(null)
const analysisLoading = ref(false)

const shortRatingClass = computed(() => {
  const g = selectedToken.value?.short_grade
  if (g === 'S') return 'grade-s'
  if (g === 'A') return 'grade-a'
  if (g === 'B') return 'grade-b'
  if (g === 'C') return 'grade-c'
  if (g === 'D') return 'grade-d'
  return 'grade-b'
})

const shortGradeLabel = computed(() => {
  const g = selectedToken.value?.short_grade
  if (g === 'S') return 'S · 极佳做空机会'
  if (g === 'A') return 'A · 良好做空机会'
  if (g === 'B') return 'B · 中性观望'
  if (g === 'C') return 'C · 风险偏高'
  if (g === 'D') return 'D · 不建议做空'
  return '暂无评级'
})

const directionText = computed(() => {
  const g = selectedToken.value?.short_grade
  if (g === 'S' || g === 'A') return '可考虑做空'
  if (g === 'B') return '观望为主'
  return '建议回避'
})

const recommendedLeverage = computed(() => selectedToken.value?.recommended_leverage ?? 5)

const fundingColorClass = computed(() => {
  const fr = selectedToken.value?.funding_rate ?? 0
  if (fr <= -0.005) return 'extreme'
  if (fr <= -0.001) return 'high'
  if (fr >= 0.005) return 'low'
  return 'medium'
})

const fundingHintText = computed(() => {
  const fr = selectedToken.value?.funding_rate ?? 0
  if (fr <= -0.005) return '空头付费给多头 — 极度拥挤'
  if (fr <= -0.001) return '空头占优,付息中'
  if (fr >= 0.005) return '多头拥挤,不适合做空'
  return '资金费率中性'
})

const crowdHintText = computed(() => {
  const c = selectedToken.value?.crowdedness_score ?? 0
  if (c > 0.7) return '空头极度拥挤,警惕轧空'
  if (c > 0.4) return '空头仓位偏高'
  if (c > 0.2) return '持仓相对平衡'
  return '空头仓位较轻'
})

const squeezeClass = computed(() => {
  const s = selectedToken.value?.squeeze_risk ?? 0
  if (s > 0.7) return 'extreme'
  if (s > 0.5) return 'high'
  if (s > 0.3) return 'medium'
  return 'low'
})

const squeezeHintText = computed(() => {
  const s = selectedToken.value?.squeeze_risk ?? 0
  if (s > 0.7) return '轧空风险高,谨慎做空'
  if (s > 0.5) return '轧空风险中等'
  if (s > 0.3) return '轧空风险偏低'
  return '轧空风险低'
})

const consecutiveDaysText = computed(() => {
  const d = selectedToken.value?.consecutive_up_days ?? 0
  if (d > 0) return `连涨 ${d} 天`
  if (d < 0) return `连跌 ${Math.abs(d)} 天`
  return '无明显趋势'
})

const marketCapText = computed(() => {
  const cap = selectedToken.value?.market_cap ?? 0
  if (cap >= 1e9) return `${(cap / 1e9).toFixed(2)}B`
  if (cap >= 1e6) return `${(cap / 1e6).toFixed(1)}M`
  if (cap >= 1e3) return `${(cap / 1e3).toFixed(1)}K`
  return `${cap.toFixed(0)}`
})

const oiUsdText = computed(() => {
  const oi = selectedToken.value?.oi_usd ?? 0
  if (oi >= 1e9) return `${(oi / 1e9).toFixed(2)}B`
  if (oi >= 1e6) return `${(oi / 1e6).toFixed(1)}M`
  if (oi >= 1e3) return `${(oi / 1e3).toFixed(1)}K`
  return `${oi.toFixed(0)}`
})

// --- API calls ---
async function fetchHotTokens() {
  htLoading.value = true
  try {
    const resp = await fetch('/api/hot_tokens/?limit=50')
    if (resp.ok) {
      const data = await resp.json()
      hotTokens.value = data || []
    }
  } catch { /* ignore */ } finally { htLoading.value = false }
}

async function fetchScannerStatus() {
  try {
    const resp = await fetch('/api/hot_tokens/status')
    if (resp.ok) {
      const data = await resp.json()
      scannerRunning.value = data.running
    }
  } catch { /* ignore */ }
}

async function startScanner() {
  try {
    await fetch('/api/hot_tokens/start', { method: 'POST' })
    await fetchScannerStatus()
  } catch { /* ignore */ }
}

async function stopScanner() {
  try {
    await fetch('/api/hot_tokens/stop', { method: 'POST' })
    await fetchScannerStatus()
  } catch { /* ignore */ }
}

async function openAnalysis(token: HotToken) {
  selectedToken.value = token
  analysisLoading.value = true
  tokenAnalysis.value = null
  try {
    const resp = await fetch(`/api/hot_tokens/${token.symbol}/analysis`)
    if (resp.ok) {
      tokenAnalysis.value = await resp.json()
    }
  } catch { /* ignore */ } finally { analysisLoading.value = false }
}

function closeAnalysis() {
  selectedToken.value = null
  tokenAnalysis.value = null
}

async function tradeHotToken(symbol: string) {
  try {
    const resp = await fetch(`/api/hot_tokens/${symbol}/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ side: 'buy' })
    })
    if (resp.ok) {
      const data = await resp.json()
      alert(`Trade result: ${JSON.stringify(data)}`)
    }
  } catch { /* ignore */ }
}

async function toggleAutoTrade() {
  try {
    if (autoTradeEnabled.value) {
      await fetch('/api/hot_tokens/auto/enable', { method: 'POST' })
    } else {
      await fetch('/api/hot_tokens/auto/disable', { method: 'POST' })
    }
  } catch { /* ignore */ }
}

async function fetchAutoTradeStatus() {
  try {
    const resp = await fetch('/api/hot_tokens/auto/status')
    if (resp.ok) {
      const data = await resp.json()
      autoTradeEnabled.value = data.enabled || false
    }
  } catch { /* ignore */ }
}

// --- WebSocket subscription for live hot-tokens updates ---
const hotTokensOff = busOn('hot_tokens_update', (data) => {
  hotTokens.value = data
})

onUnmounted(() => {
  hotTokensOff()
})

onMounted(() => {
  fetchHotTokens()
  fetchScannerStatus()
  fetchAutoTradeStatus()
})
</script>

<style scoped>
.shorts-view { padding: 24px 32px; max-width: 1400px; }

/* Header */
.sv-header { margin-bottom: 24px; }
.sv-title { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
.sv-title h1 { font-size: 24px; font-weight: 700; color: #fff; margin: 0; }
.sv-icon { font-size: 28px; }
.sv-subtitle { font-size: 13px; color: #71717a; margin: 0; }

/* Actions */
.actions-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 20px; flex-wrap: wrap; }
.btn-primary {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  background: #6366f1;
  color: #fff;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
}
.btn-primary:hover { background: #5558e6; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-outline {
  padding: 10px 20px;
  border: 1px solid #27272a;
  border-radius: 8px;
  background: transparent;
  color: #a1a1aa;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
}
.btn-outline:hover { border-color: #6366f1; color: #6366f1; }
.btn-outline:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-accent {
  padding: 6px 14px;
  border: none;
  border-radius: 6px;
  background: #6366f1;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  transition: background 0.2s;
}
.btn-accent:hover { background: #5558e6; }

/* Empty State */
.empty-state { text-align: center; padding: 80px 24px; }
.empty-icon { font-size: 48px; margin-bottom: 16px; }
.empty-title { font-size: 18px; font-weight: 600; color: #fff; margin-bottom: 8px; }
.empty-desc { font-size: 14px; color: #71717a; }

/* Hot Tokens Table */
.hot-tokens-table { overflow-x: auto; background: #111114; border: 1px solid #1e1e24; border-radius: 12px; }
.hot-tokens-table table { width: 100%; border-collapse: collapse; }
.hot-tokens-table th, .hot-tokens-table td { padding: 12px; text-align: left; border-bottom: 1px solid #1e1e24; }
.hot-tokens-table th { font-size: 12px; color: #71717a; text-transform: uppercase; background: #0a0a0f; }
.hot-tokens-table td { font-size: 14px; color: #e4e4e7; }
.hot-tokens-table tr:last-child td { border-bottom: none; }
.hot-tokens-table tr:hover td { background: #0a0a0f; }
.hot-tokens-table .btn-outline { margin-right: 4px; padding: 4px 10px; font-size: 12px; }

/* Auto Trade Toggle */
.auto-trade-toggle { display: flex; align-items: center; margin-left: auto; }
.toggle-label { display: flex; align-items: center; gap: 8px; cursor: pointer; color: #a1a1aa; font-size: 14px; }
.toggle-label input[type="checkbox"] { accent-color: #6366f1; width: 16px; height: 16px; cursor: pointer; }
.toggle-text { font-weight: 500; }
.toggle-status { font-size: 11px; padding: 2px 8px; border-radius: 12px; font-weight: 600; }
.toggle-status.on { background: rgba(34,197,94,0.15); color: #22c55e; }
.toggle-status.off { background: #27272a; color: #71717a; }

/* Sector & grade cells */
.sector-cell { color: #818cf8; font-size: 12px; }
.grade-cell {
  display: inline-block;
  width: 28px;
  height: 28px;
  line-height: 28px;
  text-align: center;
  border-radius: 6px;
  font-weight: 700;
  font-size: 14px;
}
.grade-cell.grade-s { background: rgba(34,197,94,0.18); color: #22c55e; }
.grade-cell.grade-a { background: rgba(132,204,22,0.18); color: #84cc16; }
.grade-cell.grade-b { background: rgba(245,158,11,0.18); color: #f59e0b; }
.grade-cell.grade-c { background: rgba(249,115,22,0.18); color: #f97316; }
.grade-cell.grade-d { background: rgba(239,68,68,0.18); color: #ef4444; }

/* Token Analysis Modal */
.analysis-modal {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.8);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.analysis-panel {
  background: #111114;
  border: 1px solid #1e1e24;
  border-radius: 16px;
  width: 100%;
  max-width: 1100px;
  min-width: 800px;
  min-height: 620px;
  max-height: 90vh;
  overflow-y: auto;
  padding: 28px;
}
.analysis-content { display: flex; flex-direction: column; gap: 20px; }
.analysis-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.analysis-header h2 { color: #fff; font-size: 20px; margin: 0; }
.analysis-header .btn-close {
  width: auto;
  padding: 4px 12px;
  font-size: 24px;
  background: transparent;
  border: none;
  color: #71717a;
  cursor: pointer;
}

/* Header bits */
.header-sector { font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 6px; background: rgba(99,102,241,0.15); color: #818cf8; margin-right: 12px; }
.header-left { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.header-left h2 { font-size: 22px; font-weight: 700; color: #fff; }
.header-price { font-size: 18px; font-weight: 600; color: #e4e4e7; }
.header-change.up { color: #22c55e; font-size: 14px; font-weight: 600; }
.header-change.down { color: #ef4444; font-size: 14px; font-weight: 600; }

/* Decision bar */
.decision-bar {
  display: flex;
  align-items: center;
  background: linear-gradient(135deg, #1a1a1f 0%, #15151a 100%);
  border: 1px solid #27272a;
  border-radius: 12px;
  padding: 18px 24px;
  margin-bottom: 20px;
  gap: 16px;
}
.decision-grade, .decision-direction, .decision-leverage { flex: 1; }
.grade-label, .direction-label, .leverage-label {
  font-size: 11px;
  color: #71717a;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}
.grade-value { font-size: 18px; font-weight: 700; }
.direction-value { font-size: 18px; font-weight: 600; color: #fff; }
.leverage-value { font-size: 18px; font-weight: 700; color: #f59e0b; }
.decision-divider { width: 1px; height: 40px; background: #27272a; }
.grade-s .grade-value { color: #22c55e; }
.grade-a .grade-value { color: #84cc16; }
.grade-b .grade-value { color: #f59e0b; }
.grade-c .grade-value { color: #f97316; }
.grade-d .grade-value { color: #ef4444; }

/* Metric cards */
.analysis-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
.analysis-metrics .metric-card {
  background: #1a1a1f;
  border: 1px solid #27272a;
  border-radius: 12px;
  padding: 16px;
  text-align: center;
}
.analysis-metrics .metric-card .metric-label { font-size: 12px; color: #71717a; margin-bottom: 8px; }
.analysis-metrics .metric-card .metric-value { font-size: 18px; font-weight: 700; color: #fff; }
.analysis-metrics .metric-card .metric-hint { font-size: 11px; color: #71717a; margin-top: 6px; line-height: 1.4; }
.analysis-metrics .metric-card.extreme { border-color: #ef4444; background: rgba(239,68,68,0.1); }
.analysis-metrics .metric-card.high { border-color: #f59e0b; background: rgba(245,158,11,0.1); }
.analysis-metrics .metric-card.medium { border-color: #6366f1; background: rgba(99,102,241,0.1); }
.analysis-metrics .metric-card.low { border-color: #22c55e; background: rgba(34,197,94,0.1); }

/* Charts */
.analysis-charts { margin-bottom: 20px; }
.chart-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  min-height: 320px;
}

/* Detail strip */
.detail-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  background: #0a0a0f;
  border: 1px solid #1e1e24;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
}
.strip-item { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.strip-label { font-size: 11px; color: #71717a; text-transform: uppercase; letter-spacing: 0.5px; }
.strip-value { font-size: 14px; font-weight: 600; color: #e4e4e7; word-break: break-all; }
.strip-value.profit { color: #22c55e; }
.strip-value.loss { color: #ef4444; }

/* Short reference */
.short-reference { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
.ref-card {
  background: #1a1a1f;
  border: 1px solid #27272a;
  border-radius: 10px;
  padding: 14px;
  text-align: center;
}
.ref-label { font-size: 11px; color: #71717a; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
.ref-value { font-size: 16px; font-weight: 700; color: #fff; }
.ref-value.profit { color: #22c55e; }

/* Recommendation */
.analysis-loading { text-align: center; padding: 40px; color: #71717a; }
.analysis-recommendation {
  background: #1a1a1f;
  border: 1px solid #27272a;
  border-radius: 12px;
  padding: 20px;
}
.analysis-recommendation h3 { color: #fff; font-size: 16px; margin: 0 0 12px 0; }
.analysis-recommendation p { color: #a1a1aa; font-size: 14px; line-height: 1.6; margin: 0 0 16px 0; }
.signal-badges { display: flex; flex-wrap: wrap; gap: 8px; }
.signal-badge { font-size: 12px; padding: 4px 12px; border-radius: 20px; font-weight: 600; }
.signal-badge.warning { background: rgba(245,158,11,0.15); color: #f59e0b; }
.signal-badge.danger { background: rgba(239,68,68,0.15); color: #ef4444; }
.signal-badge.alert { background: rgba(236,72,153,0.15); color: #ec4899; }
.signal-badge.success { background: rgba(34,197,94,0.15); color: #22c55e; }

@media (max-width: 768px) {
  .chart-row { grid-template-columns: 1fr; }
  .analysis-metrics { grid-template-columns: repeat(2, 1fr); }
  .shorts-view { padding: 16px; }
}
</style>
