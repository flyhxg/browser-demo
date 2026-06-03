<template>
  <div class="settings">
    <h2>Settings</h2>

    <section class="card">
      <h3>LLM Configuration</h3>
      <p class="desc">Connect to any OpenAI or Anthropic compatible API endpoint</p>
      <div class="form-row">
        <label>Protocol</label>
        <div class="radio-group">
          <label class="radio" :class="{ active: protocol === 'anthropic' }">
            <input type="radio" v-model="protocol" value="anthropic" />
            Anthropic
          </label>
          <label class="radio" :class="{ active: protocol === 'openai' }">
            <input type="radio" v-model="protocol" value="openai" />
            OpenAI
          </label>
        </div>
      </div>
      <div class="form-row">
        <label>API Key</label>
        <input v-model="apiKey" type="password" :placeholder="placeholder" />
        <span v-if="config?.configured" class="badge ok">OK</span>
        <span v-else class="badge no">--</span>
      </div>
      <div class="form-row">
        <label>Base URL</label>
        <input v-model="baseUrl" :placeholder="protocolPlaceholder" />
      </div>
      <div class="form-row">
        <label>Model</label>
        <input v-model="model" placeholder="model name" />
      </div>
      <div class="form-actions">
        <button class="btn-primary" @click="save">Save</button>
        <span v-if="saveResult === true" class="valid-text ok">Saved</span>
        <span v-if="saveResult === false" class="valid-text err">Save failed</span>
        <button class="btn-secondary" @click="validate" :disabled="validating">
          {{ validating ? 'Checking...' : 'Validate' }}
        </button>
        <span v-if="validResult === true" class="valid-text ok">Connection valid</span>
        <span v-if="validResult === false" class="valid-text err">Connection failed</span>
      </div>
    </section>

    <section class="card" style="margin-top: 20px;">
      <h3>Browser Configuration</h3>
      <p class="desc">Choose between local Playwright browser or browser-use cloud</p>
      <div class="form-row">
        <label>Mode</label>
        <div class="radio-group">
          <label class="radio" :class="{ active: browserMode === 'local' }">
            <input type="radio" v-model="browserMode" value="local" />
            Local
          </label>
          <label class="radio" :class="{ active: browserMode === 'cloud' }">
            <input type="radio" v-model="browserMode" value="cloud" />
            Cloud
          </label>
        </div>
      </div>
      <div v-if="browserMode === 'cloud'" class="form-row">
        <label>API Key</label>
        <input v-model="browserUseApiKey" type="password" :placeholder="browserKeyPlaceholder" />
        <span v-if="config?.browser_use_api_key_masked" class="badge ok">OK</span>
        <span v-else class="badge no">--</span>
      </div>
      <div class="form-actions">
        <button class="btn-primary" @click="saveBrowser">Save</button>
        <span v-if="browserSaveResult === true" class="valid-text ok">Saved</span>
        <span v-if="browserSaveResult === false" class="valid-text err">Save failed</span>
      </div>
    </section>

    <section class="card" style="margin-top: 20px;">
      <h3>Trading Configuration</h3>
      <p class="desc">Configure Binance API for automated trading</p>
      <div class="form-row">
        <label>API Key</label>
        <input v-model="binanceApiKey" type="password" :placeholder="binanceKeyPlaceholder" />
        <span v-if="config?.binance_api_key_masked" class="badge ok">OK</span>
        <span v-else class="badge no">--</span>
      </div>
      <div class="form-row">
        <label>Secret Key</label>
        <input v-model="binanceSecretKey" type="password" placeholder="Enter your Binance Secret Key" />
      </div>
      <div class="form-row">
        <label>Mode</label>
        <div class="radio-group">
          <label class="radio" :class="{ active: binanceMode === 'futures' }">
            <input type="radio" v-model="binanceMode" value="futures" /> Futures
          </label>
          <label class="radio" :class="{ active: binanceMode === 'spot' }">
            <input type="radio" v-model="binanceMode" value="spot" /> Spot
          </label>
        </div>
      </div>
      <div class="form-row">
        <label>Testnet</label>
        <div class="radio-group">
          <label class="radio" :class="{ active: binanceTestnet }">
            <input type="radio" v-model="binanceTestnet" :value="true" /> Yes
          </label>
          <label class="radio" :class="{ active: !binanceTestnet }">
            <input type="radio" v-model="binanceTestnet" :value="false" /> No
          </label>
        </div>
      </div>
      <div class="form-row">
        <label>Max Position</label>
        <input v-model="maxPositionSize" type="number" placeholder="100" />
      </div>
      <div class="form-row">
        <label>TP %</label>
        <input v-model="tpPercentage" type="number" step="0.1" placeholder="5" />
      </div>
      <div class="form-row">
        <label>SL %</label>
        <input v-model="slPercentage" type="number" step="0.1" placeholder="3" />
      </div>
      <div class="form-row">
        <label>Min Confidence</label>
        <input v-model="minConfidence" type="number" step="0.05" min="0" max="1" placeholder="0.7" />
      </div>
      <div class="form-row">
        <label>Scan Interval</label>
        <input v-model="scanInterval" type="number" placeholder="5" />
      </div>
      <div class="form-row">
        <label>Trading</label>
        <div class="radio-group">
          <label class="radio" :class="{ active: tradingEnabled }">
            <input type="radio" v-model="tradingEnabled" :value="true" /> On
          </label>
          <label class="radio" :class="{ active: !tradingEnabled }">
            <input type="radio" v-model="tradingEnabled" :value="false" /> Off
          </label>
        </div>
      </div>
      <div class="form-actions">
        <button class="btn-primary" @click="saveTrading">Save</button>
        <span v-if="tradingSaveResult === true" class="valid-text ok">Saved</span>
        <span v-if="tradingSaveResult === false" class="valid-text err">Save failed</span>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import type { AppConfig } from '../types'

