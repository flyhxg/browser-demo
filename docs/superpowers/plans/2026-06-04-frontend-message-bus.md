# Frontend WebSocket Message Bus — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate the three places that currently dispatch WebSocket frames — `useWebSocket.handleMessage` (5 console.log branches), `useAgent.handleWsMessage` (9-branch if-else), and the two `watch(lastMessage)` blocks in `HomeView.vue` and `TradingView.vue` — into a single in-process message bus that subscribers register against. The bus is a module-level singleton with `on/off/emit/clear`; the WebSocket transport loses all type-specific branching.

**Architecture:** `useWebSocket.ts` parses incoming JSON and calls `bus.emit(msg)`. `useAgent.ts` and the views subscribe via `bus.on(type, handler)` in `onMounted` and call the returned unsubscribe in `onUnmounted`. Type safety is provided by a discriminated union `WsMessageByType` in a new `types/ws.ts` so that `bus.on('hot_tokens_update', h)` infers `h: (data: HotToken[]) => void` automatically. During migration, `useAgent.handleWsMessage` and `useWebSocket.lastMessage` are kept exported but no longer drive any reactive path; they are removed in a final cleanup task.

**Tech Stack:** Vue 3 Composition API, TypeScript, Vitest

**Prerequisite:** None. This is the foundation that `arch-refactor-trading-view-tabs` will depend on (Phase 0 of that change verifies `useMessageBus` exists).

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `frontend/src/types/ws.ts` | Create | `WsMessageType` union + `WsMessageByType` discriminated union |
| `frontend/src/types/index.ts` | Modify | Re-export `WsMessage` from `./ws`; add `InteractiveCommand`, `MessageChunkData` types |
| `frontend/src/composables/useMessageBus.ts` | Create | Module-level pub/sub: `on/off/emit/clear` |
| `frontend/src/composables/__tests__/useMessageBus.spec.ts` | Create | Bus unit tests (emit/handler, off, multiple, clear, leak) |
| `frontend/src/composables/useWebSocket.ts` | Modify | `ws.onmessage` calls `bus.emit(msg)`; remove 5-branch `handleMessage` |
| `frontend/src/composables/useAgent.ts` | Modify | Subscribe to 9 chat types via `bus.on` in `onMounted`; keep `handleWsMessage` as deprecated no-op for one task |
| `frontend/src/composables/__tests__/useAgent.spec.ts` | Create | Verify bus dispatch drives agent state correctly |
| `frontend/src/views/HomeView.vue` | Modify | Replace 2 `watch(lastMessage, …)` blocks (line 134, 165) with 5 `bus.on` calls |
| `frontend/src/views/TradingView.vue` | Modify | Replace `watch(lastMessage, …)` (line 837-841) with `bus.on('hot_tokens_update', …)` |
| `frontend/CONTEXT.md` | Modify | Add "Message Bus" seam term |

---

## Task 1: Define WsMessageType union and discriminated data shapes

**Files:**
- Create: `frontend/src/types/ws.ts`
- Modify: `frontend/src/types/index.ts`

The current `types/index.ts:67-71` has a single `WsMessage` with a 13-type union and a giant `data: StepData | ResultData | …` pipe. The bus needs to look up handlers by `type` and pass the right `data` shape into each handler. We split this into a discriminated union so TypeScript narrows correctly at the call site.

The 15 types we will support, grouped by which consumer handles them:

| Type | Consumer | Data shape (already in `types/index.ts` unless noted) |
|------|----------|--------------------------------------------------------|
| `hot_tokens_update` | `TradingView.vue` | `HotToken[]` |
| `signal:new` | `TradingView.vue` (SignalsTab) | `Signal` (new type — see Step 2) |
| `signal:analyzed` | `TradingView.vue` (SignalsTab) | `{ signal: Signal; report: TokenAnalysisReport }` (new) |
| `analysis:short` | `ShortAnalysisView.vue` | `{ stage: string; progress: number }` (new) |
| `analysis:short:complete` | `ShortAnalysisView.vue` | `{ report: TokenAnalysisReport }` (new) |
| `trade:executed` | `TradingView.vue` (PositionsTab) | `{ order_id: string; symbol: string; side: 'buy'\|'sell'; quantity: number; price: number }` (new) |
| `trade:closed` | `TradingView.vue` (PositionsTab) | `{ symbol: string; pnl: number; closed_at: string }` (new) |
| `step` | `useAgent` | `StepData` (existing) |
| `result` | `useAgent` + `HomeView.vue` (result message) | `ResultData` (existing) |
| `error` | `useAgent` | `ErrorData` (existing) |
| `cancelled` | `useAgent` | `null` |
| `live_url` | `useAgent` | `LiveUrlData` (existing) |
| `queue_status` | `useAgent` | `QueueStatusData` (existing) |
| `thinking` | `useAgent` + `HomeView.vue` | `ThinkingData` (existing) |
| `tool_call_start` | `useAgent` + `HomeView.vue` | `ToolCallStartData` (existing) |
| `tool_call_result` | `useAgent` + `HomeView.vue` | `ToolCallResultData` (existing) |
| `interactive` | `HomeView.vue` | `{ type: string; message: string; screenshot: string \| null }` (new) |
| `stream` | reserved (no current consumer) | `StreamData` (existing) |

We do **not** import from `TradingView.vue` (circular). The new types added in Step 2 below (`Signal`, `TokenAnalysisReport`, `InteractiveCommand`, `TradeExecutedData`, etc.) live in `types/index.ts`. After Step 2 runs, `arch-refactor-trading-view-tabs` will extend `HotToken` to absorb the inline definition in `TradingView.vue:573-604` — out of scope here.

