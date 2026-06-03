<template>
  <div class="interactive-panel" v-if="showPanel">
    <div class="panel-header">
      <h3>Interactive Command</h3>
      <button class="close-btn" @click="closePanel">&times;</button>
    </div>
    <div class="panel-content">
      <div v-if="commandType === 'login_qr'" class="command-section">
        <p>{{ commandMessage }}</p>
        <img v-if="screenshot" :src="screenshot" alt="QR Code" class="qr-image" />
        <div class="input-group">
          <input
            v-model="userInput"
            type="text"
            placeholder="Enter confirmation code or press confirm after scanning..."
            @keyup.enter="submitInput"
          />
          <button class="btn-primary" @click="submitInput">Confirm</button>
        </div>
      </div>
      <div v-else-if="commandType === 'input_code'" class="command-section">
        <p>{{ commandMessage }}</p>
        <div class="input-group">
          <input
            v-model="userInput"
            type="text"
            placeholder="Enter code..."
            @keyup.enter="submitInput"
          />
          <button class="btn-primary" @click="submitInput">Submit</button>
        </div>
      </div>
      <div v-else-if="commandType === 'confirm_action'" class="command-section">
        <p>{{ commandMessage }}</p>
        <div class="button-group">
          <button class="btn-primary" @click="confirmAction(true)">Confirm</button>
          <button class="btn-secondary" @click="confirmAction(false)">Cancel</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  commandType: string
  commandMessage: string
  screenshot?: string | null
}>()

const emit = defineEmits<{
  input: [data: { input: string; confirmed: boolean }]
  close: []
}>()

const showPanel = ref(false)
const userInput = ref('')

watch(() => props.commandType, (newType) => {
  if (newType) {
    showPanel.value = true
  }
})

function submitInput() {
  emit('input', { input: userInput.value, confirmed: true })
  userInput.value = ''
  showPanel.value = false
}

function confirmAction(confirmed: boolean) {
  emit('input', { input: userInput.value, confirmed })
  showPanel.value = false
}

function closePanel() {
  emit('input', { input: '', confirmed: false })
  showPanel.value = false
  emit('close')
}
</script>

<style scoped>
.interactive-panel {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: #18181b;
  border: 1px solid #27272a;
  border-radius: 12px;
  padding: 24px;
  min-width: 400px;
  max-width: 600px;
  z-index: 1000;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.panel-header h3 {
  margin: 0;
  color: #e4e4e7;
  font-size: 18px;
}

.close-btn {
  background: none;
  border: none;
  color: #71717a;
  font-size: 24px;
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  color: #e4e4e7;
}

.command-section {
  color: #e4e4e7;
}

.qr-image {
  width: 100%;
  max-width: 300px;
  height: auto;
  margin: 16px 0;
  border-radius: 8px;
}

.input-group {
  display: flex;
  gap: 10px;
  margin-top: 16px;
}

.input-group input {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid #27272a;
  border-radius: 8px;
  background: #27272a;
  color: #e4e4e7;
  font-size: 14px;
}

.input-group input:focus {
  outline: none;
  border-color: #6366f1;
}

.button-group {
  display: flex;
  gap: 10px;
  margin-top: 16px;
}

.btn-primary {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  background: #6366f1;
  color: #fff;
  font-weight: 600;
  font-size: 14px;
  transition: background 0.15s;
}

.btn-primary:hover {
  background: #5558e6;
}

.btn-secondary {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  background: #6b7280;
  color: #fff;
  font-weight: 600;
  font-size: 14px;
  transition: background 0.15s;
}

.btn-secondary:hover {
  background: #4b5563;
}
</style>
