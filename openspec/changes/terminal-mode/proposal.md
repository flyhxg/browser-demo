## Why

The current single-task model requires users to submit a task, wait for completion, then submit the next task. This doesn't support continuous, interactive workflows where users want to queue multiple commands or issue follow-up instructions after seeing results. A terminal-style interface would make the tool far more flexible and practical for real-world browsing tasks.

## What Changes

- **Queue-based command execution**: Commands are queued and executed sequentially. The browser session persists across commands.
- **WebSocket bidirectional communication**: The WebSocket channel shifts from "backend-push-only" to full-duplex: the frontend can send commands at any time, and the backend pushes live_url, step updates, results, and queue status.
- **Live URL iframe integration**: When running in cloud mode, the browser view area (`ScreenshotView`) displays the live preview URL in an iframe instead of (or alongside) the base64 screenshot.
- **Live URL event**: Backend emits a `live_url` event when a cloud browser session starts, allowing the frontend to render the live preview immediately.
- **Command history panel**: The result display transitions to a scrollable history of command outputs, showing the latest result while keeping past results accessible.
- **Queue status display**: Frontend shows pending command count so users know how many tasks are queued.

## Capabilities

### New Capabilities

- `terminal-mode`: Queue-based command execution with persistent browser session, WebSocket bidirectional messaging, live URL iframe, command history, and queue status display.
- `live-url-event`: Backend-to-frontend event carrying the cloud browser's live preview URL when a session starts.
- `command-queue`: In-memory command queue managed by `AgentRunner`. Commands are dequeued sequentially; each command resets the browser page context.

### Modified Capabilities

- `agent-runner`: Currently executes a single task and emits step/result/error events via callbacks. Will be extended to manage a command queue, persist the `BrowserSession` across commands, and emit `live_url` events. Existing single-task interface (`POST /api/tasks`) remains backwards-compatible.
- `web-ui`: Currently shows a task input form, step log, screenshot view, and result display for a single task. Will be extended with a WebSocket command sender, live URL iframe (cloud mode), command history list, and queue status indicator.

## Impact

- **Backend**: `agent_runner.py` gains queue management, persistent `BrowserSession`, and `live_url` event emission. `ws.py` gains the ability to receive commands from the frontend and forward them to the runner.
- **Frontend**: `useWebSocket.ts` gains a `sendCommand()` function. `useAgent.ts` is redesigned around queue state. `ScreenshotView.vue` conditionally renders an iframe for cloud mode. A new `CommandHistory.vue` component displays scrollable history. `HomeView.vue` adds queue status display.
- **API**: No new REST endpoints; command dispatch moves to WebSocket. Existing `/api/tasks` POST and `/api/tasks/cancel` remain for backwards compatibility but are deprecated for terminal mode.
- **WebSocket protocol**: New message types: `command` (frontend → backend), `live_url`, `queue_status` (backend → frontend).