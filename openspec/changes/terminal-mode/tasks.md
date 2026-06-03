## 1. Backend — WebSocket Protocol Extension

- [ ] 1.1 Add `live_url` and `queue_status` message types to `ws.py` — extend the WebSocket handler to send these event types (existing step/result/error/cancelled unchanged)
- [ ] 1.2 Handle incoming `command` WebSocket messages in `ws.py` — receive text messages, parse as JSON with `type: "command"`, forward command string to `runner.enqueue()`
- [ ] 1.3 Handle `ping` messages in `ws.py` — respond with `pong` to keep connection alive

## 2. Backend — AgentRunner Queue Management

- [ ] 2.1 Add `self._command_queue: deque` and `self._browser_session: BrowserSession | None` to `AgentRunner.__init__`
- [ ] 2.2 Add `self._queue_max_size = 50` constant
- [ ] 2.3 Add `enqueue(command: str)` method to `AgentRunner` — validates queue depth, appends to deque, emits `queue_status` event, starts run if idle
- [ ] 2.4 Modify `run()` to check queue if idle — if `not self._running` and queue not empty, dequeue the next command and call `run()` with it (use `asyncio.create_task` to avoid recursion depth issues)
- [ ] 2.5 Update `done_callback` to dequeue next command and call `run()` instead of leaving runner idle
- [ ] 2.6 Extract `cdp_url` from `BrowserSession` after `session.start()` and emit `live_url` event via WebSocket in a new `_emit_live_url()` helper
- [ ] 2.7 Add `self._idle_timer: asyncio.Task | None` and `5 * 60` second timeout — start timer on queue drain, cancel on new enqueue, close browser on timeout
- [ ] 2.8 Update `cancel()` to clear queue, cancel idle timer, and close browser session

## 3. Backend — Reset Page Context Per Command

- [ ] 3.1 Before each command runs, use CDP `Page.navigate` to navigate to `about:blank` to clear DOM state from the previous command

## 4. Frontend — WebSocket Enhancements

- [ ] 4.1 Extend `useWebSocket.ts` `send()` function — allow sending arbitrary JSON messages including `command` type; queue messages while disconnected and flush on reconnect
- [ ] 4.2 Add `sendCommand(text: string)` helper that calls `send({ type: "command", command: text })`
- [ ] 4.3 Update `WsMessage` type in `types/index.ts` to include `live_url` and `queue_status` message types

## 5. Frontend — ScreenshotView Live URL iframe

- [ ] 5.1 Extend `ScreenshotView.vue` to accept a `liveUrl: string | null` prop
- [ ] 5.2 When `liveUrl` is non-null (cloud mode), render an `<iframe>` with the live URL instead of the base64 screenshot image
- [ ] 5.3 When `liveUrl` is null (local mode), render the existing base64 screenshot

## 6. Frontend — Queue State and Command History

- [ ] 6.1 Update `useAgent.ts` to manage queue state: `queuePending: ref<number>`, `liveUrl: ref<string | null>`, `commandHistory: ref<CommandResult[]>`
- [ ] 6.2 Update `handleWsMessage()` to handle new `live_url` and `queue_status` message types
- [ ] 6.3 Rename `ResultDisplay.vue` or create new `CommandHistory.vue` — a scrollable panel that appends results and auto-scrolls to bottom
- [ ] 6.4 Update `HomeView.vue` to pass `liveUrl` to `ScreenshotView` and show queue pending count

## 7. Frontend — Command Input

- [ ] 7.1 Update `TaskInput.vue` to send commands via WebSocket `sendCommand()` instead of `POST /api/tasks`
- [ ] 7.2 Show queue status (e.g., "2 pending") near the input area

## 8. Integration Testing

- [ ] 8.1 End-to-end test: connect frontend, queue multiple commands, verify live URL iframe appears, verify commands execute sequentially, verify history accumulates
- [ ] 8.2 Verify idle timeout closes cloud browser after 5 minutes of inactivity