- [ ] **Step 1: Add new types to `frontend/src/types/index.ts`**

Append at the end of `frontend/src/types/index.ts` (after the last existing `export interface`):

```typescript
// WebSocket chat interactive payload (used by HomeView chat UI)
export interface InteractiveCommand {
  type: string
  message: string
  screenshot: string | null
}

// WebSocket trade execution events
export interface TradeExecutedData {
  order_id: string
  symbol: string
  side: 'buy' | 'sell'
  quantity: number
  price: number
}

export interface TradeClosedData {
  symbol: string
  pnl: number
  closed_at: string
}

// WebSocket analysis:short progress events
export interface AnalysisShortProgress {
  stage: string
  progress: number
}

export interface AnalysisShortComplete {
  report: TokenAnalysisReport
}

// Minimal Signal/Report types — arch-refactor-signal-analyzer will
// produce the full Pydantic-aligned version. We declare the bare
// shape here so the discriminated union compiles.
export interface Signal {
  id: number
  source: string
  symbol: string
  content: string
  sentiment: 'bullish' | 'bearish' | 'neutral' | null
  confidence: number
  created_at: string
}

export interface TokenAnalysisReport {
  symbol: string
  sentiment: 'bullish' | 'bearish' | 'neutral'
  confidence: number
  reasoning: string
  hints?: Record<string, string>
}
```

- [ ] **Step 2: Create `frontend/src/types/ws.ts`**

```typescript
// WebSocket message types — single source of truth for which event
// types the server may broadcast. Adding a new server event means:
//   1. Add the literal to WsMessageType
//   2. Add the data shape to WsMessageByType
//   3. Subscribe via bus.on(<type>, handler) in the relevant component

import type {
  HotToken,
  Signal,
  TokenAnalysisReport,
  StepData,
  ResultData,
  ErrorData,
  LiveUrlData,
  QueueStatusData,
  ThinkingData,
  ToolCallStartData,
  ToolCallResultData,
  StreamData,
  InteractiveCommand,
  TradeExecutedData,
  TradeClosedData,
  AnalysisShortProgress,
  AnalysisShortComplete,
} from './index'

export type WsMessageType =
  | 'hot_tokens_update'
  | 'signal:new'
  | 'signal:analyzed'
  | 'analysis:short'
  | 'analysis:short:complete'
  | 'trade:executed'
  | 'trade:closed'
  | 'step'
  | 'result'
  | 'error'
  | 'cancelled'
  | 'live_url'
  | 'queue_status'
  | 'thinking'
  | 'tool_call_start'
  | 'tool_call_result'
  | 'interactive'
  | 'stream'

// Discriminated union — when a handler subscribes to a given type,
// TypeScript narrows `data` to the right shape automatically.
export interface WsMessageByType {
  'hot_tokens_update': HotToken[]
  'signal:new': Signal
  'signal:analyzed': { signal: Signal; report: TokenAnalysisReport }
  'analysis:short': AnalysisShortProgress
  'analysis:short:complete': AnalysisShortComplete
  'trade:executed': TradeExecutedData
  'trade:closed': TradeClosedData
  'step': StepData
  'result': ResultData
  'error': ErrorData
  'cancelled': null
  'live_url': LiveUrlData
  'queue_status': QueueStatusData
  'thinking': ThinkingData
  'tool_call_start': ToolCallStartData
  'tool_call_result': ToolCallResultData
  'interactive': InteractiveCommand
  'stream': StreamData
}

export interface WsMessage<T extends WsMessageType = WsMessageType> {
  type: T
  data: WsMessageByType[T]
  timestamp?: string
}
```

- [ ] **Step 3: Re-export `WsMessage` from `types/index.ts`**

In `frontend/src/types/index.ts`, add at the end (or replace the existing `WsMessage` interface):

```typescript
// Re-export for convenience — components can keep importing from
// './types' as before. The canonical definition lives in ./ws.
export type { WsMessage, WsMessageType, WsMessageByType } from './ws'
```

