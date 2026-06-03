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

## 路由

- **router.ts** — Vue Router 配置

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
