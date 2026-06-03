<template>
  <div class="signals">
    <h2>Trading Signals</h2>
    <div class="actions">
      <button class="btn-refresh" @click="fetchSignals" :disabled="loading">
        {{ loading ? 'Loading...' : 'Refresh' }}
      </button>
    </div>
    <div v-if="signals.length === 0 && !loading" class="empty">
      No signals yet. Configure trading in Settings to start scanning.
    </div>
    <div class="signal-list">
      <div
        v-for="signal in signals"
        :key="signal.id"
        class="signal-card"
        :class="signal.status"
      >
        <div class="signal-header">
          <span class="source">{{ signal.source }}</span>
          <span class="status-badge" :class="signal.status">{{ signal.status }}</span>
        </div>
        <p class="content">{{ signal.content }}</p>
        <div class="signal-meta">
          <span>👤 {{ signal.author || 'unknown' }}</span>
          <span>❤️ {{ signal.likes }}</span>
          <span>💬 {{ signal.comments }}</span>
          <span>{{ new Date(signal.created_at).toLocaleString() }}</span>
        </div>
        <div v-if="signal.analysis" class="analysis">
          <div class="token">{{ signal.analysis.token }}</div>
          <div class="sentiment" :class="signal.analysis.sentiment">
            {{ signal.analysis.sentiment }} ({{ (signal.analysis.confidence * 100).toFixed(0) }}%)
          </div>
          <p class="reasoning">{{ signal.analysis.reasoning }}</p>
        </div>
        <div class="signal-actions">
          <button @click="validateSignal(signal.id)">Validate</button>
          <button @click="executeSignal(signal.id)">Execute</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

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

const signals = ref<Signal[]>([])
const loading = ref(false)

async function fetchSignals() {
  loading.value = true
  try {
    const resp = await fetch('/api/trading/signals')
    if (resp.ok) {
      const data = await resp.json()
      signals.value = data.signals || []
    }
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

async function validateSignal(id: number) {
  try {
    await fetch(`/api/trading/signals/${id}/validate`, { method: 'POST' })
    await fetchSignals()
  } catch {
    // ignore
  }
}

async function executeSignal(id: number) {
  try {
    await fetch('/api/trades', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ signal_id: id }),
    })
    await fetchSignals()
  } catch {
    // ignore
  }
}

onMounted(fetchSignals)
</script>

<style scoped>
.signals { max-width: 900px; margin: 0 auto; padding: 32px 24px; }
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
.signal-list { display: flex; flex-direction: column; gap: 16px; }
.signal-card {
  background: #18181b;
  border: 1px solid #27272a;
  border-radius: 12px;
  padding: 20px;
}
.signal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.source { font-size: 12px; color: #71717a; text-transform: uppercase; letter-spacing: 0.5px; }
.status-badge {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 20px;
  font-weight: 600;
}
.status-badge.pending { background: #27272a; color: #a1a1aa; }
.status-badge.analyzed { background: #1e3a2f; color: #22c55e; }
.status-badge.valid { background: #1e3a2f; color: #22c55e; }
.status-badge.executed { background: #052e16; color: #22c55e; }
.status-badge.invalid { background: #3f1818; color: #ef4444; }
.content { font-size: 14px; line-height: 1.6; margin-bottom: 12px; }
.signal-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #71717a;
  margin-bottom: 12px;
}
.analysis {
  background: #0f0f11;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
}
.token {
  display: inline-block;
  background: #6366f1;
  color: #fff;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  margin-right: 8px;
}
.sentiment { display: inline-block; font-size: 12px; font-weight: 600; }
.sentiment.bullish { color: #22c55e; }
.sentiment.bearish { color: #ef4444; }
.sentiment.neutral { color: #71717a; }
.reasoning { font-size: 13px; color: #a1a1aa; margin-top: 8px; }
.signal-actions { display: flex; gap: 8px; }
.signal-actions button {
  padding: 6px 14px;
  border: 1px solid #27272a;
  border-radius: 6px;
  background: transparent;
  color: #e4e4e7;
  cursor: pointer;
  font-size: 13px;
}
.signal-actions button:hover { background: #27272a; }
</style>