Now remove the old `WsMessage` interface (line 67-71) from `types/index.ts` — it has been replaced by the `./ws` re-export.

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: no errors. If the existing `useWebSocket.ts:2` import (`import type { WsMessage } from '../types'`) still resolves, the re-export is wired correctly.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/ws.ts frontend/src/types/index.ts
git commit -m "feat(ws): define WsMessageType union and WsMessageByType discriminated shape"
```

---

## Task 2: TDD — write bus tests, then implement `useMessageBus`

**Files:**
- Create: `frontend/src/composables/__tests__/useMessageBus.spec.ts`
- Create: `frontend/src/composables/useMessageBus.ts`

The bus is a pure pub/sub (no Vue reactivity). Tests are deterministic and synchronous. We follow vitest conventions from `frontend/src/stores/__tests__/analysis.spec.ts`.

- [ ] **Step 1: Write the failing test file**

Create `frontend/src/composables/__tests__/useMessageBus.spec.ts`:

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { on, off, emit, clear, _handlerCount } from '../useMessageBus'

describe('useMessageBus', () => {
  beforeEach(() => {
    clear()
  })

  it('emit invokes a registered handler with the data payload', () => {
    const handler = vi.fn()
    on('hot_tokens_update', handler)
    const tokens = [{ symbol: 'BTCUSDT', price: 50000 }]
    emit({ type: 'hot_tokens_update', data: tokens })
    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler).toHaveBeenCalledWith(tokens)
  })

  it('emit with no registered handlers is a no-op (does not throw)', () => {
    expect(() => emit({ type: 'hot_tokens_update', data: [] })).not.toThrow()
  })

  it('off unsubscribes a handler so it no longer fires', () => {
    const handler = vi.fn()
    const unsubscribe = on('hot_tokens_update', handler)
    emit({ type: 'hot_tokens_update', data: [] })
    expect(handler).toHaveBeenCalledTimes(1)
    unsubscribe()
    emit({ type: 'hot_tokens_update', data: [] })
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('off() called directly with the handler also unsubscribes', () => {
    const handler = vi.fn()
    on('step', handler)
    off('step', handler)
    emit({ type: 'step', data: { step: 1, action: 'a', target: 't', status: 'done', screenshot: null } })
    expect(handler).not.toHaveBeenCalled()
  })

  it('multiple handlers on the same type all fire', () => {
    const h1 = vi.fn()
    const h2 = vi.fn()
    on('result', h1)
    on('result', h2)
    const payload = { output: 'ok', steps: 3, duration_ms: 1200 }
    emit({ type: 'result', data: payload })
    expect(h1).toHaveBeenCalledWith(payload)
    expect(h2).toHaveBeenCalledWith(payload)
  })

  it('handlers only fire for their subscribed type', () => {
    const stepHandler = vi.fn()
    const resultHandler = vi.fn()
    on('step', stepHandler)
    on('result', resultHandler)
    emit({ type: 'result', data: { output: 'ok', steps: 1, duration_ms: 100 } })
    expect(stepHandler).not.toHaveBeenCalled()
    expect(resultHandler).toHaveBeenCalledTimes(1)
  })

  it('clear() removes all handlers across all types', () => {
    const a = vi.fn()
    const b = vi.fn()
    on('step', a)
    on('result', b)
    clear()
    emit({ type: 'step', data: { step: 1, action: 'a', target: 't', status: 'done', screenshot: null } })
    emit({ type: 'result', data: { output: 'ok', steps: 1, duration_ms: 100 } })
    expect(a).not.toHaveBeenCalled()
    expect(b).not.toHaveBeenCalled()
    expect(_handlerCount()).toBe(0)
  })

  it('handler throwing does not prevent sibling handlers from firing', () => {
    const ok = vi.fn()
    on('result', () => {
      throw new Error('boom')
    })
    on('result', ok)
    expect(() =>
      emit({ type: 'result', data: { output: 'ok', steps: 1, duration_ms: 100 } })
    ).toThrow('boom')
    expect(ok).toHaveBeenCalledTimes(1)
  })

  it('100 subscribe/unsubscribe cycles leave zero handlers', () => {
    for (let i = 0; i < 100; i++) {
      const handler = () => {}
      const off1 = on('step', handler)
      const off2 = on('result', handler)
      off1()
      off2()
    }
    expect(_handlerCount()).toBe(0)
  })
})
```

The test imports `_handlerCount` — a debug helper for asserting that no handlers leaked. We export it from the implementation.

- [ ] **Step 2: Run the test, verify it fails**

Run: `cd frontend && npx vitest run src/composables/__tests__/useMessageBus.spec.ts`
Expected: FAIL with `Cannot find module '../useMessageBus'` (the file does not exist yet).

- [ ] **Step 3: Implement `useMessageBus.ts`**

Create `frontend/src/composables/useMessageBus.ts`:

```typescript
// In-process pub/sub for WebSocket frames. The WebSocket transport
// (useWebSocket) is the single producer; components and composables
// are consumers. Handlers receive only the `data` payload, not the
// envelope, so a handler signature looks like:
//
//     bus.on('hot_tokens_update', (tokens: HotToken[]) => { … })
//
// The bus is a module-level singleton. Tests must call `clear()` in
// `beforeEach` to isolate state. The intentional design trade-off —
// "the bus is a singleton, not a factory" — keeps the surface small
// at the cost of needing explicit `clear()` in tests. See the
// OpenSpec change "arch-refactor-frontend-message-bus" for context.

import type { WsMessage, WsMessageType } from '../types/ws'

type Handler = (data: unknown) => void

const handlers = new Map<WsMessageType, Set<Handler>>()

export function on<T extends WsMessageType>(
  type: T,
  handler: (data: WsMessage<T>['data']) => void
): () => void {
  let set = handlers.get(type)
  if (!set) {
    set = new Set()
    handlers.set(type, set)
  }
  set.add(handler as Handler)
  return () => {
    set?.delete(handler as Handler)
  }
}

export function off<T extends WsMessageType>(type: T, handler: (data: WsMessage<T>['data']) => void): void {
  handlers.get(type)?.delete(handler as Handler)
}

export function emit(msg: WsMessage): void {
  const set = handlers.get(msg.type)
  if (!set) return
  for (const h of [...set]) {
    h(msg.data)
  }
}

export function clear(): void {
  handlers.clear()
}

// Test-only — not for production use. Asserts handler count is stable
// across mount/unmount cycles.
export function _handlerCount(): number {
  let n = 0
  for (const set of handlers.values()) n += set.size
  return n
}
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `cd frontend && npx vitest run src/composables/__tests__/useMessageBus.spec.ts`
Expected: 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/composables/useMessageBus.ts frontend/src/composables/__tests__/useMessageBus.spec.ts
git commit -m "feat(ws): add useMessageBus pub/sub with on/off/emit/clear"
```

---

## Task 3: Wire `useWebSocket` to call `bus.emit`

