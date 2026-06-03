<template>
  <div class="token-selector">
    <input
      v-model="query"
      @input="onInput"
      @keydown.enter="selectToken"
      placeholder="Search token (e.g. BTC)"
      class="token-input"
    />
    <ul v-if="suggestions.length" class="suggestions">
      <li v-for="s in suggestions" :key="s.id" @click="selectSuggestion(s)">
        {{ s.name }} ({{ s.symbol.toUpperCase() }})
      </li>
    </ul>
    <div v-if="selected" class="selected">
      Selected: {{ selected.symbol.toUpperCase() }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface Token { id: string; name: string; symbol: string }

const query = ref('')
const suggestions = ref<Token[]>([])
const selected = ref<Token | null>(null)
const emit = defineEmits<{ (e: 'select', token: Token): void }>()
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function onInput() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { fetchSuggestions(query.value) }, 300)
}

async function fetchSuggestions(q: string) {
  if (q.length < 2) { suggestions.value = []; return }
  try {
    const res = await fetch(`/api/coingecko/search?query=${encodeURIComponent(q)}`)
    const data = await res.json()
    suggestions.value = data.coins?.slice(0, 5) || []
  } catch { suggestions.value = [] }
}

function selectSuggestion(token: Token) {
  selected.value = token
  query.value = token.symbol.toUpperCase()
  suggestions.value = []
  emit('select', token)
}

function selectToken() {
  if (!selected.value && query.value) {
    emit('select', { id: query.value, name: query.value, symbol: query.value })
  }
}
</script>

<style scoped>
.token-input { width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
.suggestions { list-style: none; padding: 0; margin: 4px 0; border: 1px solid #eee; }
.suggestions li { padding: 8px; cursor: pointer; }
.suggestions li:hover { background: #f5f5f5; }
</style>
