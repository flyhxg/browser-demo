## Why

browser-use 是一个强大的 AI 浏览器自动化库，但目前只能通过 Python 脚本使用。需要一个可视化 Web 界面，让用户无需编写代码即可体验 AI 驱动的浏览器自动化，同时支持多种 LLM 和本地/云端两种运行模式。

## What Changes

- 新增 Vue 3 + Vite 前端应用，提供任务输入、实时执行可视化、结果展示界面
- 新增 FastAPI 后端服务，集成 browser-use Agent，提供 REST API 和 WebSocket 通信
- 支持在网页上配置多个 LLM 的 API Key（OpenAI / Claude / Gemini / Ollama / DeepSeek / Groq）
- 支持本地 Chromium 浏览器和 Browser Use Cloud 两种浏览器模式
- 通过 WebSocket 实时推送 Agent 执行步骤、截图和状态
- 支持 Docker 云上部署

## Capabilities

### New Capabilities
- `web-ui`: Vue 3 前端界面，包含设置页（LLM Key 配置、浏览器模式选择）和主页（任务输入、实时执行可视化、结果展示）
- `backend-api`: FastAPI 后端服务，提供配置管理 API、任务执行 API、WebSocket 实时通信
- `llm-config`: 多 LLM 提供商的配置管理，支持 Key 验证、模型选择、Ollama 本地连接检测
- `agent-runner`: 封装 browser-use Agent 的执行引擎，支持多模型切换、步骤回调、截图捕获
- `deployment`: Docker 容器化部署配置，支持本地运行和云上部署两种模式

### Modified Capabilities

## Impact

- 新项目，基于 browser-use 库（`D:\work\browser-use`）构建
- 前端依赖：Vue 3、Vite、WebSocket 客户端
- 后端依赖：FastAPI、browser-use、uvicorn、python-dotenv
- 部署依赖：Docker、Node.js（前端构建）
