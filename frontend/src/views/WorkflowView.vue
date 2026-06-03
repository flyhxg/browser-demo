<template>
  <div class="workflow-page">
    <!-- Header -->
    <div class="wf-header">
      <h1>Workflow</h1>
      <p class="wf-subtitle">Visual automation builder for trading strategies</p>
    </div>

    <!-- Workflow Canvas -->
    <div class="workflow-canvas">
      <!-- Workflow Nodes -->
      <div class="workflow-nodes">
        <!-- Trigger Node -->
        <div class="wf-node trigger">
          <div class="node-icon">⚡</div>
          <div class="node-content">
            <div class="node-title">Signal Trigger</div>
            <div class="node-desc">When new signal detected</div>
          </div>
          <div class="node-status active"></div>
        </div>

        <!-- Arrow -->
        <div class="node-arrow">▼</div>

        <!-- Analysis Node -->
        <div class="wf-node">
          <div class="node-icon">🧠</div>
          <div class="node-content">
            <div class="node-title">LLM Analysis</div>
            <div class="node-desc">Sentiment & confidence scoring</div>
          </div>
          <div class="node-status active"></div>
        </div>

        <!-- Arrow -->
        <div class="node-arrow">▼</div>

        <!-- Filter Node -->
        <div class="wf-node">
          <div class="node-icon">🔍</div>
          <div class="node-content">
            <div class="node-title">Signal Filter</div>
            <div class="node-desc">Apply trading rules</div>
          </div>
          <div class="node-status active"></div>
        </div>

        <!-- Arrow -->
        <div class="node-arrow">▼</div>

        <!-- Action Node -->
        <div class="wf-node action">
          <div class="node-icon">🚀</div>
          <div class="node-content">
            <div class="node-title">Execute Trade</div>
            <div class="node-desc">Binance Futures order</div>
          </div>
          <div class="node-status" :class="tradingEnabled ? 'active' : 'inactive'"></div>
        </div>
      </div>
    </div>

    <!-- Workflow Settings Cards -->
    <div class="workflow-settings">
      <h3>Workflow Configuration</h3>
      <div class="settings-grid">
        <!-- Scan Settings -->
        <div class="setting-card">
          <div class="setting-header">
            <span class="setting-icon">📡</span>
            <div>
              <div class="setting-title">Auto Scan</div>
              <div class="setting-desc">Monitor Binance Square for signals</div>
            </div>
          </div>
          <div class="setting-controls">
            <div class="toggle-group">
              <button class="toggle-btn" :class="{ active: autoScan }" @click="autoScan = true">On</button>
              <button class="toggle-btn" :class="{ active: !autoScan }" @click="autoScan = false">Off</button>
            </div>
            <div class="input-inline">
              <span>Every</span>
              <input v-model="scanInterval" type="number" min="1" max="60" />
              <span>min</span>
            </div>
          </div>
        </div>

        <!-- Auto Execute -->
        <div class="setting-card">
          <div class="setting-header">
            <span class="setting-icon">🤖</span>
            <div>
              <div class="setting-title">Auto Execute</div>
              <div class="setting-desc">Execute trades automatically</div>
            </div>
          </div>
          <div class="setting-controls">
            <div class="toggle-group">
              <button class="toggle-btn" :class="{ active: autoExecute }" @click="autoExecute = true">On</button>
              <button class="toggle-btn" :class="{ active: !autoExecute }" @click="autoExecute = false">Off</button>
            </div>
          </div>
        </div>

        <!-- Confidence Filter -->
        <div class="setting-card">
          <div class="setting-header">
            <span class="setting-icon">🎯</span>
            <div>
              <div class="setting-title">Min Confidence</div>
              <div class="setting-desc">Signal confidence threshold</div>
            </div>
          </div>
          <div class="setting-controls">
            <input v-model="minConfidence" type="range" min="0" max="1" step="0.05" class="slider" />
            <span class="slider-value">{{ (minConfidence * 100).toFixed(0) }}%</span>
          </div>
        </div>

        <!-- Position Size -->
        <div class="setting-card">
          <div class="setting-header">
            <span class="setting-icon">💰</span>
            <div>
              <div class="setting-title">Max Position</div>
              <div class="setting-desc">Maximum position size in USD</div>
            </div>
          </div>
          <div class="setting-controls">
            <div class="input-group">
              <span class="currency">$</span>
              <input v-model="maxPositionSize" type="number" placeholder="100" />
            </div>
          </div>
        </div>

        <!-- TP / SL -->
        <div class="setting-card">
          <div class="setting-header">
            <span class="setting-icon">🛡️</span>
            <div>
              <div class="setting-title">Risk Management</div>
              <div class="setting-desc">Take Profit & Stop Loss %</div>
            </div>
          </div>
          <div class="setting-controls">
            <div class="input-inline">
              <span>TP</span>
              <input v-model="tpPercentage" type="number" step="0.1" placeholder="5" />
              <span>%</span>
            </div>
            <div class="input-inline">
              <span>SL</span>
              <input v-model="slPercentage" type="number" step="0.1" placeholder="3" />
              <span>%</span>
            </div>
          </div>
        </div>

        <!-- Trading Mode -->
        <div class="setting-card">
          <div class="setting-header">
            <span class="setting-icon">⚙️</span>
            <div>
              <div class="setting-title">Trading Mode</div>
              <div class="setting-desc">Futures or Spot</div>
            </div>
          </div>
          <div class="setting-controls">
            <div class="radio-group">
              <button class="radio-btn" :class="{ active: binanceMode === 'futures' }" @click="binanceMode = 'futures'">Futures</button>
              <button class="radio-btn" :class="{ active: binanceMode === 'spot' }" @click="binanceMode = 'spot'">Spot</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="actions-bar">
        <button class="btn-primary" @click="saveWorkflow">
          <span>💾 Save Workflow</span>
        </button>
        <button class="btn-secondary" @click="runNow">
          <span>▶ Run Now</span>
        </button>
        <span v-if="saveResult === true" class="status ok">Saved</span>
        <span v-if="saveResult === false" class="status err">Save failed</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const autoScan = ref(false)
