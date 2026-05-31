# ChatGPT-Style UI Design

## Goal

Replace the current task-based single-shot UI with a ChatGPT-style persistent chat interface: left panel shows the live browser preview, right panel shows chat history with messages and a collapsible step log.

## Layout

```
┌──────────────────────────────────────────────────────────┐
│                    HomeView.vue                           │
├────────────────────────────┬─────────────────────────────┤
│                            │  ┌─────────────────────────┐  │
│ Browser View          │  │   ChatHistory         │  │
│      (live URL iframe)      │  │   (scrollable)         │  │
│      60% width             │  │                         │  │
│      空白时不显示           │  │   [user bubble] 14:32 │  │
│                            │  │   [AI response]  14:33│  │
│                            │  │   [user bubble]  14:35│  │
│                            │  └─────────────────────────┘  │
│                            │  ┌─────────────────────────┐  │
│                            │  │ Step Log (可折叠)       │  │
│                            │  └─────────────────────────┘  │
│                            │  ┌─────────────────────────┐  │
│                            │  │ [输入框]    [发送]      │  │
│                            │  └─────────────────────────┘  │
└────────────────────────────┴─────────────────────────────┘
```

## Components

| Component | File | Responsibility |
|-----------|------|----------------|
| ChatMessage | `frontend/src/components/ChatMessage.vue` (NEW) | Single message bubble: user (right, blue) or assistant (left, gray), with timestamp |
| ChatHistory | `frontend/src/components/ChatHistory.vue` (NEW) | Scrollable container, receives `messages[]` array, auto-scrolls to bottom |
| HomeView | `frontend/src/views/HomeView.vue` (REFACTOR) | Left-right split layout, manages `messages` state, wire WS events |
| ScreenshotView | `frontend/src/components/ScreenshotView.vue` (UNCHANGED) | iframe + base64, shows when `liveUrl` is set |
| StepLog | `frontend/src/components/StepLog.vue` (UNCHANGED) | Collapsible step log panel |

## Message Data Model

```typescript
interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  timestamp: Date
}
```

## Data Flow

```
用户输入命令
  → sendCommand(command) via WebSocket
  → running = true
  → step events → StepLog updates in real-time
  → result event → messages.push({role:'assistant', text: result.output})
  → running = false
```

## Visual Style

- **User bubble**: background `#6366F1`, white text, right-aligned
- **AI bubble**: background `#2D2D2F`, white text, left-aligned
- **Timestamp**: small `#71717A` text below bubble
- **Input**: dark background `#18181B`, placeholder "输入命令..."
- **Send button**: blue `#6366F1`
- **Browser View**: 60% width, fills left panel, shown only when `liveUrl` is set
- **Step Log**: collapsible panel in right panel below ChatHistory

## Behavior

- Chat history is **in-memory only** — clears on page refresh
- Browser View **shown only when `liveUrl` is set** — blank on first load
- Step Log **collapsible** — click to expand/collapse
- Messages auto-scroll to bottom when new message arrives
- Multiple commands queue and execute sequentially; each result appears as a new AI message bubble