const config = ref<AppConfig | null>(null)
const apiKey = ref('')
const baseUrl = ref('https://api.anthropic.com')
const model = ref('claude-sonnet-4-20250514')
const protocol = ref<'openai' | 'anthropic'>('anthropic')
const validating = ref(false)
const validResult = ref<boolean | null>(null)
const saveResult = ref<boolean | null>(null)
const browserMode = ref<'local' | 'cloud'>('local')
const browserUseApiKey = ref('')
const browserSaveResult = ref<boolean | null>(null)

const binanceApiKey = ref('')
const binanceSecretKey = ref('')
const binanceMode = ref<'futures' | 'spot'>('futures')
const binanceTestnet = ref(true)
const tradingEnabled = ref(false)
const maxPositionSize = ref(100)
const tpPercentage = ref(5.0)
const slPercentage = ref(3.0)
const minConfidence = ref(0.7)
const scanInterval = ref(5)
const tradingSaveResult = ref<boolean | null>(null)

const placeholder = computed(() => config.value?.configured ? config.value.api_key_masked : 'sk-...')
const browserKeyPlaceholder = computed(() => config.value?.browser_use_api_key_masked || 'browser-use-api-key')
const binanceKeyPlaceholder = computed(() => config.value?.binance_api_key_masked || 'Enter your Binance API Key')

const protocolPlaceholder = computed(() =>
  protocol.value === 'openai' ? 'https://api.openai.com/v1' : 'https://api.anthropic.com'
)

async function loadConfig() {
  try {
    const resp = await fetch('/api/config')
    config.value = await resp.json()
    baseUrl.value = config.value?.base_url || 'https://api.anthropic.com'
    model.value = config.value?.model || 'claude-sonnet-4-20250514'
    protocol.value = config.value?.protocol || 'anthropic'
    browserMode.value = config.value?.browser_mode || 'local'
    binanceMode.value = config.value?.binance_mode || 'futures'
    binanceTestnet.value = config.value?.binance_testnet !== false
    tradingEnabled.value = config.value?.trading_enabled || false
    maxPositionSize.value = config.value?.max_position_size_usd || 100
    tpPercentage.value = config.value?.tp_percentage || 5.0
    slPercentage.value = config.value?.sl_percentage || 3.0
    minConfidence.value = config.value?.min_confidence || 0.7
    scanInterval.value = config.value?.scan_interval_minutes || 5
  } catch { /* ignore */ }
}

async function save() {
  const data: Record<string, string> = {
    base_url: baseUrl.value,
    model: model.value,
    protocol: protocol.value,
  }
  if (apiKey.value) {
    data.api_key = apiKey.value
  }
  try {
    const resp = await fetch('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (resp.ok) {
      apiKey.value = ''
      await loadConfig()
      saveResult.value = true
      setTimeout(() => { saveResult.value = null }, 2000)
    } else {
      saveResult.value = false
      setTimeout(() => { saveResult.value = null }, 2000)
    }
  } catch {
    saveResult.value = false
    setTimeout(() => { saveResult.value = null }, 2000)
  }
}

