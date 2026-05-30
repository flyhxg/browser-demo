<template>
  <div class="task-input">
    <textarea
      v-model="task"
      placeholder="Describe the browser task you want the AI to perform..."
      rows="3"
      :disabled="running"
    ></textarea>
    <div class="controls">
      <select v-model="provider" :disabled="running">
        <option value="" disabled>Select model</option>
        <option
          v-for="p in configuredProviders"
          :key="p.name"
          :value="p.name"
        >
          {{ p.label }} ({{ p.model }})
        </option>
      </select>
      <button v-if="!running" @click="execute" :disabled="!task || !provider">
        Execute
      </button>
      <button v-else @click="cancel" class="cancel">Cancel</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import type { AppConfig } from '../types'

const props = defineProps<{ running: boolean }>()
const emit = defineEmits<{
  execute: [task: string, provider: string]
  cancel: []
}>()

const task = ref('')
const provider = ref('')
const config = ref<AppConfig | null>(null)

const configuredProviders = computed(() => {
  if (!config.value) return []
  const providers = config.value.providers
  const result: { name: string; label: string; model: string }[] = []
  const map: Record<string, string> = {
    openai: 'OpenAI',
    anthropic: 'Claude',
    google: 'Gemini',
    deepseek: 'DeepSeek',
    groq: 'Groq',
    ollama: 'Ollama',
  }
  for (const [key, p] of Object.entries(providers)) {
    if (p.configured) {
      result.push({ name: key, label: map[key] || key, model: p.model })
    }
  }
  return result
})

async function loadConfig() {
  const resp = await fetch('/api/config')
  config.value = await resp.json()
}

function execute() {
  if (task.value && provider.value) {
    emit('execute', task.value, provider.value)
  }
}

function cancel() {
  emit('cancel')
}

onMounted(loadConfig)
</script>

<style scoped>
.task-input { margin-bottom: 20px; }
textarea {
  width: 100%;
  padding: 10px;
  border: 1px solid #ccc;
  border-radius: 6px;
  resize: vertical;
  font-size: 14px;
  box-sizing: border-box;
}
.controls {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
select {
  padding: 8px 12px;
  border: 1px solid #ccc;
  border-radius: 4px;
  min-width: 200px;
}
button {
  padding: 8px 20px;
  border: 1px solid #ccc;
  border-radius: 4px;
  cursor: pointer;
  background: #4a9eff;
  color: white;
  font-weight: 500;
}
button:disabled { opacity: 0.5; cursor: not-allowed; }
button:hover:not(:disabled) { background: #3a8eef; }
button.cancel { background: #ff4a4a; }
button.cancel:hover { background: #ef3a3a; }
</style>
