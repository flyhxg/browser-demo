# Terminal Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add queue-based command execution, persistent browser session, bidirectional WebSocket, live URL iframe, command history, and queue status display to the browser-use web demo.

**Architecture:** Backend `AgentRunner` gains an in-memory `deque` command queue. The `BrowserSession` is created once and reused across commands. WebSocket `/ws` shifts to bidirectional: frontend sends `command` messages, backend pushes `step`, `result`, `error`, `live_url`, and `queue_status` events. Frontend `ScreenshotView` renders a live URL iframe in cloud mode and base64 screenshots in local mode.

**Tech Stack:** Python asyncio, FastAPI WebSocket, browser-use `BrowserSession`, Vue 3 Composition API, TypeScript.

---

## File Map

### Backend
| File | Responsibility |
|------|-----------------|
| `backend/services/agent_runner.py` | Queue (`deque`), persistent `BrowserSession`, idle timer, `live_url` emission |
| `backend/api/ws.py` | Bidirectional WS: receive `command`/`ping`, send `live_url`/`queue_status` |
| `backend/api/tasks.py` | Unchanged (backwards compat only) |

### Frontend
| File | Responsibility |
|------|-----------------|
| `frontend/src/types/index.ts` | New `WsMessage` union types for `live_url`, `queue_status`, `command` |
| `frontend/src/composables/useWebSocket.ts` | `send(obj)`, `sendCommand(text)`, offline buffering |
| `frontend/src/composables/useAgent.ts` | Queue state: `queuePending`, `liveUrl`, `commandHistory` |
| `frontend/src/components/ScreenshotView.vue` | `liveUrl` prop → iframe (cloud) or base64 img (local) |
| `frontend/src/components/CommandHistory.vue` | NEW: scrollable result history panel |
| `frontend/src/components/TaskInput.vue` | WS `sendCommand()` instead of `POST /api/tasks` |
| `frontend/src/views/HomeView.vue` | Pass `liveUrl` to ScreenshotView, show queue count |

---

## Phase 1: Backend — WebSocket Protocol Extension

### Task 1.1: Extend ws.py to handle incoming messages

**Files:**
- Modify: `backend/api/ws.py:1-80`

**Steps:**

- [ ] **Step 1: Read the existing ws.py**

Read `backend/api/ws.py` in full.

- [ ] **Step 2: Add import for runner and json**

At the top of the file (after existing imports), add:
```python
import json
from services.agent_runner import runner
```

- [ ] **Step 3: Add command handler inside websocket_endpoint**

Inside the `try: while True:` loop (after `await ws.receive_text()`), replace the bare receive with:
```python
data = await ws.receive_text()
try:
    msg = json.loads(data)
except json.JSONDecodeError:
    # Not JSON — ignore malformed messages
    continue

msg_type = msg.get("type")
if msg_type == "command":
    command_text = msg.get("command", "")
    if command_text:
        runner.enqueue(command_text)
elif msg_type == "ping":
    await ws.send_json({"type": "pong", "data": {}})
```

- [ ] **Step 4: Commit**

```bash
git add backend/api/ws.py
git commit -m "feat(ws): handle incoming command and ping messages"
```

---

### Task 1.2: Add live_url and queue_status send helpers to ws.py

**Files:**
- Modify: `backend/api/ws.py`

**Steps:**

- [ ] **Step 1: Add helper functions after the router definition**

Add these functions after `router = APIRouter(...)`:
```python
async def send_live_url(ws: WebSocket, url: str) -> None:
    try:
        await ws.send_json({"type": "live_url", "data": {"url": url}})
    except Exception:
        pass

async def send_queue_status(ws: WebSocket, pending: int) -> None:
    try:
        await ws.send_json({"type": "queue_status", "data": {"pending": pending}})
    except Exception:
        pass
```

- [ ] **Step 2: Commit**

```bash
git add backend/api/ws.py
git commit -m "feat(ws): add send_live_url and send_queue_status helpers"
```

---

## Phase 2: Backend — AgentRunner Queue Management