async function validate() {
  await save()
  validating.value = true
  validResult.value = null
  try {
    const resp = await fetch('/api/config/validate', { method: 'POST' })
    const data = await resp.json()
    validResult.value = data.valid
  } catch {
    validResult.value = false
  }
  validating.value = false
}

async function saveBrowser() {
  const data: Record<string, string> = {
    browser_mode: browserMode.value,
  }
  data.browser_use_api_key = browserUseApiKey.value
  try {
    const resp = await fetch('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (resp.ok) {
      browserUseApiKey.value = ''
      await loadConfig()
      browserSaveResult.value = true
      setTimeout(() => { browserSaveResult.value = null }, 2000)
    } else {
      browserSaveResult.value = false
      setTimeout(() => { browserSaveResult.value = null }, 2000)
    }
  } catch {
    browserSaveResult.value = false
    setTimeout(() => { browserSaveResult.value = null }, 2000)
  }
}

async function saveTrading() {
  const data: Record<string, any> = {
    binance_mode: binanceMode.value,
    binance_testnet: binanceTestnet.value,
    trading_enabled: tradingEnabled.value,
    max_position_size_usd: maxPositionSize.value,
    tp_percentage: tpPercentage.value,
    sl_percentage: slPercentage.value,
    min_confidence: minConfidence.value,
    scan_interval_minutes: scanInterval.value,
  }
  if (binanceApiKey.value) {
    data.binance_api_key = binanceApiKey.value
  }
  if (binanceSecretKey.value) {
    data.binance_secret_key = binanceSecretKey.value
  }
  try {
    const resp = await fetch('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (resp.ok) {
      binanceApiKey.value = ''
      binanceSecretKey.value = ''
      await loadConfig()
      tradingSaveResult.value = true
      setTimeout(() => { tradingSaveResult.value = null }, 2000)
    } else {
      tradingSaveResult.value = false
      setTimeout(() => { tradingSaveResult.value = null }, 2000)
    }
  } catch {
    tradingSaveResult.value = false
    setTimeout(() => { tradingSaveResult.value = null }, 2000)
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.settings { max-width: 640px; margin: 0 auto; padding: 32px 24px; }
h2 { margin-bottom: 24px; font-size: 24px; }
.card {
  background: #18181b;
  border: 1px solid #27272a;
  border-radius: 12px;
  padding: 24px;
}
h3 { margin: 0 0 4px; font-size: 16px; }
.desc { color: #71717a; font-size: 13px; margin: 0 0 20px; }
.form-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}
label { min-width: 80px; font-weight: 500; font-size: 14px; color: #a1a1aa; }
input[type="text"], input[type="password"] {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid #27272a;
  border-radius: 8px;
  background: #0f0f11;
  color: #e4e4e7;
  font-size: 14px;
  font-family: inherit;
  transition: border-color 0.15s;
}
input::placeholder { color: #3f3f46; }
input:focus { outline: none; border-color: #6366f1; }
.radio-group {
  display: flex;
  gap: 6px;
}
.radio {
  min-width: auto !important;
  padding: 8px 18px;
  border: 1px solid #27272a;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #a1a1aa;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  gap: 6px;
}
.radio input { display: none; }
.radio.active {
  background: #6366f1;
  border-color: #6366f1;
  color: #fff;
}
.radio:hover:not(.active) { background: #27272a; }
.badge {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 4px;
  font-weight: 600;
  flex-shrink: 0;
}
.badge.ok { background: #052e16; color: #22c55e; }
.badge.no { background: #27272a; color: #52525b; }
.form-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-top: 20px;
}
.btn-primary {
  padding: 10px 24px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  background: #6366f1;
  color: #fff;
  font-weight: 600;
  font-size: 14px;
  transition: background 0.15s;
}
.btn-primary:hover { background: #5558e6; }
.btn-secondary {
  padding: 10px 24px;
  border: 1px solid #27272a;
  border-radius: 8px;
  cursor: pointer;
  background: transparent;
  color: #e4e4e7;
  font-weight: 500;
  font-size: 14px;
  transition: all 0.15s;
}
.btn-secondary:hover { background: #27272a; }
.btn-secondary:disabled { opacity: 0.4; cursor: not-allowed; }
.valid-text { font-size: 13px; font-weight: 500; }
.valid-text.ok { color: #22c55e; }
.valid-text.err { color: #ef4444; }
</style>
