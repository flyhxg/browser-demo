import { ref, onUnmounted } from 'vue'
import type { WsMessage } from '../types'

export function useWebSocket() {
  const connected = ref(false)
  const lastMessage = ref<WsMessage | null>(null)
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let intentionalClose = false
  let offlineBuffer: object[] = []

  function connect() {
    if (ws && ws.readyState === WebSocket.OPEN) return

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${location.host}/ws`
    ws = new WebSocket(url)

    ws.onopen = () => {
      connected.value = true
      const _ws = ws
      while (offlineBuffer.length > 0 && _ws) {
        const msg = offlineBuffer.shift()
        if (msg) _ws.send(JSON.stringify(msg))
      }
    }

    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data)
        // Force reactivity by creating a new object
        lastMessage.value = { ...parsed }
      } catch {
        // ignore malformed messages
      }
    }

    ws.onclose = () => {
      connected.value = false
      ws = null
      offlineBuffer = []
      if (!intentionalClose) {
        scheduleReconnect()
      }
    }

    ws.onerror = () => {
      ws?.close()
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = setTimeout(connect, 3000)
  }

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

  function disconnect() {
    intentionalClose = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = null
    ws?.close()
    ws = null
  }

  connect()

  onUnmounted(disconnect)

  return { connected, lastMessage, disconnect, send, sendCommand }
}