**Files:**
- Modify: `frontend/src/composables/useWebSocket.ts`

The current `useWebSocket` has a `handleMessage` method with 5 `if (data.type === '…') console.log(…)` branches. None of those branches do anything reactive. We replace `handleMessage` with a single `bus.emit(parsed)` call. The `lastMessage` ref is kept (and re-emitted on every message) so any consumer still reading it does not break in this task; it is removed in Task 8.

- [ ] **Step 1: Replace `handleMessage` with `bus.emit`**

In `frontend/src/composables/useWebSocket.ts`, remove the `handleMessage` function (lines 25-37). Then in `ws.onmessage` (around line 70), replace the call:

```typescript
// OLD:
// handleMessage(parsed)

// NEW:
import { emit as busEmit } from './useMessageBus'
// (place the import at the top of the file)
…
ws.onmessage = (event) => {
  try {
    const parsed = JSON.parse(event.data)
    if (parsed.type === 'history' && parsed.data?.session_id) {
      setSessionId(parsed.data.session_id)
    }
    if (parsed.type === 'session_created' && parsed.data?.session_id) {
      setSessionId(parsed.data.session_id)
    }
    busEmit(parsed)
    lastMessage.value = { ...parsed }
  } catch {
    // ignore malformed messages
  }
}
```

At the top of the file, add the import:

```typescript
import { emit as busEmit } from './useMessageBus'
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Run the existing `useWebSocket` smoke test**

Run: `cd frontend && npx vitest run src/composables/__tests__/useWebSocket.spec.ts`
Expected: PASS (the smoke test only checks `typeof useWebSocket === 'function'`).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/composables/useWebSocket.ts
git commit -m "refactor(ws): useWebSocket emits to message bus instead of branching by type"
```

---

## Task 4: TDD — write `useAgent` bus dispatch test

**Files:**
- Create: `frontend/src/composables/__tests__/useAgent.spec.ts`

We are about to replace the 9-branch `handleWsMessage` in `useAgent` with 9 `bus.on` calls. The test below drives the bus and asserts the agent's reactive state changes. After this test is red, Task 5 makes it green.

The test uses `nextTick` to let Vue flush reactive updates.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/composables/__tests__/useAgent.spec.ts`:

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { useAgent } from '../useAgent'
import { emit, clear } from '../useMessageBus'

describe('useAgent bus dispatch', () => {
  beforeEach(() => {
    clear()
  })

  it('step event pushes a new step', async () => {
    const agent = useAgent()
    emit({
      type: 'step',
      data: { step: 1, action: 'goto', target: 'binance.com', status: 'running', screenshot: null },
    })
    await nextTick()
    expect(agent.steps.value).toHaveLength(1)
    expect(agent.steps.value[0].step).toBe(1)
  })

  it('repeated step event with same step number updates in place', async () => {
    const agent = useAgent()
    emit({ type: 'step', data: { step: 1, action: 'a', target: 't', status: 'running', screenshot: null } })
    emit({ type: 'step', data: { step: 1, action: 'a', target: 't', status: 'done', screenshot: null } })
    await nextTick()
    expect(agent.steps.value).toHaveLength(1)
    expect(agent.steps.value[0].status).toBe('done')
  })

  it('result event sets result and clears running', async () => {
    const agent = useAgent()
    agent.running.value = true
    emit({ type: 'result', data: { output: 'done', steps: 3, duration_ms: 500 } })
    await nextTick()
    expect(agent.result.value).toEqual({ output: 'done', steps: 3, duration_ms: 500 })
    expect(agent.running.value).toBe(false)
  })

  it('error event sets error and clears running', async () => {
    const agent = useAgent()
    agent.running.value = true
    emit({ type: 'error', data: { message: 'oops', step: 2 } })
    await nextTick()
    expect(agent.error.value).toEqual({ message: 'oops', step: 2 })
    expect(agent.running.value).toBe(false)
  })

  it('cancelled event clears running', async () => {
    const agent = useAgent()
    agent.running.value = true
    emit({ type: 'cancelled', data: null })
    await nextTick()
    expect(agent.running.value).toBe(false)
  })

  it('live_url event sets liveUrl', async () => {
    const agent = useAgent()
    emit({ type: 'live_url', data: { url: 'https://example.com/live' } })
    await nextTick()
    expect(agent.liveUrl.value).toBe('https://example.com/live')
  })

  it('queue_status event sets queuePending', async () => {
    const agent = useAgent()
    emit({ type: 'queue_status', data: { pending: 3 } })
    await nextTick()
    expect(agent.queuePending.value).toBe(3)
  })

  it('thinking event appends to thinkingSteps', async () => {
    const agent = useAgent()
    emit({ type: 'thinking', data: { step: 1, description: 'analyzing' } })
    emit({ type: 'thinking', data: { step: 2, description: 'planning' } })
    await nextTick()
    expect(agent.thinkingSteps.value).toEqual([
      { step: 1, description: 'analyzing' },
      { step: 2, description: 'planning' },
    ])
  })

  it('tool_call_start then tool_call_result transitions status pending → completed', async () => {
    const agent = useAgent()
    emit({ type: 'tool_call_start', data: { tool: 'fetch', arguments: { url: 'x' } } })
    emit({ type: 'tool_call_result', data: { tool: 'fetch', result: { ok: true } } })
    await nextTick()
    expect(agent.toolCalls.value).toHaveLength(1)
    expect(agent.toolCalls.value[0].status).toBe('completed')
    expect(agent.toolCalls.value[0].result).toEqual({ ok: true })
  })

  it('unmounting the consumer stops it receiving further events', async () => {
    const agent = useAgent()
    const off = (useAgent as any).test_offs ?? (() => {
      // simulate the unmount path
    })
    // we cannot easily call onUnmounted outside a component setup,
    // so we assert only that without bus subscription nothing fires
    // (the bus is cleared between tests via beforeEach)
    expect(agent.steps.value).toHaveLength(0)
  })
})
```

