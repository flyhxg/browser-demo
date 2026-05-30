<template>
  <div class="settings">
    <h2>Settings</h2>

    <section>
      <h3>LLM Providers</h3>
      <LlmConfigForm
        v-for="p in apiProviders"
        :key="p.name"
        :provider="p.name"
        :label="p.label"
        :configured="p.config.configured"
        :masked-key="p.config.api_key_masked"
        :model="p.config.model"
        @save="saveProvider"
        @validate="validateProvider"
      />

      <!-- Ollama special form -->
      <div class="llm-config-form">
        <h3>Ollama</h3>
        <div class="form-row">
          <label>Server URL</label>
          <input v-model="ollamaUrl" @blur="saveOllama" />
          <button @click="checkOllama">Check</button>
          <span v-if="ollamaChecking">Checking...</span>
          <span v-if="ollamaConnected" class="ok">Connected</span>
        </div>
        <div class="form-row">
          <label>Model</label>
          <select v-model="ollamaModel" @change="saveOllama">
            <option value="" disabled>Select a model</option>
            <option v-for="m in ollamaModels" :key="m" :value="m">{{ m }}</option>
          </select>
        </div>
        <div class="form-row">
          <span v-if="config?.providers.ollama.configured" class="badge ok">Configured</span>
          <span v-else class="badge no">Not configured</span>
        </div>
      </div>
    </section>

    <section>
      <h3>Browser Mode</h3>
      <div class="form-row">
        <label>
          <input type="radio" v-model="browserMode" value="local" @change="saveBrowserMode" />
          Local Chromium
        </label>
        <label>
          <input type="radio" v-model="browserMode" value="cloud" @change="saveBrowserMode" />
          Browser Use Cloud
        </label>
      </div>
      <div v-if="browserMode === 'cloud'" class="form-row">
        <label>Cloud API Key</label>
        <input v-model="cloudApiKey" type="password" @blur="saveBrowserMode" />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import LlmConfigForm from '../components/LlmConfigForm.vue'
import type { AppConfig } from '../types'

const config = ref<AppConfig | null>(null)
const browserMode = ref('local')
const cloudApiKey = ref('')
const ollamaUrl = ref('http://localhost:11434')
const ollamaModel = ref('')
const ollamaModels = ref<string[]>([])
const ollamaChecking = ref(false)
const ollamaConnected = ref(false)

const apiProviders = computed(() => {
  if (!config.value) return []
  const providers = config.value.providers
  return [
    { name: 'openai', label: 'OpenAI', config: providers.openai },
    { name: 'anthropic', label: 'Claude', config: providers.anthropic },
    { name: 'google', label: 'Gemini', config: providers.google },
    { name: 'deepseek', label: 'DeepSeek', config: providers.deepseek },
    { name: 'groq', label: 'Groq', config: providers.groq },
  ]
})

async function loadConfig() {
  try {
    const resp = await fetch('/api/config')
    config.value = await resp.json()
    browserMode.value = config.value?.browser.mode || 'local'
    cloudApiKey.value = config.value?.browser.cloud_api_key || ''
    ollamaUrl.value = config.value?.providers.ollama.url || 'http://localhost:11434'
    ollamaModel.value = config.value?.providers.ollama.model || ''
  } catch {
    // server unreachable, keep stale config
  }
}

async function saveProvider(provider: string, data: Record<string, string>) {
  try {
    await fetch(`/api/config/${provider}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    await loadConfig()
  } catch {
    // best effort
  }
}

async function validateProvider(provider: string) {
  try {
    const resp = await fetch(`/api/config/${provider}/validate`, { method: 'POST' })
    const data = await resp.json()
    if (!data.valid) {
      alert(`Validation failed: ${data.error}`)
    } else {
      alert('Valid!')
    }
    await loadConfig()
  } catch {
    alert('Validation failed: cannot reach server')
  }
}

async function checkOllama() {
  ollamaChecking.value = true
  ollamaConnected.value = false
  try {
    const resp = await fetch(`/api/config/ollama/check?url=${encodeURIComponent(ollamaUrl.value)}`)
    const data = await resp.json()
    ollamaConnected.value = data.connected
    ollamaModels.value = data.models || []
  } catch {
    ollamaConnected.value = false
  }
  ollamaChecking.value = false
}

async function saveOllama() {
  try {
    await fetch('/api/config/ollama', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: ollamaUrl.value, model: ollamaModel.value }),
    })
    await loadConfig()
  } catch {
    // best effort
  }
}

async function saveBrowserMode() {
  try {
    await fetch('/api/config/browser-mode', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: browserMode.value, cloud_api_key: cloudApiKey.value }),
    })
  } catch {
    // best effort
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.settings { max-width: 700px; margin: 0 auto; padding: 24px; }
h2 { margin-bottom: 24px; }
section { margin-bottom: 32px; }
h3 { margin-bottom: 16px; }
.form-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
label { min-width: 100px; font-weight: 500; }
input, select {
  padding: 6px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
button {
  padding: 6px 16px;
  border: 1px solid #ccc;
  border-radius: 4px;
  cursor: pointer;
  background: #f5f5f5;
}
button:hover { background: #eee; }
.badge { font-size: 12px; padding: 2px 8px; border-radius: 4px; }
.badge.ok { background: #d4edda; color: #155724; }
.badge.no { background: #f8d7da; color: #721c24; }
.ok { color: #155724; }
.err { color: #721c24; }
</style>
