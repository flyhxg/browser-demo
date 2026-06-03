## Context

browser-use 是一个 Python 库（位于 `D:\work\browser-use`），提供 AI 驱动的浏览器自动化能力。它通过 CDP 协议控制 Chromium，用 LLM 解析页面状态并生成操作指令。当前仅支持 Python 脚本调用，没有可视化界面。

本项目（`D:\work\browser-demo`）是一个全新的 Web 应用，将 browser-use 封装为可交互的 Web 服务，让用户通过浏览器界面使用 AI 浏览器自动化功能。

## Goals / Non-Goals

**Goals:**
- 提供直观的 Web 界面，用户无需编写代码即可使用 AI 浏览器自动化
- 支持在网页上配置多个 LLM 提供商的 API Key 并验证
- 支持本地 Chromium 和 Browser Use Cloud 两种浏览器模式
- 实时展示 Agent 执行过程（步骤日志 + 截图）
- 支持本地运行（`python main.py`）和 Docker 云上部署

**Non-Goals:**
- 不做用户认证/多租户系统（Demo 项目）
- 不做 Agent 历史记录持久化存储（仅内存中保存当前会话）
- 不做自定义工具/Action 注册（使用 browser-use 内置工具）
- 不做桌面应用打包（Electron/Tauri）
- 不做移动端适配

## Decisions

### 1. 前后端分离，单一仓库

**决策**: 前端（Vue 3 + Vite）和后端（FastAPI）放在同一个仓库，前端构建产物由 FastAPI 静态文件服务提供。

**替代方案**: 前后端独立仓库、微前端。对于 Demo 项目过度设计。

**理由**: 简化部署，本地运行只需 `python main.py`，Docker 部署只需一个容器。

### 2. WebSocket 实时通信

**决策**: Agent 执行过程通过 WebSocket 推送到前端，包括步骤状态、截图、最终结果。

**替代方案**: SSE（Server-Sent Events）、轮询。

**理由**: WebSocket 支持双向通信，未来可扩展为远程控制 Agent。SSE 仅单向，轮询延迟高。

### 3. LLM 配置存储在后端 JSON 文件

**决策**: LLM API Key 等配置存储在后端 JSON 文件（`backend/config.json`），通过 API 读写。前端不持久化 Key。

**替代方案**: `.env` 文件、浏览器 localStorage。

**理由**: `.env` 不适合动态读写，localStorage 在前端暴露 Key。JSON 文件支持结构化存储和动态更新，启动时自动加载。

### 4. Agent 执行为异步单任务

**决策**: 同一时间只运行一个 Agent 任务，异步执行。前端显示执行状态，支持取消。

**替代方案**: 多任务并行队列。

**理由**: Demo 项目不需要并行。单任务简化状态管理，避免资源竞争。后续可扩展为多任务。

### 5. 项目结构

```
browser-demo/
├── backend/
│   ├── main.py              # FastAPI 入口
│   ├── api/
│   │   ├── __init__.py
│   │   ├── config.py        # 配置管理 API
│   │   ├── tasks.py         # 任务执行 API
│   │   └── ws.py            # WebSocket 端点
│   ├── services/
│   │   ├── __init__.py
│   │   ├── agent_runner.py  # Agent 执行引擎
│   │   ├── llm_factory.py   # LLM 工厂，按配置创建实例
│   │   └── config_store.py  # 配置存储（JSON 文件）
│   ├── config.json          # 运行时配置文件（API Keys 等）
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.vue
│   │   ├── views/
│   │   │   ├── HomeView.vue   # 主页：任务输入+执行可视化
│   │   │   └── SettingsView.vue # 设置页：LLM配置+浏览器模式
│   │   ├── components/
│   │   │   ├── TaskInput.vue
│   │   │   ├── StepLog.vue
│   │   │   ├── ScreenshotView.vue
│   │   │   ├── ResultDisplay.vue
│   │   │   └── LlmConfigForm.vue
│   │   ├── composables/
│   │   │   ├── useWebSocket.ts
│   │   │   └── useAgent.ts
│   │   └── types/
│   │       └── index.ts
│   ├── package.json
│   └── vite.config.ts
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Risks / Trade-offs

- **[API Key 安全]** → 后端存储 Key，不返回明文给前端（仅返回是否已配置+掩码）
- **[Ollama 兼容性]** → Ollama 需要用户自行安装和启动，提供检测接口和错误提示
- **[Chromium 依赖]** → 本地模式需要系统安装 Chromium，Docker 镜像需内置
- **[单任务限制]** → 同时间只能执行一个任务，后续可扩展为任务队列
- **[截图性能]** → browser-use 的 `BrowserStateSummary.screenshot` 自带 base64 截图，无需额外调用

## WebSocket 消息协议

WebSocket 端点: `/ws`

消息格式 (JSON):
```json
{
  "type": "step" | "result" | "error" | "cancelled",
  "data": { ... }
}
```

| type | data 字段 |
|------|----------|
| `step` | `{ "step": number, "action": string, "target": string, "status": "running"|"done"|"error", "screenshot": "base64..." }` |
| `result` | `{ "output": string, "steps": number, "duration_ms": number }` |
| `error` | `{ "message": string, "step": number }` |
| `cancelled` | `{}` |

## 开发模式

本地开发时，前端使用 Vite dev server，通过代理转发请求到 FastAPI 后端：

```ts
// vite.config.ts
server: {
  proxy: {
    '/api': 'http://localhost:8000',
    '/ws': { target: 'ws://localhost:8000', ws: true }
  }
}
```

生产模式：前端构建为静态文件，由 FastAPI 直接托管。

## browser-use 安装

从 PyPI 安装：
```bash
pip install browser-use
```

或从本地路径安装（开发时）：
```bash
pip install -e D:\work\browser-use
```
