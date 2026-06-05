<template>
  <div class="trading-view">
    <!-- Header -->
    <div class="tv-header">
      <div class="tv-title">
        <span class="tv-icon">📈</span>
        <h1>Trading Desk</h1>
      </div>
      <div class="tv-tabs">
        <button class="tv-tab" :class="{ active: activeTab === 'crypto' }" @click="activeTab = 'crypto'">
          <span class="tab-dot" :class="{ active: activeTab === 'crypto' }"></span>
          Crypto
        </button>
        <button class="tv-tab" :class="{ active: activeTab === 'prediction' }" @click="activeTab = 'prediction'">
          <span class="tab-dot" :class="{ active: activeTab === 'prediction' }"></span>
          Prediction
        </button>
      </div>
    </div>

    <!-- Crypto Panel -->
    <div v-if="activeTab === 'crypto'" class="tv-panel">
      <!-- Stats Row -->
      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-label">Open Positions</div>
          <div class="stat-value">{{ positions.length }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Total Signals</div>
          <div class="stat-value">{{ signals.length }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Pending</div>
          <div class="stat-value pending">{{ pendingCount }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Executed</div>
          <div class="stat-value executed">{{ executedCount }}</div>
        </div>
      </div>

      <!-- Sub Nav -->
      <div class="sub-nav">
        <button class="sub-btn" :class="{ active: cryptoSubTab === 'signals' }" @click="cryptoSubTab = 'signals'">
          Signals Feed
        </button>
        <button class="sub-btn" :class="{ active: cryptoSubTab === 'positions' }" @click="cryptoSubTab = 'positions'">
          Positions
        </button>
      </div>

      <!-- Signals -->
      <div v-if="cryptoSubTab === 'signals'" class="content-area">
        <div class="actions-bar">
          <button class="btn-primary" @click="fetchSignals" :disabled="loading">
            {{ loading ? 'Loading...' : 'Refresh Signals' }}
          </button>
        </div>
        <div v-if="signals.length === 0 && !loading" class="empty-state">
          <div class="empty-icon">📡</div>
          <div class="empty-title">No signals yet</div>
          <div class="empty-desc">Configure trading in Workflow to start scanning Binance Square.</div>
        </div>
        <div class="signal-list">
          <div v-for="signal in signals" :key="signal.id" class="signal-card" :class="signal.status">
            <div class="signal-top">
              <div class="signal-source">
                <span class="source-badge">{{ signal.source }}</span>
                <span class="signal-time" :title="signal.created_at">{{ formatRelativeTime(signal.created_at) }}</span>
              </div>
              <span class="status-badge" :class="signal.status">{{ signal.status }}</span>
            </div>
            <div class="signal-body">
              <p class="signal-content">"{{ signal.content }}"</p>
              <div class="signal-meta">
                <span>👤 {{ signal.author || 'unknown' }}</span>
                <span>❤️ {{ signal.likes }}</span>
                <span>💬 {{ signal.comments }}</span>
              </div>
            </div>
            <div v-if="signal.analysis" class="signal-analysis">
              <div class="analysis-header">
                <span class="analysis-token">{{ signal.analysis.token }}</span>
                <span class="analysis-sentiment" :class="signal.analysis.sentiment">
                  {{ signal.analysis.sentiment }}
                </span>
                <span class="analysis-confidence" :class="signal.analysis.sentiment">
                  {{ (signal.analysis.confidence * 100).toFixed(0) }}%
                </span>
              </div>
              <p class="analysis-reasoning">{{ signal.analysis.reasoning }}</p>
            </div>
            <div class="signal-actions">
              <button class="btn-outline" @click="validateSignal(signal.id)">Analyze</button>
              <button class="btn-accent" @click="executeSignal(signal.id)">Execute</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Positions -->
      <div v-if="cryptoSubTab === 'positions'" class="content-area">
        <div class="actions-bar">
          <button class="btn-primary" @click="fetchPositions" :disabled="posLoading">
            {{ posLoading ? 'Loading...' : 'Refresh Positions' }}
          </button>
        </div>
        <div v-if="positions.length === 0 && !posLoading" class="empty-state">
          <div class="empty-icon">📊</div>
          <div class="empty-title">No open positions</div>
          <div class="empty-desc">Execute a signal to open your first position.</div>
        </div>
        <div class="position-grid">
          <div v-for="pos in positions" :key="pos.symbol" class="position-card">
            <div class="pos-header">
              <div class="pos-symbol">{{ pos.symbol }}</div>
              <span class="pos-side" :class="pos.side">{{ pos.side.toUpperCase() }}</span>
            </div>
            <div class="pos-metrics">
              <div class="metric">
                <div class="metric-label">Size</div>
                <div class="metric-value">{{ pos.positionAmt }}</div>
              </div>
              <div class="metric">
                <div class="metric-label">Entry</div>
                <div class="metric-value">${{ pos.entryPrice }}</div>
              </div>
              <div class="metric">
                <div class="metric-label">Mark</div>
                <div class="metric-value">${{ pos.markPrice }}</div>
              </div>
              <div class="metric">
                <div class="metric-label">PNL</div>
                <div class="metric-value" :class="pos.unRealizedProfit >= 0 ? 'profit' : 'loss'">
                  ${{ pos.unRealizedProfit.toFixed(2) }}
                </div>
              </div>
            </div>
            <button class="btn-close" @click="closePosition(pos.symbol)">Close Position</button>
          </div>
        </div>
      </div>

    </div>

    <!-- Prediction Panel -->
    <div v-if="activeTab === 'prediction'" class="tv-panel">
      <!-- Status Bar -->
      <div class="status-bar">
        <div class="status-left">
          <span class="status-label">Poller:</span>
          <span class="status-dot" :class="{ running: pmStatus.running }"></span>
          <span class="status-text">{{ pmStatus.running ? 'Running' : 'Stopped' }}</span>
        </div>
        <div class="status-actions">
          <button class="btn-primary" @click="startPoller" :disabled="pmStatus.running">
            ▶ Start
          </button>
          <button class="btn-outline" @click="stopPoller" :disabled="!pmStatus.running">
            ⏹ Stop
          </button>
        </div>
      </div>

      <!-- Stats Row -->
      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-label">Open Positions</div>
          <div class="stat-value">{{ pmPositions.length }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Total Signals</div>
          <div class="stat-value">{{ pmSignals.length }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Pending</div>
          <div class="stat-value pending">{{ pmPendingCount }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Executed</div>
          <div class="stat-value executed">{{ pmExecutedCount }}</div>
        </div>
      </div>

      <!-- Sub Nav -->
      <div class="sub-nav">
        <button class="sub-btn" :class="{ active: predSubTab === 'signals' }" @click="predSubTab = 'signals'">
          🔥 Signals
        </button>
        <button class="sub-btn" :class="{ active: predSubTab === 'positions' }" @click="predSubTab = 'positions'">
          📊 Positions
        </button>
        <button class="sub-btn" :class="{ active: predSubTab === 'trades' }" @click="predSubTab = 'trades'">
          📜 Trades
        </button>
      </div>

      <!-- Signals Tab -->
      <div v-if="predSubTab === 'signals'" class="content-area">
        <div class="actions-bar">
          <button class="btn-primary" @click="fetchPmSignals" :disabled="pmLoading">
            {{ pmLoading ? 'Loading...' : 'Refresh Signals' }}
          </button>
        </div>
        <div v-if="pmSignals.length === 0 && !pmLoading" class="empty-state">
          <div class="empty-icon">📡</div>
          <div class="empty-title">No prediction signals yet</div>
          <div class="empty-desc">Start the poller to discover cluster signals from top traders.</div>
        </div>
        <div class="signal-list">
          <div v-for="sig in pmSignals" :key="sig.id" class="signal-card" :class="sig.status">
            <div class="signal-top">
              <div class="signal-source">
                <span class="source-badge">Polymarket</span>
                <span class="signal-time">{{ formatDate(sig.created_at) }}</span>
              </div>
              <span class="status-badge" :class="sig.status">{{ sig.status }}</span>
            </div>
            <div class="signal-body">
              <div class="pm-market-info">
                <span class="pm-market">{{ sig.market_slug }}</span>
                <span class="pm-outcome" :class="sig.side.toLowerCase()">{{ sig.outcome }} ({{ sig.side }})</span>
              </div>
              <div class="pm-details">
                <span>💰 ${{ sig.total_value?.toFixed(2) }} total</span>
                <span>👥 {{ sig.unique_users }} users</span>
                <span>🎯 {{ (sig.confidence * 100).toFixed(0) }}% confidence</span>
              </div>
              <div class="pm-price-info">
                <span>Avg Price: <b>{{ sig.avg_price?.toFixed(3) }}</b></span>
                <span>Net Inflow: <b :class="sig.net_inflow >= 0 ? 'profit' : 'loss'">{{ sig.net_inflow >= 0 ? '+' : '' }}${{ sig.net_inflow?.toFixed(2) }}</b></span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Positions Tab -->
      <div v-if="predSubTab === 'positions'" class="content-area">
        <div class="actions-bar">
          <button class="btn-primary" @click="fetchPmPositions" :disabled="pmPosLoading">
            {{ pmPosLoading ? 'Loading...' : 'Refresh Positions' }}
          </button>
        </div>
        <div v-if="pmPositions.length === 0 && !pmPosLoading" class="empty-state">
          <div class="empty-icon">📊</div>
          <div class="empty-title">No open positions</div>
          <div class="empty-desc">Signals with confidence >= 70% will be auto-executed.</div>
        </div>
        <div class="position-grid">
          <div v-for="pos in pmPositions" :key="pos.position_id" class="position-card">
            <div class="pos-header">
              <div class="pos-title">{{ pos.market_slug }}</div>
              <span class="pos-outcome">{{ pos.outcome }} ({{ pos.side }})</span>
            </div>
            <div class="pm-question">{{ pos.question }}</div>
            <div class="pos-metrics">
              <div class="metric">
                <div class="metric-label">Entry</div>
                <div class="metric-value">{{ pos.entry_price?.toFixed(3) }}</div>
              </div>
              <div class="metric">
                <div class="metric-label">Current</div>
                <div class="metric-value">{{ pos.current_price?.toFixed(3) }}</div>
              </div>
              <div class="metric">
                <div class="metric-label">Size</div>
                <div class="metric-value">{{ pos.size?.toFixed(2) }}</div>
              </div>
              <div class="metric">
                <div class="metric-label">P&L</div>
                <div class="metric-value" :class="pos.pnl >= 0 ? 'profit' : 'loss'">
                  {{ pos.pnl >= 0 ? '+' : '' }}${{ pos.pnl?.toFixed(2) }}
                  ({{ pos.pnl_pct >= 0 ? '+' : '' }}{{ (pos.pnl_pct * 100).toFixed(1) }}%)
                </div>
              </div>
            </div>
            <div class="pm-sl-tp">
              <span>SL: {{ pos.stop_loss_price?.toFixed(3) }}</span>
              <span>TP: {{ pos.take_profit_price?.toFixed(3) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Trades Tab -->
      <div v-if="predSubTab === 'trades'" class="content-area">
        <div class="actions-bar">
          <button class="btn-primary" @click="fetchPmTrades" :disabled="pmTradeLoading">
            {{ pmTradeLoading ? 'Loading...' : 'Refresh Trades' }}
          </button>
        </div>
        <div v-if="pmTrades.length === 0 && !pmTradeLoading" class="empty-state">
          <div class="empty-icon">📜</div>
          <div class="empty-title">No trades yet</div>
          <div class="empty-desc">Trade history will appear here after execution.</div>
        </div>
        <div class="trade-list">
          <div v-for="trade in pmTrades" :key="trade.id" class="trade-row">
            <div class="trade-market">{{ trade.market_slug }}</div>
            <div class="trade-outcome">{{ trade.outcome }}</div>
            <div class="trade-side" :class="trade.side.toLowerCase()">{{ trade.side }}</div>
            <div class="trade-price">{{ trade.price?.toFixed(3) }}</div>
            <div class="trade-size">{{ trade.size?.toFixed(2) }}</div>
            <div class="trade-status" :class="trade.status">{{ trade.status }}</div>
            <div class="trade-time">{{ formatDate(trade.created_at) }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'

// --- Crypto types & state ---
interface Signal {
  id: number
  source: string
  author: string
  content: string
  likes: number
  comments: number
  status: string
  created_at: string
  analysis?: {
    token: string
    sentiment: string
    confidence: number
    reasoning: string
  }
}

interface Position {
  symbol: string
  side: string
  positionAmt: number
  entryPrice: number
  markPrice: number
  unRealizedProfit: number
  leverage: number
  liquidationPrice: number
}

const activeTab = ref<'crypto' | 'prediction'>('crypto')
const cryptoSubTab = ref<'signals' | 'positions'>('signals')
const predSubTab = ref<'signals' | 'positions' | 'trades'>('signals')
const signals = ref<Signal[]>([])
const positions = ref<Position[]>([])
const loading = ref(false)
const posLoading = ref(false)

const pendingCount = computed(() => signals.value.filter(s => s.status === 'pending').length)
const executedCount = computed(() => signals.value.filter(s => s.status === 'executed').length)

// --- Polymarket types & state ---
interface PmSignal {
  id: number
  signal_id: string
  market_slug: string
  question: string | null
  outcome: string
  side: string
  token_id: string
  condition_id: string
  avg_price: number | null
  total_value: number | null
  unique_users: number
  confidence: number
  net_inflow: number
  status: string
  created_at: string
}

interface PmPosition {
  position_id: string
  market_slug: string
  question: string | null
  outcome: string
  side: string
  entry_price: number | null
  current_price: number | null
  size: number | null
  pnl: number | null
  pnl_pct: number | null
  stop_loss_price: number | null
  take_profit_price: number | null
  status: string
  opened_at: string
}

interface PmTrade {
  id: number
  trade_id: string
  market_slug: string
  outcome: string
  side: string
  price: number | null
  size: number | null
  status: string
  created_at: string
}

interface PmStatus {
  running: boolean
}

const pmSignals = ref<PmSignal[]>([])
const pmPositions = ref<PmPosition[]>([])
const pmTrades = ref<PmTrade[]>([])
const pmLoading = ref(false)
const pmPosLoading = ref(false)
const pmTradeLoading = ref(false)
const pmStatus = ref<PmStatus>({ running: false })

const pmPendingCount = computed(() => pmSignals.value.filter(s => s.status === 'pending').length)
const pmExecutedCount = computed(() => pmSignals.value.filter(s => s.status === 'executed').length)

function formatDate(dateStr: string): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

// Render an ISO/string timestamp as "5m ago" / "2h ago" / "3d ago",
// falling back to a short absolute date once a post is older than a week.
// New BinanceSquareScraper rows carry the post's own creation time
// (from binance_square_browser._parse_html); legacy rows carry the DB
// row insert time — both are valid `Date` inputs, so the relative
// display works for them too (it just shows the time since insert).
// Empty / unparseable values render as '' and leave the timestamp slot
// blank rather than showing "1970/1/1".
function formatRelativeTime(isoString: string | null | undefined): string {
  if (!isoString) return ''
  const post = new Date(isoString)
  if (isNaN(post.getTime())) return ''
  const now = Date.now()
  const diffMs = now - post.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  if (diffSec < 60) return 'just now'
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour}h ago`
  const diffDay = Math.floor(diffHour / 24)
  if (diffDay < 7) return `${diffDay}d ago`
  // Older than 7 days: show absolute date so the user can still tell when it was
  return post.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

// --- Crypto API ---
async function fetchSignals() {
  loading.value = true
  try {
    const resp = await fetch('/api/trading/signals')
    if (resp.ok) {
      const data = await resp.json()
      signals.value = data.signals || []
    }
  } catch { /* ignore */ } finally { loading.value = false }
}

async function validateSignal(id: number) {
  try {
    await fetch(`/api/trading/signals/${id}/validate`, { method: 'POST' })
    await fetchSignals()
  } catch { /* ignore */ }
}

async function executeSignal(id: number) {
  try {
    await fetch('/api/trades', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ signal_id: id }),
    })
    await fetchSignals()
  } catch { /* ignore */ }
}

async function fetchPositions() {
  posLoading.value = true
  try {
    const resp = await fetch('/api/trading/positions')
    if (resp.ok) {
      const data = await resp.json()
      positions.value = data.positions || []
    }
  } catch { /* ignore */ } finally { posLoading.value = false }
}

async function closePosition(symbol: string) {
  try {
    await fetch(`/api/trading/positions/${symbol}/close`, { method: 'POST' })
    await fetchPositions()
  } catch { /* ignore */ }
}

// --- Polymarket API ---
async function fetchPmStatus() {
  try {
    const resp = await fetch('/api/polymarket/status')
    if (resp.ok) {
      const data = await resp.json()
      pmStatus.value = { running: data.poller_running }
    }
  } catch { /* ignore */ }
}

async function startPoller() {
  try {
    const resp = await fetch('/api/polymarket/start', { method: 'POST' })
    if (resp.ok) {
      await fetchPmStatus()
      await fetchPmSignals()
    }
  } catch { /* ignore */ }
}

async function stopPoller() {
  try {
    const resp = await fetch('/api/polymarket/stop', { method: 'POST' })
    if (resp.ok) {
      await fetchPmStatus()
    }
  } catch { /* ignore */ }
}

async function fetchPmSignals() {
  pmLoading.value = true
  try {
    const resp = await fetch('/api/polymarket/signals')
    if (resp.ok) {
      const data = await resp.json()
      pmSignals.value = data.signals || []
    }
  } catch { /* ignore */ } finally { pmLoading.value = false }
}

async function fetchPmPositions() {
  pmPosLoading.value = true
  try {
    const resp = await fetch('/api/polymarket/positions')
    if (resp.ok) {
      const data = await resp.json()
      pmPositions.value = data.positions || []
    }
  } catch { /* ignore */ } finally { pmPosLoading.value = false }
}

async function fetchPmTrades() {
  pmTradeLoading.value = true
  try {
    const resp = await fetch('/api/polymarket/trades')
    if (resp.ok) {
      const data = await resp.json()
      pmTrades.value = data.trades || []
    }
  } catch { /* ignore */ } finally { pmTradeLoading.value = false }
}

onMounted(() => {
  fetchSignals()
  fetchPositions()
  fetchPmStatus()
  fetchPmSignals()
  fetchPmPositions()
  fetchPmTrades()
})
</script>

<style scoped>
.trading-view { padding: 24px 32px; max-width: 1200px; }

/* Header */
.tv-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; }
.tv-title { display: flex; align-items: center; gap: 12px; }
.tv-title h1 { font-size: 24px; font-weight: 700; color: #fff; margin: 0; }
.tv-icon { font-size: 28px; }
.tv-tabs { display: flex; gap: 8px; background: #111114; padding: 4px; border-radius: 10px; }
.tv-tab {
  padding: 8px 20px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #71717a;
  cursor: pointer;
  font-weight: 500;
  font-size: 14px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 8px;
}
.tv-tab:hover { color: #e4e4e7; }
.tv-tab.active { background: #6366f1; color: #fff; }
.tab-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #52525b;
}
.tab-dot.active { background: #22c55e; }

/* Stats */
.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
.stat-card {
  background: #111114;
  border: 1px solid #1e1e24;
  border-radius: 12px;
  padding: 20px 24px;
}
.stat-label { font-size: 12px; color: #71717a; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
.stat-value { font-size: 28px; font-weight: 700; color: #fff; }
.stat-value.pending { color: #f59e0b; }
.stat-value.executed { color: #22c55e; }

/* Sub Nav */
.sub-nav { display: flex; gap: 8px; margin-bottom: 20px; }
.sub-btn {
  padding: 8px 20px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #71717a;
  cursor: pointer;
  font-weight: 500;
  font-size: 14px;
  transition: all 0.2s;
}
.sub-btn:hover { color: #e4e4e7; }
.sub-btn.active { background: #1a1a1f; color: #fff; }

/* Actions */
.actions-bar { margin-bottom: 20px; }
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

/* Empty State */
.empty-state { text-align: center; padding: 80px 24px; }
.empty-icon { font-size: 48px; margin-bottom: 16px; }
.empty-title { font-size: 18px; font-weight: 600; color: #fff; margin-bottom: 8px; }
.empty-desc { font-size: 14px; color: #71717a; }

/* Signal Cards */
.signal-list { display: flex; flex-direction: column; gap: 16px; }
.signal-card {
  background: #111114;
  border: 1px solid #1e1e24;
  border-radius: 12px;
  padding: 20px;
  transition: border-color 0.2s;
}
.signal-card:hover { border-color: #27272a; }
.signal-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.signal-source { display: flex; align-items: center; gap: 12px; }
.source-badge { font-size: 11px; padding: 4px 10px; border-radius: 6px; background: #1a1a1f; color: #a1a1aa; font-weight: 600; text-transform: uppercase; }
.signal-time { font-size: 12px; color: #52525b; }
.signal-body { margin-bottom: 16px; }
.signal-content { font-size: 15px; line-height: 1.6; color: #e4e4e7; margin-bottom: 8px; font-style: italic; }
.signal-meta { display: flex; gap: 16px; font-size: 13px; color: #52525b; }
.signal-analysis {
  background: #0a0a0f;
  border: 1px solid #1e1e24;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.analysis-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.analysis-token { font-size: 14px; font-weight: 700; color: #6366f1; background: rgba(99,102,241,0.1); padding: 2px 8px; border-radius: 4px; }
.analysis-sentiment { font-size: 13px; font-weight: 600; text-transform: capitalize; }
.analysis-sentiment.bullish { color: #22c55e; }
.analysis-sentiment.bearish { color: #ef4444; }
.analysis-sentiment.neutral { color: #71717a; }
.analysis-confidence { font-size: 13px; font-weight: 600; }
.analysis-confidence.bullish { color: #22c55e; }
.analysis-confidence.bearish { color: #ef4444; }
.analysis-reasoning { font-size: 13px; color: #a1a1aa; line-height: 1.5; }
.status-badge { font-size: 11px; padding: 4px 12px; border-radius: 20px; font-weight: 600; text-transform: capitalize; }
.status-badge.pending { background: #27272a; color: #a1a1aa; }
.status-badge.analyzed { background: rgba(99,102,241,0.15); color: #6366f1; }
.status-badge.valid { background: rgba(34,197,94,0.15); color: #22c55e; }
.status-badge.executed { background: rgba(34,197,94,0.15); color: #22c55e; }
.status-badge.invalid { background: rgba(239,68,68,0.15); color: #ef4444; }
.signal-actions { display: flex; gap: 8px; }
.btn-outline {
  padding: 8px 16px;
  border: 1px solid #27272a;
  border-radius: 8px;
  background: transparent;
  color: #a1a1aa;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s;
}
.btn-outline:hover { border-color: #6366f1; color: #6366f1; }
.btn-accent {
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  background: #6366f1;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  transition: background 0.2s;
}
.btn-accent:hover { background: #5558e6; }

/* Positions */
.position-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.position-card {
  background: #111114;
  border: 1px solid #1e1e24;
  border-radius: 12px;
  padding: 20px;
}
.pos-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.pos-symbol { font-size: 18px; font-weight: 700; color: #fff; }
.pos-side { font-size: 11px; padding: 4px 10px; border-radius: 20px; font-weight: 600; text-transform: uppercase; }
.pos-side.long { background: rgba(34,197,94,0.15); color: #22c55e; }
.pos-side.short { background: rgba(239,68,68,0.15); color: #ef4444; }
.pos-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
.metric { display: flex; flex-direction: column; }
.metric-label { font-size: 11px; color: #52525b; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.metric-value { font-size: 15px; font-weight: 600; color: #e4e4e7; }
.metric-value.profit { color: #22c55e; }
.metric-value.loss { color: #ef4444; }
.btn-close {
  width: 100%;
  padding: 10px;
  border: 1px solid #27272a;
  border-radius: 8px;
  background: transparent;
  color: #a1a1aa;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s;
}
.btn-close:hover { border-color: #ef4444; color: #ef4444; }

/* Prediction specific */
.status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #111114;
  border: 1px solid #1e1e24;
  border-radius: 12px;
  padding: 16px 24px;
  margin-bottom: 24px;
}
.status-left { display: flex; align-items: center; gap: 10px; }
.status-label { font-size: 14px; color: #71717a; font-weight: 500; }
.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #52525b;
}
.status-dot.running { background: #22c55e; box-shadow: 0 0 8px rgba(34,197,94,0.4); }
.status-text { font-size: 14px; font-weight: 600; color: #fff; }
.status-actions { display: flex; gap: 10px; }

.pm-market-info { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.pm-market { font-size: 16px; font-weight: 600; color: #fff; }
.pm-outcome { font-size: 13px; padding: 3px 10px; border-radius: 6px; font-weight: 600; }
.pm-outcome.buy { background: rgba(34,197,94,0.15); color: #22c55e; }
.pm-outcome.sell { background: rgba(239,68,68,0.15); color: #ef4444; }
.pm-details { display: flex; gap: 16px; font-size: 13px; color: #71717a; margin-bottom: 8px; flex-wrap: wrap; }
.pm-price-info { display: flex; gap: 20px; font-size: 14px; color: #a1a1aa; }
.pm-price-info b { color: #fff; }

.pos-title { font-size: 16px; font-weight: 600; color: #fff; }
.pos-outcome { font-size: 12px; padding: 3px 10px; border-radius: 6px; background: #1a1a1f; color: #a1a1aa; font-weight: 500; }
.pm-question { font-size: 13px; color: #71717a; margin-bottom: 12px; line-height: 1.4; }
.pm-sl-tp { display: flex; justify-content: space-between; font-size: 12px; color: #52525b; margin-top: 12px; padding-top: 12px; border-top: 1px solid #1e1e24; }

/* Trade list */
.trade-list { display: flex; flex-direction: column; gap: 8px; }
.trade-row {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1fr 1fr 1fr 1.5fr;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #111114;
  border: 1px solid #1e1e24;
  border-radius: 8px;
  font-size: 13px;
}
.trade-market { font-weight: 600; color: #fff; }
.trade-outcome { color: #a1a1aa; }
.trade-side { font-weight: 600; text-transform: uppercase; font-size: 12px; padding: 2px 8px; border-radius: 4px; width: fit-content; }
.trade-side.buy { background: rgba(34,197,94,0.15); color: #22c55e; }
.trade-side.sell { background: rgba(239,68,68,0.15); color: #ef4444; }
.trade-price { color: #e4e4e7; }
.trade-size { color: #a1a1aa; }
.trade-status { font-size: 12px; font-weight: 500; text-transform: capitalize; }
.trade-status.pending { color: #f59e0b; }
.trade-status.filled { color: #22c55e; }
.trade-status.failed { color: #ef4444; }
.trade-time { color: #52525b; font-size: 12px; }

/* Hot Tokens */
.hot-tokens-table { overflow-x: auto; }
.hot-tokens-table table { width: 100%; border-collapse: collapse; }
.hot-tokens-table th, .hot-tokens-table td { padding: 10px; text-align: left; border-bottom: 1px solid #1e1e24; }
.hot-tokens-table th { font-size: 12px; color: #71717a; text-transform: uppercase; }
.hot-tokens-table td { font-size: 14px; color: #e4e4e7; }
.hot-tokens-table .btn-outline { margin-right: 4px; }

/* Auto Trade Toggle */
.auto-trade-toggle { display: flex; align-items: center; }
.toggle-label { display: flex; align-items: center; gap: 8px; cursor: pointer; color: #a1a1aa; font-size: 14px; }
.toggle-label input[type="checkbox"] { accent-color: #6366f1; width: 16px; height: 16px; cursor: pointer; }
.toggle-text { font-weight: 500; }
.toggle-status { font-size: 11px; padding: 2px 8px; border-radius: 12px; font-weight: 600; }
.toggle-status.on { background: rgba(34,197,94,0.15); color: #22c55e; }
.toggle-status.off { background: #27272a; color: #71717a; }

@media (max-width: 768px) {
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  .prediction-grid { grid-template-columns: 1fr; }
  .position-grid { grid-template-columns: 1fr; }
  .trading-view { padding: 16px; }
  .trade-row { grid-template-columns: 1fr; gap: 4px; }
}
</style>
