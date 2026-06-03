## Context

The current implementation accepts a single task via `POST /api/tasks`, runs it to completion, and pushes step/result/error events through a WebSocket. After `result` is sent the session ends. There is no way to send additional commands after a task completes, and there is no live preview URL in the UI.

The target experience is a terminal-style interface: the user types a command, sees live progress, gets a result, types the next command, and so on. The browser window should persist across commands (not restart between them). Cloud mode should show a live preview iframe.

## Goals / Non-Goals

**Goals:**
- Queue-based execution: multiple commands can be queued and executed sequentially
- Browser session persistence: the BrowserSession stays open between commands (faster subsequent commands)
- Bidirectional WebSocket: frontend can send commands at any time over the existing `/ws` connection
- Live URL: cloud mode shows a live preview iframe in the Browser View area
- Command history: results panel shows scrollable history of past command outputs
- Queue status: frontend shows how many commands are pending

**Non-Goals:**
- Concurrent command execution (multiple agents at the same time)
- Command context inheritance (each command resets page context, does not carry over DOM state from previous command)
- Multi-tab/browser support
- Browser state persistence across queue drain (browser closes when queue is empty and runner is idle for a configurable timeout)
- Authentication/multi-user

## Decisions

### 1. Command transport: WebSocket only (no new REST endpoint)

**Decision**: All terminal-mode commands are sent over the existing `/ws` WebSocket connection. No new REST endpoint is created for dispatching commands.

**Alternatives considered**:
- `POST /api/tasks/queue` REST endpoint. Rejected because it would require the frontend to manage two transport mechanisms (HTTP for commands, WS for events). WebSocket is already bidirectional and avoids CORS complexity.
- SSE for server-to-client events only, WebSocket for commands. Rejected as mixing two transports adds unnecessary complexity.

**Reason**: The WebSocket is already open and bidirectional. Extending the protocol to support a `command` message type is the simplest path.

### 2. Queue management: in-memory in AgentRunner

**Decision**: The command queue lives in `AgentRunner` as a `deque`. The `done_callback` automatically dequeues the next command and calls `run()` again.

**Alternatives considered**:
- Separate `CommandQueue` service class. Rejected — the queue is tightly coupled to the agent lifecycle. Keeping it inside `AgentRunner` avoids an extra abstraction layer.
- Background thread polling queue. Rejected — asyncio event loop with callbacks is already the execution model.

**Reason**: Minimal abstraction, aligns with existing `asyncio.create_task` pattern.

### 3. Browser session persistence: keep BrowserSession alive between commands

**Decision**: The `BrowserSession` instance is created once when the runner starts and stored in `self._browser_session`. It is only closed when the runner is explicitly cancelled or when an idle timeout fires after the queue drains.

**Alternatives considered**:
- Create and destroy BrowserSession per command. Rejected — cloud browser startup has significant latency (3–8 s). Keeping the session alive between commands makes subsequent commands feel instant.
- Close browser only on explicit user disconnect. Rejected — if the user closes the tab the cloud browser would stay running, consuming quota.

**Reason**: Balances cost (session stays up but is not actively running commands) and UX (near-instant subsequent commands).

### 4. Idle timeout: 5 minutes

**Decision**: After the last command in the queue completes and 5 minutes pass with no new commands, the BrowserSession is closed.

**Alternatives considered**:
- No idle timeout (keep forever). Rejected — cloud browser quota is finite.
- Aggressive timeout (30 s). Rejected — user may switch to another tab and come back within a few minutes.

**Reason**: Reasonable default for a demo app. Configurable in future.

### 5. Live URL delivery: `live_url` event on `BrowserSession.start()`

**Decision**: When `BrowserSession.start()` completes in cloud mode, the runner extracts `session.cdp_url`, constructs the live URL, and emits a `live_url` event to the frontend via WebSocket. The frontend renders this URL in an iframe inside `ScreenshotView`.

**Alternatives considered**:
- Frontend polls `GET /api/browser/live-url` after connecting. Rejected — adds a new endpoint and delays the live view.
- BrowserSession emits its own internal event that the runner listens to. Rejected — less visible in the code flow; the runner is the right place to own the emission.

**Reason**: The runner already coordinates browser session lifecycle; it is the natural place to forward the live URL.

### 6. Command isolation: each command resets page context

**Decision**: Each command runs with a fresh page context. Before running the next command, `browser_session` navigates to `about:blank` or opens a new page to clear DOM state from the previous command.

**Alternatives considered**:
- Commands share page context (click element found by previous command persists). Rejected by user preference.
- Full browser restart per command (close+reopen CDP). Rejected — latency cost is too high.

**Reason**: User explicitly chose reset per command.

### 7. Frontend result history: scrollable list with latest result visible

**Decision**: A `CommandHistory` component maintains a `ref<CommandResult[]>` array. Results are appended as commands complete. The container auto-scrolls to the bottom (latest result). Previous results remain visible by scrolling up.

**Alternatives considered**:
- One result card at a time, older results collapsed. Rejected — user wants visible history.
- Terminal-style monospace log (all output merged). Rejected — step/action information is valuable context that should be preserved per command.

**Reason**: Balances information density with usability.

## Risks / Trade-offs

- **[Cloud quota]** → Browser session persists and consumes quota even when idle. Mitigation: 5-minute idle timeout auto-closes the session.
- **[Queue memory growth]** → Unlimited queue depth could consume memory. Mitigation: cap queue at 50 commands; reject additional commands with an error message.
- **[Stale browser state]** → After a long idle period, the cloud browser's CDP connection may drop. Mitigation: detect CDP connection errors on the next command and recreate the BrowserSession automatically.
- **[WebSocket reconnect loses queue]** → If the WebSocket drops and reconnects, the in-memory queue in `AgentRunner` is preserved (server-side) but the frontend loses its view of pending commands. Mitigation: on reconnect, frontend requests `queue_status` via a `sync` message; backend responds with current queue state.
- **[Command during reconnect]** → If a command is sent while WebSocket is reconnecting, the frontend must buffer it locally and resend on reconnect. Mitigation: `useWebSocket.ts` exposes a `send()` method; if called while disconnected it queues locally and flushes on reconnect.

## Migration Plan

1. **Phase 1 — WebSocket protocol extension** (no behavior change for existing single-task users):
   - Add `live_url` and `queue_status` message types to ws.py and useWebSocket.ts
   - Frontend starts rendering iframe in ScreenshotView when `live_url` event received

2. **Phase 2 — Queue state in AgentRunner**:
   - Add `self._command_queue: deque` and `self._browser_session: BrowserSession | None`
   - Modify `run()` to check queue if no task running
   - `done_callback` dequeues and re-runs automatically

3. **Phase 3 — WebSocket command receiver**:
   - ws.py starts reading text messages and dispatching `command` messages to `runner.enqueue()`
   - Frontend replaces `POST /api/tasks` with WebSocket command sending

4. **Phase 4 — Command history + idle timeout**:
   - Add `CommandHistory.vue`
   - Add idle timeout logic to close browser after 5 min

## Open Questions

1. Should the idle timeout be configurable via the settings UI? (Defer to future iteration.)
2. What happens if a cloud browser command fails due to a dropped CDP connection — automatically retry once? (Defer to v2.)
3. Do we need a `cancel` per queue item, or only cancel-all? Answer: cancel-all only (per-item cancel deferred to v2).