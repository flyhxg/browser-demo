<template>
  <div class="positions">
    <h2>Positions</h2>
    <div class="actions">
      <button class="btn-refresh" @click="fetchPositions" :disabled="loading">
        {{ loading ? 'Loading...' : 'Refresh' }}
      </button>
    </div>
    <div v-if="positions.length === 0 && !loading" class="empty">
      No open positions.
    </div>
    <div class="position-list">
      <div
        v-for="pos in positions"
        :key="pos.symbol"
        class="position-card"
      >
        <div class="pos-header">
          <span class="symbol">{{ pos.symbol }}</span>
          <span class="side" :class="pos.side">{{ pos.side.toUpperCase() }}</span>
        </div>
        <div class="pos-details">
          <div class="detail">
            <label>Size</label>
            <value>{{ pos.positionAmt }}</value>
          </div>
          <div class="detail">
            <label>Entry</label>
            <value>${{ pos.entryPrice }}</value>
          </div>
          <div class="detail">
            <label>Mark</label>
            <value>${{ pos.markPrice }}</value>
          </div>
          <div class="detail">
            <label>PNL</label>
            <value :class="pos.unRealizedProfit >= 0 ? 'profit' : 'loss'">
              ${{ pos.unRealizedProfit.toFixed(2) }}
            </value>
          </div>
        </div>
        <div class="pos-actions">
          <button @click="closePosition(pos.symbol)">Close</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

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

const positions = ref<Position[]>([])
const loading = ref(false)

async function fetchPositions() {
  loading.value = true
  try {
    const resp = await fetch('/api/trading/positions')
    if (resp.ok) {
      const data = await resp.json()
      positions.value = data.positions || []
    }
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

async function closePosition(symbol: string) {
  try {
    await fetch(`/api/trading/positions/${symbol}/close`, { method: 'POST' })
    await fetchPositions()
  } catch {
    // ignore
  }
}

onMounted(fetchPositions)
</script>

<style scoped>
.positions { max-width: 900px; margin: 0 auto; padding: 32px 24px; }
h2 { margin-bottom: 24px; font-size: 24px; }
.actions { margin-bottom: 20px; }
.btn-refresh {
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  background: #6366f1;
  color: #fff;
  cursor: pointer;
  font-weight: 600;
}
.btn-refresh:disabled { opacity: 0.5; cursor: not-allowed; }
.empty { color: #71717a; padding: 40px 0; text-align: center; }
.position-list { display: flex; flex-direction: column; gap: 16px; }
.position-card {
  background: #18181b;
  border: 1px solid #27272a;
  border-radius: 12px;
  padding: 20px;
}
.pos-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.symbol { font-size: 18px; font-weight: 700; }
.side {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 20px;
  font-weight: 600;
  text-transform: uppercase;
}
.side.long { background: #1e3a2f; color: #22c55e; }
.side.short { background: #3f1818; color: #ef4444; }
.pos-details {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}
.detail { display: flex; flex-direction: column; }
.detail label { font-size: 12px; color: #71717a; margin-bottom: 4px; }
.detail value { font-size: 14px; font-weight: 600; }
.profit { color: #22c55e; }
.loss { color: #ef4444; }
.pos-actions button {
  padding: 6px 14px;
  border: 1px solid #27272a;
  border-radius: 6px;
  background: transparent;
  color: #e4e4e7;
  cursor: pointer;
  font-size: 13px;
}
.pos-actions button:hover { background: #27272a; }
</style>
