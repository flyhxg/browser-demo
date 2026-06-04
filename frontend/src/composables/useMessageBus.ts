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
  // Iterate over a snapshot so a handler that unsubscribes itself
  // does not skip the next handler. We also catch errors so a single
  // throwing handler cannot prevent its siblings from firing; the
  // first error is re-thrown after all handlers have been invoked.
  let firstError: unknown
  let didCatch = false
  for (const h of [...set]) {
    try {
      h(msg.data)
    } catch (e) {
      if (!didCatch) {
        firstError = e
        didCatch = true
      }
    }
  }
  if (didCatch) throw firstError
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
