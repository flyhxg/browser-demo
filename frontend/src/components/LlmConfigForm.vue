<template>
  <div class="llm-config-form">
    <h3>{{ label }}</h3>
    <div class="form-row">
      <label>API Key</label>
      <input
        v-model="apiKey"
        type="password"
        :placeholder="placeholder"
        @blur="save"
      />
      <span v-if="configured" class="badge ok">Configured</span>
      <span v-else class="badge no">Not configured</span>
    </div>
    <div class="form-row">
      <label>Model</label>
      <input v-model="model" @blur="save" />
    </div>
    <div class="form-row">
      <button @click="validate" :disabled="!apiKey">Validate</button>
      <span v-if="validating">Checking...</span>
      <span v-if="validResult === true" class="ok">Valid</span>
      <span v-if="validResult === false" class="err">Invalid</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const props = defineProps<{
  provider: string
  label: string
  configured: boolean
  maskedKey: string
  model: string
}>()

const emit = defineEmits<{
  save: [provider: string, data: Record<string, string>]
  validate: [provider: string]
}>()

const apiKey = ref('')
const model = ref(props.model)
const validating = ref(false)
const validResult = ref<boolean | null>(null)

const placeholder = props.configured ? props.maskedKey : 'Enter API key'

onMounted(() => {
  model.value = props.model
})

async function save() {
  const data: Record<string, string> = { model: model.value }
  if (apiKey.value) {
    data.api_key = apiKey.value
  }
  emit('save', props.provider, data)
}

async function validate() {
  // Save first
  await save()
  validating.value = true
  validResult.value = null
  emit('validate', props.provider)
}
</script>

<style scoped>
.llm-config-form {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
h3 {
  margin: 0 0 12px;
}
.form-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
label {
  min-width: 70px;
  font-weight: 500;
}
input {
  flex: 1;
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
button:disabled { opacity: 0.5; cursor: not-allowed; }
.badge { font-size: 12px; padding: 2px 8px; border-radius: 4px; }
.badge.ok { background: #d4edda; color: #155724; }
.badge.no { background: #f8d7da; color: #721c24; }
.ok { color: #155724; }
.err { color: #721c24; }
</style>
