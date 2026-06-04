# 领域上下文：Frontend (Vue 3 + Vite)

## 概述

Frontend 是基于 Vue 3 + Vite 的单页应用，提供聊天交互界面、交易面板、工作流配置和 Polymarket 预测市场面板。

## 核心视图

- **views/HomeView.vue** — 聊天主界面（ChatGPT 风格左右分栏）
- **views/TradingView.vue** — 交易面板（币安期货）
- **views/SignalsView.vue** — 信号展示
- **views/PositionsView.vue** — 持仓列表
- **views/SettingsView.vue** — 系统配置
- **views/WorkflowView.vue** — 工作流配置

## 核心组件

- **components/TaskInput.vue** — 聊天输入框
- **components/ResultDisplay.vue** — 结果展示
- **components/ScreenshotView.vue** — 截图查看
- **components/ChatHistory.vue** — 聊天历史
- **components/InteractivePanel.vue** — 交互面板
- **components/CommandHistory.vue** — 命令历史

## Composables

- **composables/useAgent.ts** — Agent 状态管理
- **composables/useWebSocket.ts** — WebSocket 连接管理
- **composables/useMessageBus.ts** — 进程内 WebSocket 消息 pub/sub（详见下方"Message Bus"）

## 路由

- **router.ts** — Vue Router 配置

## Message Bus

`composables/useMessageBus.ts` 是 WebSocket 帧的进程内 pub/sub。传输层（`useWebSocket`）是唯一的生产者；组件和 composables 通过 `bus.on(type, handler)` 订阅。新增一个服务端事件的步骤：

1. 在 `types/ws.ts` 的 `WsMessageType` 中加入字面量
2. 在 `WsMessageByType` 中加入对应的 `data` 形状
3. 在相关消费者中通过 `bus.on(<type>, handler)` 订阅

Bus 是模块级单例；测试必须在 `beforeEach` 中调用 `clear()`。没有优先级或异步调度 —— 所有 handler 在 WebSocket 接收线程上同步触发。

**Error policy：** 第一个 handler 抛出的错误会被重新抛出；后续错误 `console.error`。这样单个坏的 consumer 不会阻塞它的兄弟节点，但排查异常应用时仍能看到所有失败。

## 数据流

```
用户输入 → TaskInput.vue → useWebSocket.ts → WebSocket → Backend
WebSocket 消息 → useWebSocket.ts → useAgent.ts → 组件渲染
```

## 状态管理

- `useAgent.ts` 管理全局 Agent 状态（消息列表、连接状态等）
- `useWebSocket.ts` 管理 WebSocket 连接和消息收发

## 术语

| 术语 | 说明 |
|------|------|
| useAgent | Agent 状态管理 composable |
| useWebSocket | WebSocket 连接 composable |
| message | 聊天消息，含 role / content / tool_calls 等 |
| status | 消息状态：idle / streaming / tool_calling / complete / error |
| session | 会话，含 session_id 和消息历史 |
