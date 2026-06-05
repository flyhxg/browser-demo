<template>
  <div class="workflow-view">
    <!-- Header -->
    <div class="wf-header">
      <h1>Workflow</h1>
      <p class="wf-subtitle">Scheduled task control for the signal scanner</p>
    </div>

    <!-- Loading / empty state -->
    <div v-if="loading && !task" class="loading-card">
      <div class="loading-spinner"></div>
      <span>Loading scheduler state…</span>
    </div>

    <div v-else-if="error" class="error-card">
      <div class="error-icon">⚠</div>
      <div class="error-title">Scheduler not reachable</div>
      <div class="error-desc">{{ error }}</div>
      <button class="btn-outline" @click="fetchStatus">Retry</button>
    </div>

    <template v-else-if="task">
      <!-- Task Card -->
      <div class="task-card">
        <div class="task-header">
          <div class="task-identity">
            <span class="task-icon" :class="statusClass">⚡</span>
            <div>
              <div class="task-name">{{ task.name }}</div>
              <div class="task-id">Task #{{ task.id }}</div>
            </div>
          </div>
          <div class="task-status-badge" :class="statusClass">
            <span class="status-dot" :class="statusClass"></span>
            {{ statusLabel }}
          </div>
        </div>

        <div class="task-metrics">
          <div class="metric">
            <div class="metric-label">Interval</div>
            <div class="metric-value">
              {{ task.interval_minutes }} <span class="metric-unit">min</span>
            </div>
          </div>
          <div class="metric">
            <div class="metric-label">Last run</div>
            <div class="metric-value" :class="{ 'muted': !task.last_run }">
              {{ formatTimestamp(task.last_run) }}
            </div>
          </div>
          <div class="metric">
            <div class="metric-label">Next run</div>
            <div class="metric-value" :class="{ 'muted': !task.next_run }">
              {{ formatTimestamp(task.next_run) }}
            </div>
          </div>
        </div>

        <div class="task-actions">
          <button
            class="btn-primary"
            :disabled="actionPending"
            @click="toggleTask"
          >
            <span v-if="actionPending">Working…</span>
            <span v-else-if="task.running">⏸ Pause</span>
            <span v-else-if="task.enabled">▶ Resume</span>
            <span v-else>Enable & Start</span>
          </button>

          <button
            class="btn-accent"
            :disabled="actionPending || !task.enabled"
            :title="!task.enabled ? 'Task is disabled — enable first' : 'Run a single tick immediately'"
            @click="runNow"
          >
            ▶ Run Now
          </button>

          <div class="interval-control">
            <label for="interval-input">Interval (min):</label>
            <input
              id="interval-input"
              v-model.number="intervalInput"
              type="number"
              min="1"
              max="60"
              :disabled="intervalSaving"
            />
            <button
              class="btn-outline"
              :disabled="intervalSaving || intervalInput === task.interval_minutes"
              @click="saveInterval"
            >
              {{ intervalSaving ? 'Saving…' : 'Save' }}
            </button>
            <span v-if="intervalResult === 'ok'" class="status ok">Saved</span>
            <span v-if="intervalResult === 'err'" class="status err">Save failed</span>
          </div>
        </div>

        <div v-if="actionError" class="action-error">{{ actionError }}</div>
      </div>

      <!-- Help text -->
      <div class="help-card">
        <h3>How it works</h3>
        <ul>
          <li>
            <strong>Signal Scanner</strong> runs on the backend every N minutes
            and scrapes Binance Square for new posts.
          </li>
          <li>
            <strong>Pause</strong> stops the loop without forgetting the interval;
            the task resumes from the same point when started again.
          </li>
          <li>
            <strong>Run Now</strong> fires a single tick in the background
            (non-blocking) — useful for testing config changes without waiting.
          </li>
          <li>
            Changing the interval only affects future ticks; the current tick
            (if any) finishes first.
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

interface TaskStatus {
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

const task = ref<TaskStatus | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const actionPending = ref(false)
const actionError = ref<string | null>(null)

const intervalInput = ref<number>(5)
const intervalSaving = ref(false)
const intervalResult = ref<'ok' | 'err' | null>(null)

const statusLabel = computed(() => {
  if (!task.value) return ''
  if (task.value.running) return 'Running'
  if (!task.value.enabled) return 'Disabled'
  return 'Paused'
})

const statusClass = computed(() => {
  if (!task.value) return 'inactive'
  if (task.value.running) return 'active'
  if (task.value.enabled) return 'idle'
  return 'inactive'
})

function formatTimestamp(epochSeconds: number | null): string {
  if (!epochSeconds) return '—'
  const d = new Date(epochSeconds * 1000)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

async function fetchStatus() {
  try {
    const resp = await fetch('/api/workflow/tasks')
    if (!resp.ok) {
      error.value = `HTTP ${resp.status}: ${resp.statusText}`
      task.value = null
      return
    }
    const data = await resp.json()
    const tasks: TaskStatus[] = data.tasks || []
    error.value = null
    if (tasks.length === 0) {
      task.value = null
      return
    }
    task.value = tasks[0]
    if (intervalInput.value !== tasks[0].interval_minutes) {
      intervalInput.value = tasks[0].interval_minutes
    }
  } catch (e: any) {
    error.value = e?.message || 'Network error'
  } finally {
    loading.value = false
  }
}

async function toggleTask() {
  if (!task.value) return
  actionPending.value = true
  actionError.value = null
  try {
    const resp = await fetch(`/api/workflow/tasks/${task.value.id}/toggle`, { method: 'POST' })
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}))
      actionError.value = body.detail || `HTTP ${resp.status}`
    } else {
      await fetchStatus()
    }
  } catch (e: any) {
    actionError.value = e?.message || 'Network error'
  } finally {
    actionPending.value = false
  }
}