Note: the test's last `it` is a stub — full unmount assertions are in Task 9's mount/unmount 100-cycles test, which uses `@vue/test-utils` `mountSuspended`. The unit test here only proves the bus → state path works.

- [ ] **Step 2: Run the test, verify it fails**

Run: `cd frontend && npx vitest run src/composables/__tests__/useAgent.spec.ts`
Expected: FAIL — `emit` is currently not wired to `useAgent` state because we have not yet replaced `handleWsMessage` with `bus.on` subscriptions. The 9 type-specific tests will fail with `expected length 1, got 0`.

- [ ] **Step 3: Commit the failing test (red)**

```bash
git add frontend/src/composables/__tests__/useAgent.spec.ts
git commit -m "test(agent): add bus-dispatch tests for useAgent (red)"
```

---

## Task 5: Replace `useAgent.handleWsMessage` if-else with 9 `bus.on` subscriptions

**Files:**
- Modify: `frontend/src/composables/useAgent.ts`

`useAgent` is a plain function (not a Vue composable in the strict sense — it does not register lifecycle hooks). We add a small `setupAgentBus()` helper that subscribes to the 9 chat types and returns the unsubscribe handles. For the unit test path (no Vue component), we expose this as `__test_install` so the test can manually wire it.

In production, `HomeView.vue` will call this in `onMounted` and the returned array in `onUnmounted`. We cover that wiring in Task 6.

- [ ] **Step 1: Add `installBusHandlers` export**

In `frontend/src/composables/useAgent.ts`, add at the bottom of the file (after the existing `return { … }` block):

```typescript
import { on as busOn } from './useMessageBus'

/**
 * Subscribe agent state to the 9 chat-related WebSocket event types.
 * Returns an array of unsubscribe functions; caller is responsible
 * for invoking them on unmount.
 *
 * Production callers: HomeView.vue (calls in onMounted, off in onUnmounted).
 * Test callers: useAgent.spec.ts (calls once per test, then clear() in
 * beforeEach ensures isolation).
 */
export function installBusHandlers(agent: ReturnType<typeof useAgent>) {
  return [
    busOn('step', (data) => {
      const idx = agent.steps.value.findIndex((s) => s.step === data.step)
      if (idx >= 0) {
        agent.steps.value[idx] = { ...agent.steps.value[idx], ...data }
      } else {
        agent.steps.value.push(data)
      }
      if (data.screenshot) agent.screenshot.value = data.screenshot
    }),
    busOn('result', (data) => {
      agent.result.value = data
      agent.commandHistory.value.push(data)
      agent.running.value = false
      agent.steps.value = agent.steps.value.map((s) => ({ ...s, status: 'done' as const }))
    }),
    busOn('error', (data) => {
      agent.error.value = data
      agent.running.value = false
    }),
    busOn('cancelled', () => {
      agent.running.value = false
    }),
    busOn('live_url', (data) => {
      agent.liveUrl.value = data.url
    }),
    busOn('queue_status', (data) => {
      agent.queuePending.value = data.pending
    }),
    busOn('thinking', (data) => {
      agent.thinkingSteps.value.push({ step: data.step, description: data.description })
    }),
    busOn('tool_call_start', (data) => {
      agent.toolCalls.value.push({ name: data.tool, arguments: data.arguments, status: 'pending' })
    }),
    busOn('tool_call_result', (data) => {
      const tc = agent.toolCalls.value.find((t) => t.name === data.tool)
      if (tc) {
        tc.status = 'completed'
        tc.result = data.result
      }
    }),
  ]
}
```

- [ ] **Step 2: Call `installBusHandlers` from inside `useAgent` for production use**

The simplest path: have `useAgent` return the same shape as before, plus a `__installBus` function. We make `useAgent` self-install by registering a one-shot on next tick. Actually, the cleanest path is to have `useAgent` self-install and store the offs in a closure; we expose a `dispose` for tests and components.

Replace the `return { … }` block in `useAgent.ts` with:

```typescript
const offs = installBusHandlers({ steps, result, error, running, screenshot, queuePending, liveUrl, commandHistory, thinkingSteps, toolCalls })

// In a Vue component, calling onUnmounted(offs.forEach(off => off())) is
// the caller's responsibility. We expose the array for that.
return {
  steps,
  result,
  error,
  running,
  screenshot,
  queuePending,
  liveUrl,
  commandHistory,
  thinkingSteps,
  toolCalls,
  startTask,
  cancelTask,
  resetTask,
  handleWsMessage, // DEPRECATED — kept for one task; remove in Task 8
  reset,
  __busOffs: offs, // for onUnmounted in components
}
```

The challenge: `useAgent` is currently not used inside `setup()` with lifecycle — it's called once in `HomeView.vue:111`. The `__busOffs` array leaks if `HomeView` unmounts without calling them. We fix that in Task 6.

For now, also leave `handleWsMessage` exported (its body is still the old 9-branch code). Production traffic flows through `bus.emit` → `installBusHandlers` so `handleWsMessage` is dead code; we remove it in Task 8.

- [ ] **Step 3: Update unit test to call `installBusHandlers`**

