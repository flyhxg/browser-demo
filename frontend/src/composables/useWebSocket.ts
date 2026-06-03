import { ref, onUnmounted } from 'vue'
import type { WsMessage } from '../types'

export function useWebSocket() {
  const connected = ref(false)
  const lastMessage = ref<WsMessage | null>(null)
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let intentionalClose = false
  let offlineBuffer: object[] = []

  function getSessionId(): string | null {
    return localStorage.getItem('chat_session_id')
  }

  function setSessionId(id: string) {
    localStorage.setItem('chat_session_id', id)
  }

  function clearSessionId() {
    localStorage.removeItem('chat_session_id')
    offlineBuffer = []
  }

  function handleMessage(data: any) {
    if (data.type === 'analysis:short') {
      console.log('Analysis short received:', data.data)
    } else if (data.type === 'signal:new') {
      console.log('New signal:', data.data)
    } else if (data.type === 'signal:analyzed') {
      console.log('Signal analyzed:', data.data)
    } else if (data.type === 'trade:executed') {
      console.log('Trade executed:', data.data)
    } else if (data.type === 'trade:closed') {
      console.log('Trade closed:', data.data)
    }
  }

  function connect() {
    if (ws && ws.readyState === WebSocket.OPEN) return

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const sessionId = getSessionId()
    const url = sessionId
      ? `${protocol}//${location.host}/ws?session_id=${encodeURIComponent(sessionId)}`
      : `${protocol}//${location.host}/ws`
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
        // Save session_id when receiving history on connect
        if (parsed.type === 'history' && parsed.data?.session_id) {
          setSessionId(parsed.data.session_id)
        }
        // Handle session events
        if (parsed.type === 'session_created' && parsed.data?.session_id) {
          setSessionId(parsed.data.session_id)
        }
        // Handle new event types
        handleMessage(parsed)
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

  function clearSession() {
    // Tell backend to clear messages for current session
    send({ type: 'clear_session' })
    // Clear local buffer and messages
    offlineBuffer = []
  }

  function newSession() {
    // Tell backend to create a new session and switch
    send({ type: 'new_session' })
    // Clear local state
    offlineBuffer = []
    clearSessionId()
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

  return { connected, lastMessage, disconnect, send, sendCommand, clearSession, newSession, clearSessionId, connect }
}
