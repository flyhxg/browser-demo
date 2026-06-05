<template>
  <div class="task-card" :data-task-id="task.id">
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
        <label :for="`interval-input-${task.id}`">Interval (min):</label>
        <input
          :id="`interval-input-${task.id}`"
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
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import type { TaskStatus } from './WorkflowView.vue'

const props = defineProps<{
  task: TaskStatus
}>()

const emit = defineEmits<{
  (e: 'changed'): void
}>()

const actionPending = ref(false)
const actionError = ref<string | null>(null)
const intervalInput = ref<number>(props.task.interval_minutes)
const intervalSaving = ref(false)
const intervalResult = ref<'ok' | 'err' | null>(null)

const statusLabel = computed(() => {
  if (props.task.running) return 'Running'
  if (!props.task.enabled) return 'Disabled'
  return 'Paused'
})

const statusClass = computed(() => {
  if (props.task.running) return 'active'
  if (props.task.enabled) return 'idle'
  return 'inactive'
})

function formatTimestamp(epochSeconds: number | null): string {
  if (!epochSeconds) return '—'
  const d = new Date(epochSeconds * 1000)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

async function toggleTask() {
  if (actionPending.value) return
  actionPending.value = true
  actionError.value = null
  try {
    // When the persisted kill switch is off, "Enable & Start" needs /enable
    // (which persists the kill switch AND starts the scheduler). Once the
    // task is enabled, /toggle is the right endpoint for Pause / Resume.
    const endpoint = props.task.enabled
      ? `/api/workflow/tasks/${props.task.id}/toggle`
      : `/api/workflow/tasks/${props.task.id}/enable`
    const resp = await fetch(endpoint, { method: 'POST' })
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}))
      actionError.value = body.detail || `HTTP ${resp.status}`
    } else {
      emit('changed')
    }
  } catch (e: any) {
    actionError.value = e?.message || 'Network error'
  } finally {
    actionPending.value = false
  }
}

async function runNow() {
  if (actionPending.value) return
  actionPending.value = true
  actionError.value = null
  try {
    const resp = await fetch(`/api/workflow/tasks/${props.task.id}/run`, { method: 'POST' })
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}))
      actionError.value = body.detail || `HTTP ${resp.status}`
    } else {
      scheduleTimeout(() => emit('changed'), 500)
    }
  } catch (e: any) {
    actionError.value = e?.message || 'Network error'
  } finally {
    actionPending.value = false
  }
}

async function saveInterval() {
  if (intervalSaving.value) return
  const desired = intervalInput.value
  if (desired === props.task.interval_minutes) return
  intervalSaving.value = true
  intervalResult.value = null
  try {
    const resp = await fetch('/api/workflow/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: props.task.id, interval_minutes: desired }),
    })
    if (!resp.ok) {
      intervalResult.value = 'err'
    } else {
      intervalResult.value = 'ok'
      emit('changed')
    }
  } catch {
    intervalResult.value = 'err'
  } finally {
    intervalSaving.value = false
    scheduleTimeout(() => { intervalResult.value = null }, 2000)
  }
}

// Pending one-shot timers (runNow's 500ms refresh, saveInterval's 2s
// status clear). Tracked so onUnmounted can cancel them — otherwise they
// fire on an unmounted component and call setRef/setValue on detached state.
const pendingTimers = new Set<ReturnType<typeof setTimeout>>()

function scheduleTimeout(fn: () => void, ms: number): void {
  const id = setTimeout(() => {
    pendingTimers.delete(id)
    fn()
  }, ms)
  pendingTimers.add(id)
}

onUnmounted(() => {
  for (const id of pendingTimers) clearTimeout(id)
  pendingTimers.clear()
})
</script>

<style scoped>
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

@media (max-width: 640px) {
  .task-metrics { grid-template-columns: 1fr; }
  .task-actions { flex-direction: column; align-items: stretch; }
  .interval-control { margin-left: 0; }
}
</style>
