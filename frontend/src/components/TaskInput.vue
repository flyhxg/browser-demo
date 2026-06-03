<template>
  <div class="task-input">
    <textarea
      v-model="task"
      placeholder="Describe the browser task you want the AI to perform..."
      rows="3"
      :disabled="running"
    ></textarea>
    <div class="controls">
      <button v-if="!running" class="btn-primary" @click="onSubmit" :disabled="!task">
        Execute
      </button>
      <button v-else class="btn-danger" @click="cancel">Cancel</button>
      <button class="btn-secondary" @click="reset">Reset</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ running: boolean }>()
const emit = defineEmits<{
  submit: [command: string]
  cancel: []
  reset: []
}>()

const task = ref('')

function onSubmit() {
  if (!task.value.trim() || props.running) return
  emit('submit', task.value.trim())
  task.value = ''
}

function cancel() {
  emit('cancel')
}

function reset() {
  emit('reset')
  task.value = ''
}
</script>

<style scoped>
.task-input { margin-bottom: 24px; }
textarea {
  width: 100%;
  padding: 14px 16px;
  border: 1px solid #27272a;
  border-radius: 10px;
  resize: vertical;
  font-size: 15px;
  font-family: inherit;
  background: #18181b;
  color: #e4e4e7;
  transition: border-color 0.15s;
  box-sizing: border-box;
}
textarea::placeholder { color: #52525b; }
textarea:focus { outline: none; border-color: #6366f1; }
.controls {
  display: flex;
  gap: 10px;
  margin-top: 12px;
  align-items: center;
}
.btn-primary {
  padding: 10px 28px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  background: #6366f1;
  color: #fff;
  font-weight: 600;
  font-size: 14px;
  transition: background 0.15s;
}
.btn-primary:hover:not(:disabled) { background: #5558e6; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-danger {
  padding: 10px 28px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  background: #dc2626;
  color: #fff;
  font-weight: 600;
  font-size: 14px;
  transition: background 0.15s;
}
.btn-secondary {
  padding: 10px 28px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  background: #6b7280;
  color: #fff;
  font-weight: 600;
  font-size: 14px;
  transition: background 0.15s;
}
.btn-secondary:hover { background: #4b5563; }
</style>