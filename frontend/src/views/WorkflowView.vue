<template>
  <div class="workflow-view">
    <!-- Header -->
    <div class="wf-header">
      <h1>Workflow</h1>
      <p class="wf-subtitle">Scheduled task control for the registered schedulers</p>
    </div>

    <!-- Loading / empty state -->
    <div v-if="loading && tasks.length === 0" class="loading-card">
      <div class="loading-spinner"></div>
      <span>Loading scheduler state…</span>
    </div>

    <div v-else-if="error" class="error-card">
      <div class="error-icon">⚠</div>
      <div class="error-title">Scheduler not reachable</div>
      <div class="error-desc">{{ error }}</div>
      <button class="btn-outline" @click="fetchStatus">Retry</button>
    </div>

    <template v-else-if="tasks.length > 0">
      <TaskCard
        v-for="task in tasks"
        :key="task.id"
        :task="task"
        @changed="fetchStatus"
      />

      <!-- Help text -->
      <div class="help-card">
        <h3>How it works</h3>
        <ul>
          <li>
            <strong>Signal Scanner</strong> runs the Binance Square signal scraper
            on the interval shown on its card.
          </li>
          <li>
            <strong>Polymarket Poller</strong> runs the top-200 cluster signal
            poller plus the position monitor (SL/TP).
          </li>
          <li>
            <strong>Pause / Run Now / Interval</strong> work the same way on both
            cards — each control binds to its own task.
          </li>
          <li>
            Each card's kill switch persists independently — flipping one
            doesn't affect the other.
          </li>
        </ul>
      </div>
    </template>

    <!-- Loaded but no schedulers registered (shouldn't happen in prod) -->
    <div v-else class="loading-card">
      <span>No schedulers registered.</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import TaskCard from './TaskCard.vue'

export interface TaskStatus {
  id: number
  name: string
  enabled: boolean
  running: boolean
  status: 'running' | 'paused' | 'idle'
  interval_minutes: number
  last_run: number | null
  next_run: number | null
}

const POLL_INTERVAL_MS = 2000

const tasks = ref<TaskStatus[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

async function fetchStatus() {
  try {
    const resp = await fetch('/api/workflow/tasks')
    if (!resp.ok) {
      error.value = `HTTP ${resp.status}: ${resp.statusText}`
      tasks.value = []
      return
    }
    const data = await resp.json()
    tasks.value = data.tasks || []
    error.value = null
  } catch (e: any) {
    error.value = e?.message || 'Network error'
  } finally {
    loading.value = false
  }
}

let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  fetchStatus()
  pollTimer = setInterval(fetchStatus, POLL_INTERVAL_MS)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.workflow-view { padding: 32px; max-width: 900px; margin: 0 auto; }
.wf-header { margin-bottom: 28px; }
.wf-header h1 { font-size: 24px; font-weight: 700; color: #fff; margin: 0 0 6px; }
.wf-subtitle { font-size: 14px; color: #71717a; margin: 0; }

/* Loading / error states */
.loading-card, .error-card {
  background: #111114;
  border: 1px solid #1e1e24;
  border-radius: 12px;
  padding: 40px;
  text-align: center;
}
.loading-card { display: flex; align-items: center; justify-content: center; gap: 12px; color: #71717a; }
.loading-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid #27272a;
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.error-icon { font-size: 32px; margin-bottom: 8px; }
.error-title { font-size: 16px; font-weight: 600; color: #fff; margin-bottom: 4px; }
.error-desc { font-size: 13px; color: #71717a; margin-bottom: 16px; }
.btn-outline {
  padding: 8px 16px;
  border: 1px solid #27272a;
  border-radius: 8px;
  background: transparent;
  color: #a1a1aa;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-outline:hover:not(:disabled) { border-color: #6366f1; color: #6366f1; }
.btn-outline:disabled { opacity: 0.4; cursor: not-allowed; }

/* Help card */
.help-card {
  background: #0a0a0f;
  border: 1px solid #1e1e24;
  border-radius: 12px;
  padding: 20px 24px;
}
.help-card h3 {
  font-size: 14px;
  font-weight: 600;
  color: #a1a1aa;
  margin: 0 0 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.help-card ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.help-card li {
  font-size: 13px;
  color: #a1a1aa;
  line-height: 1.5;
  padding-left: 16px;
  position: relative;
}
.help-card li::before {
  content: '·';
  position: absolute;
  left: 0;
  color: #6366f1;
  font-weight: 700;
  font-size: 20px;
  line-height: 1;
}
.help-card strong { color: #e4e4e7; }
</style>