### Task 2.1: Add queue state and browser session to AgentRunner

**Files:**
- Modify: `backend/services/agent_runner.py:1-100`

**Steps:**

- [ ] **Step 1: Read agent_runner.py in full**

- [ ] **Step 2: Add new imports and constants**

After the existing imports, add:
```python
from collections import deque
import asyncio
from urllib.parse import quote
```

Add to `AgentRunner.__init__`:
```python
self._command_queue: deque = deque()
self._browser_session: BrowserSession | None = None
self._queue_max_size = 50
self._idle_timer: asyncio.Task | None = None
self._idle_timeout = 5 * 60  # 5 minutes
self._ws: WebSocket | None = None  # set by ws.py via set_ws()
```

Add a new method:
```python
def set_ws(self, ws: WebSocket) -> None:
    self._ws = ws
```

- [ ] **Step 3: Add enqueue method**

```python
async def enqueue(self, command: str) -> None:
    if len(self._command_queue) >= self._queue_max_size:
        from backend.api.ws import send_queue_status
        if self._ws:
            await send_queue_status(self._ws, len(self._command_queue))
            await self._ws.send_json({
                "type": "error",
                "data": {"message": "Queue is full (max 50 commands)", "step": 0}
            })
        return

    self._command_queue.append(command)

    # Cancel any pending idle timer
    if self._idle_timer:
        self._idle_timer.cancel()
        self._idle_timer = None

    from backend.api.ws import send_queue_status
    if self._ws:
        await send_queue_status(self._ws, len(self._command_queue))

    # If nothing is running, start immediately
    if not self._running:
        asyncio.create_task(self._run_next())
```

Add `_run_next` helper:
```python
async def _run_next(self) -> None:
    if not self._command_queue:
        return
    command = self._command_queue.popleft()
    await self.run(command)
```

- [ ] **Step 4: Update run() to call _run_next in done_callback instead of nothing**

In `done_callback`, after sending result events, add:
```python
# Queue next command if available
if self._command_queue:
    asyncio.create_task(self._run_next())
else:
    # Start idle timer
    self._idle_timer = asyncio.create_task(self._idle_wait())
```

Add `_idle_wait` method:
```python
async def _idle_wait(self) -> None:
    await asyncio.sleep(self._idle_timeout)
    if self._browser_session:
        await self._browser_session.close()
        self._browser_session = None
    from backend.api.ws import send_queue_status
    if self._ws:
        await send_queue_status(self._ws, 0)
```

- [ ] **Step 5: Update cancel() to clear queue and close browser**

In `cancel()`:
```python
self._command_queue.clear()
if self._idle_timer:
    self._idle_timer.cancel()
    self._idle_timer = None
if self._browser_session:
    await self._browser_session.close()
    self._browser_session = None
```

- [ ] **Step 6: Commit**

```bash
git add backend/services/agent_runner.py
git commit -m "feat(agent_runner): add command queue, persistent browser session, idle timeout"
```

---

### Task 2.2: Emit live_url event when cloud browser starts

**Files:**
- Modify: `backend/services/agent_runner.py` (around the browser session creation in `run()`)

**Steps:**

- [ ] **Step 1: Find where BrowserSession is created in run() and emit live_url**

In `run()`, after `browser_session = BrowserSession(...)`, add emission after `session.start()` succeeds:

```python
# After await session.start() succeeds:
if browser_use_api_key:
    # Cloud mode — emit live URL
    live_url = f"https://live.browser-use.com/?wss={quote(session.cdp_url, safe='')}"
    from backend.api.ws import send_live_url
    if self._ws:
        await send_live_url(self._ws, live_url)
```

This requires `quote` from `urllib.parse`. Confirm it's already imported from Task 2.1 Step 2.

- [ ] **Step 2: Commit**

```bash
git add backend/services/agent_runner.py
git commit -m "feat(agent_runner): emit live_url event when cloud browser starts"
```

---

### Task 2.3: Reset page context before each command

**Files:**
- Modify: `backend/services/agent_runner.py` (in the `run()` method, before creating the Agent)

**Steps:**