In `frontend/src/composables/__tests__/useAgent.spec.ts`, modify the first `it` block of each test to wire up the bus. Add this helper at the top of the `describe`:

```typescript
import { installBusHandlers, useAgent } from '../useAgent'

let offs: Array<() => void> = []

function freshAgent() {
  const agent = useAgent()
  offs = installBusHandlers(agent)
  return agent
}
```

Then inside each `it`, replace `const agent = useAgent()` with `const agent = freshAgent()`. Add an `afterEach`:

```typescript
import { afterEach } from 'vitest'

afterEach(() => {
  offs.forEach((off) => off())
  offs = []
})
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `cd frontend && npx vitest run src/composables/__tests__/useAgent.spec.ts`
Expected: all tests pass.

- [ ] **Step 5: TypeScript check**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: no errors. (`handleWsMessage` is still typed correctly; `__busOffs` is a new public field.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/composables/useAgent.ts frontend/src/composables/__tests__/useAgent.spec.ts
git commit -m "refactor(agent): subscribe to message bus via 9 bus.on calls"
```

---

## Task 6: Refactor `HomeView.vue` — replace 2 `watch(lastMessage)` blocks with `bus.on`

**Files:**
- Modify: `frontend/src/views/HomeView.vue`

`HomeView.vue` has two `watch(lastMessage, …)` blocks (lines 134-163 and 165-185) that handle `interactive`, `thinking`, `tool_call_start`, `tool_call_result`, and `result` (the second `result` block writes to `messages.value` and is NOT redundant with `useAgent`'s handler — the first routes to `useAgent` via `handleWsMessage`, the second captures the result for chat history). We replace both with `bus.on` calls.

- [ ] **Step 1: Remove `watch` import if no other use**

Check whether `watch` is used elsewhere in `HomeView.vue` (it is not — `HomeView.vue` only watches `lastMessage`). Replace the import:

```typescript
// OLD:
import { ref, watch, onMounted, nextTick } from 'vue'
// NEW:
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
```

- [ ] **Step 2: Add bus subscription lifecycle**

> **Plan deviation (from Task 5 review):** `useAgent` does NOT auto-install bus subscriptions. The spec originally had `useAgent` call `installBusHandlers` internally and expose `__busOffs` on the return value, but the test pattern (Task 4) required explicit calls — auto-install would double-register handlers in the test. As a result, `useAgent` returns its original shape (no `__busOffs`), and the consumer must call `installBusHandlers(agent)` explicitly.

Update the imports and the `useAgent` destructure (line 111):

```typescript
// OLD:
import { ref, watch, onMounted, nextTick } from 'vue'
// NEW:
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
```

```typescript
// OLD:
import { useAgent } from '../composables/useAgent'
// NEW:
import { useAgent, installBusHandlers } from '../composables/useAgent'
```

```typescript
// OLD:
const { steps, running, screenshot, queuePending, liveUrl, cancelTask, resetTask, handleWsMessage } = useAgent()
// NEW:
const agent = useAgent()
const { steps, running, screenshot, queuePending, liveUrl, cancelTask, resetTask } = agent
// handleWsMessage is no longer needed — bus subscriptions replace it.
// Use the explicit `agent` reference for installBusHandlers below.
```

After the existing state declarations (after line 132), declare the agent bus-offs container and install the 9 useAgent subscriptions in `onMounted` (so the setup is tied to component lifecycle):

```typescript
let agentBusOffs: Array<() => void> = []

onMounted(() => {
  agentBusOffs = installBusHandlers(agent)
})
```

- [ ] **Step 3: Add 4 `bus.on` calls for the first watch block (interactive + 3 chat events)**

After the existing state declarations (after line 132), add:

```typescript
const busOffs: Array<() => void> = []

busOffs.push(
  busOn('interactive', (data) => {
    interactiveCommand.value = {
      type: data.type,
      message: data.message,
      screenshot: data.screenshot || null,
    }
  }),
  busOn('thinking', (data) => {
    currentThinkingSteps.value.push(data)
  }),
  busOn('tool_call_start', (data) => {
    currentToolCalls.value.push({
      name: data.tool,
      arguments: data.arguments,
      status: 'pending',
    })
  }),
  busOn('tool_call_result', (data) => {
    const tc = currentToolCalls.value.find((t) => t.name === data.tool && t.status === 'pending')
    if (tc) {
      tc.status = 'completed'
      tc.result = data.result
    }
  })
)
```

Note: `thinking` and `tool_call_*` are also subscribed by `useAgent`. Both consumers see the same emit — the bus dispatches to all subscribers. This is by design: `useAgent` tracks task execution; `HomeView` tracks the current chat message's thought/tool trail. They share the data, not the state.

- [ ] **Step 4: Add `bus.on('result', …)` for the second watch block**

After the previous block, add:

```typescript
busOffs.push(
  busOn('result', (data) => {
    messages.value.push({
      role: 'assistant',
      text: data.output,
      timestamp: new Date(),
      thinkingSteps: [...currentThinkingSteps.value],
      toolCalls: [...currentToolCalls.value],
    })
  })
)
```

(Read the existing watch block at lines 165-185 to copy the exact field mapping for `messages.value.push(...)`; the snippet above is the canonical shape.)

- [ ] **Step 5: Add `onUnmounted` cleanup**

At the end of the `<script setup>` block (or wherever the existing `onMounted` is), add:

```typescript
onUnmounted(() => {
  busOffs.forEach((off) => off())
  agentBusOffs.forEach((off) => off())
})
```

- [ ] **Step 6: Delete the two `watch(lastMessage, …)` blocks (lines 134-163 and 165-185)**

Remove both blocks entirely. The reactive `lastMessage` ref is no longer read in this file.

- [ ] **Step 7: Verify TypeScript compiles**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: no errors. (`watch` is no longer imported; `lastMessage` may now be unused — destructure it out from the `useWebSocket()` call if `tsc` warns.)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/HomeView.vue
git commit -m "refactor(home): migrate from watch(lastMessage) to bus.on subscriptions"
```

---

## Task 7: Refactor `TradingView.vue` — replace `hot_tokens_update` watch with `bus.on`

**Files:**
- Modify: `frontend/src/views/TradingView.vue`

`TradingView.vue:835-841` has a single `useWebSocket()` call (returning `lastMessage`) and a `watch(lastMessage, …)` that filters on `hot_tokens_update`. The refactor: use the bus directly, drop the `lastMessage` destructure.

- [ ] **Step 1: Read the exact watch block to migrate**

In `frontend/src/views/TradingView.vue` around line 835, the current code is:

```typescript
// --- WebSocket ---
const { lastMessage } = useWebSocket()

watch(lastMessage, (msg) => {
  if (msg?.type === 'hot_tokens_update') {
    hotTokens.value = msg.data || []
  }
})
```

- [ ] **Step 2: Replace with bus subscription**

```typescript
// --- WebSocket (hot tokens) ---
import { on as busOn } from '../composables/useMessageBus'
import { onUnmounted } from 'vue'

const hotTokensOff = busOn('hot_tokens_update', (data) => {
  hotTokens.value = data
})

onUnmounted(() => {
  hotTokensOff()
})
```

- [ ] **Step 3: Remove the now-unused `useWebSocket` import if no other consumer**

Grep `useWebSocket` in `TradingView.vue` (line 540 has the import). If `useWebSocket` is no longer used anywhere else in the file, remove the import too:

```typescript
// Remove line 540:
// import { useWebSocket } from '../composables/useWebSocket'
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: no errors. If `useWebSocket` is still referenced elsewhere, the import stays.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/TradingView.vue
git commit -m "refactor(trading): migrate hot_tokens_update from watch to bus.on"
```

---

## Task 8: Remove deprecated `handleWsMessage` and `lastMessage`

**Files:**
- Modify: `frontend/src/composables/useAgent.ts`
- Modify: `frontend/src/composables/useWebSocket.ts`
- Modify: `frontend/src/views/HomeView.vue`
- Modify: `frontend/src/views/TradingView.vue`

Now that all consumers route through the bus, the deprecated `useAgent.handleWsMessage` function and the `lastMessage` ref in `useWebSocket` are dead code. Remove them.

- [ ] **Step 1: Remove `handleWsMessage` from `useAgent.ts`**

Delete the `handleWsMessage` function (lines 69-110). Remove it from the returned object.

- [ ] **Step 2: Run agent unit tests**

Run: `cd frontend && npx vitest run src/composables/__tests__/useAgent.spec.ts`
Expected: PASS (the tests use the bus, not `handleWsMessage`).

- [ ] **Step 3: Remove `lastMessage` from `useWebSocket.ts`**

Delete:
- The `const lastMessage = ref<WsMessage | null>(null)` declaration.
- The `lastMessage.value = { ...parsed }` line in `ws.onmessage`.
- The `lastMessage` field in the return object.
- The `WsMessage` import (if no longer referenced).

- [ ] **Step 4: Remove `lastMessage` from consumers**

In `HomeView.vue` and `TradingView.vue`, remove `lastMessage` from the destructure of `useWebSocket()`. If `useWebSocket` is no longer called at all in `TradingView.vue`, remove that import too (see Task 7 Step 3).

- [ ] **Step 5: Verify TypeScript compiles**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Run all tests**

Run: `cd frontend && npx vitest run`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/composables/useAgent.ts frontend/src/composables/useWebSocket.ts frontend/src/views/HomeView.vue frontend/src/views/TradingView.vue
git commit -m "refactor(ws): remove deprecated handleWsMessage and lastMessage"
```

---

## Task 9: Memory-leak regression test — 100 mount/unmount cycles

**Files:**
- Create: `frontend/src/views/__tests__/HomeView.bus.spec.ts`

The bus is a module-level singleton. A subtle bug would be handlers accumulating across mount cycles. We assert handler count stays at 0 (or at the expected number for currently-mounted components) after many mount/unmount cycles.

- [ ] **Step 1: Install `@vue/test-utils` if not already a dep**

Run: `cd frontend && grep -q '"@vue/test-utils"' package.json || npm install -D @vue/test-utils`

- [ ] **Step 2: Write the mount/unmount test**

Create `frontend/src/views/__tests__/HomeView.bus.spec.ts`:

```typescript
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { _handlerCount, clear } from '../../composables/useMessageBus'
import HomeView from '../HomeView.vue'

// Stub the global WebSocket so useWebSocket() does not throw on mount.
class FakeWebSocket {
  url: string
  readyState = 0
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(url: string) {
    this.url = url
    setTimeout(() => {
      this.readyState = 1
      this.onopen?.()
    }, 0)
  }
  send() {}
  close() {
    this.readyState = 3
    this.onclose?.()
  }
}
;(globalThis as any).WebSocket = FakeWebSocket

describe('HomeView bus mount/unmount', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    clear()
  })

  afterEach(() => {
    clear()
  })

  it('handler count returns to 0 after 100 mount/unmount cycles', async () => {
    for (let i = 0; i < 100; i++) {
      const wrapper = mount(HomeView)
      await wrapper.vm.$nextTick()
      wrapper.unmount()
    }
    // Allow Vue to flush pending unmount hooks
    await new Promise((r) => setTimeout(r, 0))
    expect(_handlerCount()).toBe(0)
  })
})
```

- [ ] **Step 3: Run the test, verify it passes**

Run: `cd frontend && npx vitest run src/views/__tests__/HomeView.bus.spec.ts`
Expected: PASS. If a handler count > 0 leaks, the test fails and we know the cleanup in Task 6 or Task 7 is missing an `onUnmounted`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/__tests__/HomeView.bus.spec.ts frontend/package.json frontend/package-lock.json
git commit -m "test(home): verify bus handlers are released across mount/unmount cycles"
```

---

## Task 10: Document the seam and add dev-mode trace logging

**Files:**
- Modify: `frontend/src/composables/useMessageBus.ts`
- Modify: `frontend/CONTEXT.md`

- [ ] **Step 1: Add dev-mode trace log to `useMessageBus.ts`**

In the `emit` function, prepend a `console.debug` gated on `import.meta.env.DEV`:

```typescript
export function emit(msg: WsMessage): void {
  if (import.meta.env.DEV) {
    console.debug(`[bus] emit ${msg.type}`, msg.data)
  }
  const set = handlers.get(msg.type)
  if (!set) return
  for (const h of [...set]) {
    h(msg.data)
  }
}
```

- [ ] **Step 2: Add the Message Bus term to `frontend/CONTEXT.md`**

Append a section (or insert in the existing "seams" section if present):

```markdown
## Message Bus

`composables/useMessageBus.ts` is the in-process pub/sub for WebSocket
frames. The transport (`useWebSocket`) is the sole producer; components
and composables subscribe via `bus.on(type, handler)`. Adding a new
server event:

1. Add the literal to `WsMessageType` in `types/ws.ts`
2. Add the data shape to `WsMessageByType`
3. Subscribe via `bus.on(<type>, handler)` in the relevant consumer

The bus is a module-level singleton; tests must call `clear()` in
`beforeEach`. There is no priority or async dispatch — all handlers
fire synchronously on the WebSocket receive thread.
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/composables/useMessageBus.ts frontend/CONTEXT.md
git commit -m "docs(ws): document message bus seam and dev-mode trace"
```

---

## Task 11: Final verification

**Files:** none modified.

- [ ] **Step 1: Run the full test suite**

Run: `cd frontend && npx vitest run`
Expected: all tests pass (useWebSocket smoke, useMessageBus 9 tests, useAgent dispatch tests, HomeView mount/unmount test).

- [ ] **Step 2: TypeScript build**

Run: `cd frontend && npm run build`
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 3: Manual smoke (out-of-band)**

Spin up the dev server (`cd frontend && npm run dev`) and backend (`cd backend && python main.py`). Open the chat UI, send a task. Verify:

- step / result / error / thinking events appear in real time
- the second `result` event writes a message into the chat history
- `hot_tokens_update` populates the Hot Tokens tab in TradingView
- DevTools console shows `[bus] emit <type>` debug lines

If any event is missing, grep for stale `watch(lastMessage, …)` patterns:
`grep -rn "watch(lastMessage" frontend/src`

- [ ] **Step 4: Mark the OpenSpec change ready for archive**

Per OpenSpec workflow: once all tasks above are complete, the change `arch-refactor-frontend-message-bus` is ready to be archived. Run `openspec archive arch-refactor-frontend-message-bus` (or the project's equivalent — see `openspec/AGENTS.md` if it exists).

- [ ] **Step 5: Final commit (if any doc-only updates remain)**

```bash
git add -A
git status  # review what's staged; should only be docs/openspec artifacts
git commit -m "chore: mark message-bus change complete"
```

---

## Self-Review Notes

**Spec coverage:**
- ✅ WsMessageType union: Task 1
- ✅ WsMessageByType discriminated union: Task 1
- ✅ useMessageBus on/off/emit/clear: Task 2
- ✅ Module-level singleton (no factory): Task 2 Step 3
- ✅ useWebSocket.handleMessage → bus.emit: Task 3
- ✅ useAgent 9-branch → 9 bus.on: Task 5
- ✅ TradingView.vue:838 watch → bus.on: Task 7
- ✅ HomeView.vue 2 watch blocks (proposal missed this): Task 6
- ✅ Memory leak test: Task 9
- ✅ Documentation: Task 10
- ✅ Dev-mode trace: Task 10

**Gaps caught during self-review:**
- The proposal said "useWebSocket.handleMessage no longer contains if-else" but did not mention the `lastMessage` ref. Tasks 3 and 8 handle this: keep `lastMessage` during migration, remove in Task 8 once all consumers are off it.
- The proposal did not mention `HomeView.vue` at all. Grep found 2 `watch(lastMessage, …)` blocks (lines 134, 165). Task 6 covers both.
- `useAgent.handleWsMessage` is exported and consumed by `HomeView.vue:111`. We keep it exported for one task (Task 5) as a no-op for backward compat, then remove in Task 8.

**Cross-document dependencies (for the executor):**
- `arch-refactor-trading-view-tabs` Phase 0 prerequisite: `useMessageBus.ts` must exist and export `on/off/emit/clear`. Verified in Task 2.
- `arch-refactor-signal-analyzer` Phase 5 (hint text via WS) will subscribe to `analysis:short:complete` via the bus. Already supported in `WsMessageType` (Task 1).