const autoExecute = ref(false)
const scanInterval = ref(5)
const saveResult = ref<boolean | null>(null)

const binanceMode = ref<'futures' | 'spot'>('futures')
const tradingEnabled = ref(false)
const maxPositionSize = ref(100)
const tpPercentage = ref(5.0)
const slPercentage = ref(3.0)
const minConfidence = ref(0.7)

async function loadConfig() {
  try {
    const resp = await fetch('/api/config')
    const config = await resp.json()
    autoScan.value = config?.trading_enabled || false
    scanInterval.value = config?.scan_interval_minutes || 5
    binanceMode.value = config?.binance_mode || 'futures'
    tradingEnabled.value = config?.trading_enabled || false
    maxPositionSize.value = config?.max_position_size_usd || 100
    tpPercentage.value = config?.tp_percentage || 5.0
    slPercentage.value = config?.sl_percentage || 3.0
    minConfidence.value = config?.min_confidence || 0.7
  } catch { /* ignore */ }
}

async function saveWorkflow() {
  const data = {
    auto_scan: autoScan.value,
    auto_execute: autoExecute.value,
    scan_interval_minutes: scanInterval.value,
    binance_mode: binanceMode.value,
    trading_enabled: autoExecute.value,
    max_position_size_usd: maxPositionSize.value,
    tp_percentage: tpPercentage.value,
    sl_percentage: slPercentage.value,
    min_confidence: minConfidence.value,
  }
  try {
    const resp = await fetch('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    saveResult.value = resp.ok
    setTimeout(() => { saveResult.value = null }, 2000)
  } catch {
    saveResult.value = false
    setTimeout(() => { saveResult.value = null }, 2000)
  }
}

async function runNow() {
  try {
    await fetch('/api/workflow/tasks/1/run', { method: 'POST' })
  } catch { /* ignore */ }
}

onMounted(() => {
  loadConfig()
})
</script>

<style scoped>
.workflow-page { padding: 32px; max-width: 900px; margin: 0 auto; }
.wf-header { margin-bottom: 32px; }
.wf-header h1 { font-size: 24px; font-weight: 700; color: #fff; margin: 0 0 8px; }
.wf-subtitle { font-size: 14px; color: #71717a; margin: 0; }

/* Workflow Canvas */
.workflow-canvas {
  background: #111114;
  border: 1px solid #1e1e24;
  border-radius: 16px;
  padding: 32px;
  margin-bottom: 32px;
}
.workflow-nodes {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
}

/* Node */
.wf-node {
  display: flex;
  align-items: center;
  gap: 16px;
  background: #0a0a0f;
  border: 1px solid #27272a;
  border-radius: 12px;
  padding: 16px 24px;
  width: 100%;
  max-width: 400px;
  position: relative;
  transition: all 0.2s;
}
.wf-node:hover {
  border-color: #3f3f46;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}
.wf-node.trigger {
  border-color: rgba(99, 102, 241, 0.3);
  background: rgba(99, 102, 241, 0.05);
}
.wf-node.action {
  border-color: rgba(34, 197, 94, 0.3);
  background: rgba(34, 197, 94, 0.05);
}
.node-icon { font-size: 24px; }
.node-content { flex: 1; }
.node-title { font-size: 15px; font-weight: 600; color: #fff; margin-bottom: 2px; }
.node-desc { font-size: 13px; color: #71717a; }
.node-status {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.node-status.active { background: #22c55e; box-shadow: 0 0 8px rgba(34,197,94,0.4); }
.node-status.inactive { background: #52525b; }

/* Arrow */
.node-arrow {
  color: #3f3f46;
  font-size: 12px;
  padding: 8px 0;
  user-select: none;
}

/* Settings */
.workflow-settings { margin-bottom: 32px; }
.workflow-settings h3 { font-size: 18px; font-weight: 600; color: #fff; margin: 0 0 20px; }
.settings-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

/* Setting Card */
.setting-card {
  background: #111114;
  border: 1px solid #1e1e24;
  border-radius: 12px;
  padding: 20px;
  transition: border-color 0.2s;
}
.setting-card:hover { border-color: #27272a; }
.setting-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.setting-icon { font-size: 24px; }
.setting-title { font-size: 14px; font-weight: 600; color: #fff; margin-bottom: 2px; }
.setting-desc { font-size: 12px; color: #71717a; }

/* Controls */
.setting-controls { display: flex; flex-direction: column; gap: 12px; }
.toggle-group { display: flex; gap: 6px; }
.toggle-btn {
  padding: 6px 16px;
  border: 1px solid #27272a;
  border-radius: 8px;
  background: transparent;
  color: #a1a1aa;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}
.toggle-btn.active { background: #6366f1; color: #fff; border-color: #6366f1; }
.toggle-btn:hover:not(.active) { background: #1a1a1f; }

.input-inline {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #a1a1aa;
}
.input-inline input {
  width: 60px;
  padding: 6px 10px;
  border: 1px solid #27272a;
  border-radius: 6px;
  background: #0a0a0f;
  color: #e4e4e7;
  font-size: 13px;
  text-align: center;
  outline: none;
}
.input-inline input:focus { border-color: #6366f1; }

.slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: #27272a;
  outline: none;
  cursor: pointer;
}
.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #6366f1;
  cursor: pointer;
  transition: transform 0.2s;
}
.slider::-webkit-slider-thumb:hover { transform: scale(1.2); }
.slider-value { font-size: 13px; font-weight: 600; color: #6366f1; text-align: center; }

.input-group {
  display: flex;
  align-items: center;
  gap: 8px;
}
.input-group input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #27272a;
  border-radius: 8px;
  background: #0a0a0f;
  color: #e4e4e7;
  font-size: 14px;
  outline: none;
}
.input-group input:focus { border-color: #6366f1; }
.currency { font-size: 14px; color: #71717a; }

.radio-group { display: flex; gap: 6px; }
.radio-btn {
  padding: 6px 16px;
  border: 1px solid #27272a;
  border-radius: 8px;
  background: transparent;
  color: #a1a1aa;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}
.radio-btn.active { background: #6366f1; color: #fff; border-color: #6366f1; }
.radio-btn:hover:not(.active) { background: #1a1a1f; }

/* Actions */
.actions-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid #1e1e24;
}
.btn-primary {
  padding: 10px 24px;
  border: none;
  border-radius: 10px;
  background: #6366f1;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}
.btn-primary:hover { background: #5558e6; }
.btn-secondary {
  padding: 10px 24px;
  border: 1px solid #27272a;
  border-radius: 10px;
  background: transparent;
  color: #e4e4e7;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-secondary:hover { background: #1a1a1f; }
.status { font-size: 13px; font-weight: 500; }
.status.ok { color: #22c55e; }
.status.err { color: #ef4444; }

@media (max-width: 768px) {
  .settings-grid { grid-template-columns: 1fr; }
  .workflow-page { padding: 16px; }
}
</style>