- [ ] **Step 1: Add page reset before Agent creation**

In `run()`, after `browser_session` is created and `session.start()` is called (but before the Agent is created), add:

```python
# Reset page context before each command
try:
    cdp = await browser_session.get_or_create_cdp_session()
    await cdp.Page.navigate(url="about:blank")
except Exception as e:
    logger.warning(f"[AgentRunner] Failed to reset page context: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/agent_runner.py
git commit -m "feat(agent_runner): reset page context to about:blank before each command"
```

---

## Phase 3: Frontend — WebSocket Enhancements

### Task 3.1: Update WsMessage types

**Files:**
- Modify: `frontend/src/types/index.ts`

**Steps:**

- [ ] **Step 1: Add new interface definitions**

Add before or after existing interfaces:
```typescript
export interface LiveUrlData {
  url: string
}

export interface QueueStatusData {
  pending: number
}

export interface CommandData {
  command: string
}
```

- [ ] **Step 2: Extend WsMessage type union**

Replace the existing `WsMessage` interface:
```typescript
export interface WsMessage {
  type: 'step' | 'result' | 'error' | 'cancelled' | 'interactive' | 'live_url' | 'queue_status'
  data: StepData | ResultData | ErrorData | LiveUrlData | QueueStatusData | Record<string, never>
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): add LiveUrlData, QueueStatusData, extend WsMessage union"
```

---

### Task 3.2: Extend useWebSocket.ts with send() and sendCommand()

**Files:**
- Modify: `frontend/src/composables/useWebSocket.ts`

**Steps:**

- [ ] **Step 1: Read useWebSocket.ts in full**

- [ ] **Step 2: Add offline send buffer**

Add to the module-level state (after `let intentionalClose = false`):
```typescript
let offlineBuffer: object[] = []
```

- [ ] **Step 3: Update the `send` function**

