import { ref, onUnmounted } from 'vue'
import type { WsMessage } from '../types'

export function useWebSocket() {
  const connected = ref(false)
  const lastMessage = ref<WsMessage | null>(null)
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let intentionalClose = false

  function connect() {
    if (ws && ws.readyState === WebSocket.OPEN) return

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${location.host}/ws`
    ws = new WebSocket(url)

    ws.onopen = () => {
      connected.value = true
    }

    ws.onmessage = (event) => {
      try {
        lastMessage.value = JSON.parse(event.data)
      } catch {
        // ignore malformed messages
      }
    }

    ws.onclose = () => {
      connected.value = false
      ws = null
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

  function disconnect() {
    intentionalClose = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = null
    ws?.close()
    ws = null
  }

  connect()

  onUnmounted(disconnect)

  return { connected, lastMessage, disconnect }
}