async function runNow() {
  if (!task.value) return
  actionPending.value = true
  actionError.value = null
  try {
    const resp = await fetch(`/api/workflow/tasks/${task.value.id}/run`, { method: 'POST' })
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}))
      actionError.value = body.detail || `HTTP ${resp.status}`
    } else {
      // Refresh after a brief moment so the UI reflects the new last_run
      setTimeout(fetchStatus, 500)
    }
  } catch (e: any) {
    actionError.value = e?.message || 'Network error'
  } finally {
    actionPending.value = false
  }
}

async function saveInterval() {
  if (!task.value) return
  if (intervalInput.value === task.value.interval_minutes) return
  intervalSaving.value = true
  intervalResult.value = null
  try {
    const resp = await fetch('/api/workflow/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ interval_minutes: intervalInput.value }),
    })
    if (!resp.ok) {
      intervalResult.value = 'err'
    } else {
      intervalResult.value = 'ok'
      await fetchStatus()
    }
  } catch {
    intervalResult.value = 'err'
  } finally {
    intervalSaving.value = false
    setTimeout(() => { intervalResult.value = null }, 2000)
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

/* Task card */
.task-card {
  background: #111114;
  border: 1px solid #1e1e24;
  border-radius: 16px;
  padding: 24px 28px;
  margin-bottom: 24px;
}
.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.task-identity { display: flex; align-items: center; gap: 14px; }
.task-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  background: #6366f1;
  color: #fff;
}
.task-icon.idle { background: rgba(99,102,241,0.15); color: #818cf8; }
.task-icon.inactive { background: #27272a; color: #71717a; }
.task-name { font-size: 17px; font-weight: 700; color: #fff; }
.task-id { font-size: 12px; color: #71717a; }
.task-status-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
}
.task-status-badge.active { background: rgba(34,197,94,0.15); color: #22c55e; }
.task-status-badge.idle { background: rgba(99,102,241,0.15); color: #818cf8; }
.task-status-badge.inactive { background: #27272a; color: #71717a; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.status-dot.active { background: #22c55e; box-shadow: 0 0 6px rgba(34,197,94,0.5); }
.status-dot.idle { background: #818cf8; }
.status-dot.inactive { background: #52525b; }

/* Metrics */
.task-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 16px;
  background: #0a0a0f;
  border: 1px solid #1e1e24;
  border-radius: 12px;
  margin-bottom: 20px;
}
.metric { text-align: center; }
.metric-label {
  font-size: 11px;
  color: #71717a;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}
.metric-value {
  font-size: 18px;
  font-weight: 700;
  color: #fff;
  font-variant-numeric: tabular-nums;
}
.metric-value.muted { color: #52525b; font-weight: 500; }
.metric-unit { font-size: 13px; color: #71717a; font-weight: 500; }

/* Actions */
.task-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
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
.btn-primary:hover:not(:disabled) { background: #5558e6; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-accent {
  padding: 10px 20px;
  border: none;
  border-radius: 10px;
  background: #22c55e;
  color: #0a0a0f;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s;
}
.btn-accent:hover:not(:disabled) { background: #16a34a; }
.btn-accent:disabled { opacity: 0.4; cursor: not-allowed; }
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

/* Interval control */
.interval-control {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  font-size: 13px;
  color: #a1a1aa;
}
.interval-control input {
  width: 70px;
  padding: 8px 10px;
  border: 1px solid #27272a;
  border-radius: 8px;
  background: #0a0a0f;
  color: #e4e4e7;
  font-size: 14px;
  text-align: center;
  outline: none;
}
.interval-control input:focus { border-color: #6366f1; }
.interval-control input:disabled { opacity: 0.5; }
.status { font-size: 12px; font-weight: 600; margin-left: 4px; }
.status.ok { color: #22c55e; }
.status.err { color: #ef4444; }

.action-error {
  margin-top: 12px;
  padding: 10px 14px;
  background: rgba(239,68,68,0.1);
  border: 1px solid #ef4444;
  border-radius: 8px;
  color: #ef4444;
  font-size: 13px;
}

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

@media (max-width: 640px) {
  .task-metrics { grid-template-columns: 1fr; }
  .task-actions { flex-direction: column; align-items: stretch; }
  .interval-control { margin-left: 0; }
}
</style>