Replace the existing `send` function (which doesn't exist yet — add it as a new export):
```typescript
function send(obj: object) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(obj))
  } else {
    offlineBuffer.push(obj)
  }
}

function sendCommand(text: string) {
  send({ type: 'command', command: text })
}
```

- [ ] **Step 4: Flush offline buffer on reconnect**

In `ws.onopen`, add after `connected.value = true`:
```typescript
while (offlineBuffer.length > 0) {
  const msg = offlineBuffer.shift()
  if (msg) ws.send(JSON.stringify(msg))
}
```

- [ ] **Step 5: Update onclose to reset buffer**

In `ws.onclose`, add after `ws = null`:
```typescript
offlineBuffer = []
```

- [ ] **Step 6: Add send and sendCommand to return value**

Update the return statement:
```typescript
return { connected, lastMessage, disconnect, send, sendCommand }
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/composables/useWebSocket.ts
git commit -m "feat(ws): add send() and sendCommand() with offline buffering"
```

---

## Phase 4: Frontend — ScreenshotView Live URL iframe

### Task 4.1: ScreenshotView iframe for cloud mode

**Files:**
- Modify: `frontend/src/components/ScreenshotView.vue`

**Steps:**

- [ ] **Step 1: Read ScreenshotView.vue in full**

- [ ] **Step 2: Add liveUrl prop**

Update the `defineProps`:
```typescript
defineProps<{ screenshot: string | null; liveUrl?: string | null }>()
```

- [ ] **Step 3: Update template to render iframe or img**

Replace the template section:
```html
<div class="screenshot-view">
  <h3>Browser View</h3>
  <div v-if="liveUrl" class="screenshot-container">
    <iframe :src="liveUrl" allow="fullscreen" />
  </div>
  <div v-else-if="screenshot" class="screenshot-container">
    <img :src="'data:image/png;base64,' + screenshot" alt="Browser screenshot" />
  </div>
  <div v-else class="empty">No screenshot yet</div>
</div>
```

- [ ] **Step 4: Add iframe style**

Add to `<style scoped>`:
```css
iframe {
  width: 100%;
  height: 500px;
  border: none;
  border-radius: 6px;
  background: #000;
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ScreenshotView.vue
git commit -m "feat(screenshot): add liveUrl iframe for cloud mode"
```

---

## Phase 5: Frontend — Queue State and Command History

### Task 5.1: Update useAgent.ts with queue state

**Files:**
- Modify: `frontend/src/composables/useAgent.ts`

**Steps:**

- [ ] **Step 1: Read useAgent.ts in full**

- [ ] **Step 2: Add new refs**

Add after existing refs:
```typescript
const queuePending = ref(0)
const liveUrl = ref<string | null>(null)
const commandHistory = ref<ResultData[]>([])
```

- [ ] **Step 3: Update reset()**

Add to `reset()`:
```typescript
queuePending.value = 0
liveUrl.value = null
commandHistory.value = []
```

- [ ] **Step 4: Update handleWsMessage()**

Add cases in `handleWsMessage()`:
```typescript
} else if (msg.type === 'live_url') {
  liveUrl.value = (msg.data as LiveUrlData).url
} else if (msg.type === 'queue_status') {
  queuePending.value = (msg.data as QueueStatusData).pending
} else if (msg.type === 'result') {
  const resultData = msg.data as ResultData
  result.value = resultData
  commandHistory.value.push(resultData)
  running.value = false
  steps.value = steps.value.map((s) => ({ ...s, status: 'done' as const }))
}
```

- [ ] **Step 5: Update return**

```typescript
return {
  steps, result, error, running, screenshot,
  queuePending, liveUrl, commandHistory,
  startTask, cancelTask, resetTask, handleWsMessage, reset,
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/composables/useAgent.ts
git commit -m "feat(useAgent): add queuePending, liveUrl, commandHistory state"
```

---

### Task 5.2: Create CommandHistory.vue

**Files:**
- Create: `frontend/src/components/CommandHistory.vue`

**Steps:**

- [ ] **Step 1: Write the component**

```vue
<template>
  <div class="command-history">
    <h3>Results</h3>
    <div class="history-list" ref="listEl">
      <div
        v-for="(item, idx) in history"
        :key="idx"
        class="history-item"
        :class="{ latest: idx === history.length - 1 }"
      >
        <div class="box-header">Command {{ idx + 1 }}</div>
        <p>{{ item.output }}</p>
        <div class="meta">
          <span>{{ item.steps }} steps</span>
          <span>{{ (item.duration_ms / 1000).toFixed(1) }}s</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import type { ResultData } from '../types'

const props = defineProps<{ history: ResultData[] }>()
const listEl = ref<HTMLElement | null>(null)

watch(() => props.history.length, async () => {
  await nextTick()
  if (listEl.value) {
    listEl.value.scrollTop = listEl.value.scrollHeight
  }
})
</script>

<style scoped>
.command-history {
  background: #18181b;
  border: 1px solid #27272a;
  border-radius: 10px;
  padding: 16px;
}
h3 { margin: 0 0 12px; font-size: 14px; color: #a1a1aa; text-transform: uppercase; letter-spacing: 0.5px; }
.history-list {
  max-height: 300px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.history-item {
  border-radius: 8px;
  padding: 12px;
  background: #0a0a0a;
  border: 1px solid #1c1c1e;
}
.history-item.latest {
  background: #052e16;
  border-color: #166534;
}
.box-header {
  font-weight: 700;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
  color: #71717a;
}
p { margin: 0; white-space: pre-wrap; font-size: 13px; line-height: 1.5; }
.meta {
  margin-top: 8px;
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #52525b;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/CommandHistory.vue
git commit -m "feat(commandHistory): add scrollable result history component"
```

---

### Task 5.3: Update TaskInput.vue to use WebSocket sendCommand

**Files:**
- Modify: `frontend/src/components/TaskInput.vue`

**Steps:**

- [ ] **Step 1: Read TaskInput.vue in full**

- [ ] **Step 2: Import useWebSocket and update submit handler**

Add import:
```typescript
import { useWebSocket } from '../composables/useWebSocket'
```

Replace the submit handler to use `sendCommand()`:
```typescript
// In the component setup, replace the emit call:
const { sendCommand } = useWebSocket()

async function onSubmit() {
  if (!task.value.trim() || props.running) return
  sendCommand(task.value.trim())
  task.value = ''
}
```

Note: `running` state is still managed by `useAgent` — WebSocket messages drive the state updates.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/TaskInput.vue
git commit -m "feat(taskInput): send commands via WebSocket sendCommand()"
```

---

### Task 5.4: Update HomeView.vue for liveUrl and queue status

**Files:**
- Modify: `frontend/src/views/HomeView.vue`

**Steps:**

- [ ] **Step 1: Read HomeView.vue in full**

- [ ] **Step 2: Destructure new useAgent returns**

Update `useAgent()` destructuring:
```typescript
const {
  steps, result, error, running, screenshot,
  queuePending, liveUrl, commandHistory,
  startTask, cancelTask, resetTask, handleWsMessage
} = useAgent()
```

- [ ] **Step 3: Pass liveUrl to ScreenshotView**

Update ScreenshotView usage:
```html
<ScreenshotView :screenshot="screenshot" :live-url="liveUrl" />
```

- [ ] **Step 4: Replace ResultDisplay with CommandHistory**

Update the component import and usage:
```html
<CommandHistory :history="commandHistory" />
```

- [ ] **Step 5: Add queue pending indicator**

Add near the TaskInput component:
```html
<div v-if="queuePending > 0" class="queue-badge">
  {{ queuePending }} pending
</div>
```

Add style:
```css
.queue-badge {
  display: inline-block;
  background: #1c1c1e;
  color: #a1a1aa;
  border-radius: 20px;
  padding: 4px 12px;
  font-size: 12px;
  margin-bottom: 8px;
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/HomeView.vue
git commit -m "feat(home): wire liveUrl, queue status, command history"
```

---

## Phase 6: Integration Test

### Task 6.1: End-to-end smoke test

**Steps:**

- [ ] **Step 1: Start the backend server**

```bash
cd backend && python -m uvicorn main:app --reload --port 8000
```

- [ ] **Step 2: Start the frontend dev server**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: Open browser to http://localhost:5173**

- [ ] **Step 4: Submit a command like "go to example.com"**

Verify:
- Live URL iframe appears (in cloud mode) OR screenshot updates (in local mode)
- Step log entries appear
- Result appears in CommandHistory panel
- Queue badge shows "0 pending"

- [ ] **Step 5: Submit a second command immediately**

Verify:
- Queue badge shows "1 pending"
- After first command completes, second executes
- Result appended to CommandHistory

- [ ] **Step 6: Verify idle timeout (optional — skip for quick test)**

Let the queue drain and wait 5 minutes. Verify browser session closes.

---

## Self-Review Checklist

**Spec coverage:**
- [ ] Command queuing → Tasks 2.1, 5.3, 5.4
- [ ] Persistent browser session → Task 2.1 (browser_session field)
- [ ] Bidirectional WS → Tasks 1.1, 1.2, 3.2
- [ ] Live URL event → Task 2.2
- [ ] Live URL iframe → Tasks 4.1, 5.4
- [ ] Command history → Tasks 5.1, 5.2, 5.4
- [ ] Queue status display → Tasks 2.1, 5.1, 5.4
- [ ] Queue capacity limit → Task 2.1 (enqueue check)
- [ ] CDP recovery → Task 2.3 (navigate to about:blank)
- [ ] Idle timeout → Task 2.1 (_idle_wait)
- [ ] Reset page context → Task 2.3
- [ ] Cancel clears queue → Task 2.1 (cancel)

**Placeholder scan:**
- [ ] No "TBD", "TODO" in any step
- [ ] All code blocks show actual code
- [ ] All file paths are exact

**Type consistency:**
- [ ] `WsMessage.type` union updated in Task 3.1 matches all handleWsMessage cases in Task 5.1
- [ ] `LiveUrlData`, `QueueStatusData` defined in Task 3.1 and used in Task 5.1
- [ ] `sendCommand()` return type matches runner.enqueue signature