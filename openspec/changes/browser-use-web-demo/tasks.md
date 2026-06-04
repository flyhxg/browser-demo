## 1. Project Setup

- [ ] 1.1 Initialize backend directory structure (backend/main.py, backend/api/__init__.py, backend/services/__init__.py)
- [ ] 1.2 Create backend/requirements.txt with dependencies (fastapi, uvicorn, browser-use, python-dotenv, websockets)
- [ ] 1.3 Initialize Vue 3 + Vite frontend project in frontend/ directory
- [ ] 1.4 Configure Vite proxy to forward /api and /ws requests to FastAPI backend (see design.md for proxy config)

## 2. Backend - Configuration Service

- [ ] 2.1 Implement backend/services/config_store.py - load/save config from backend/config.json, API Key masking (show last 4 chars)
- [ ] 2.2 Implement backend/services/llm_factory.py - factory to create ChatOpenAI/ChatAnthropic/ChatGoogle/ChatOllama/ChatDeepSeek/ChatGroq instances (all importable from browser_use top-level), ChatDeepSeek needs default base_url
- [ ] 2.3 Implement backend/api/config.py - REST endpoints: GET /api/config, PUT /api/config/{provider}, POST /api/config/{provider}/validate, GET /api/ollama/check

## 3. Backend - Agent Runner Service

- [ ] 3.1 Implement backend/services/agent_runner.py - Agent execution engine using register_new_step_callback (receives BrowserStateSummary with screenshot), register_done_callback, and agent.stop() for cancellation
- [ ] 3.2 Implement backend/api/tasks.py - REST endpoints: POST /api/tasks (start), POST /api/tasks/cancel
- [ ] 3.3 Implement backend/api/ws.py - WebSocket endpoint at /ws, send JSON messages with type field (step/result/error/cancelled) per protocol in design.md

## 4. Backend - Main Entry

- [ ] 4.1 Implement backend/main.py - FastAPI app with CORS, API router mount, WebSocket route, static file serving for frontend
- [ ] 4.2 Test backend independently: verify config API, start task via API, receive WebSocket events

## 5. Frontend - Foundation

- [ ] 5.1 Setup Vue Router with / (Home) and /settings routes
- [ ] 5.2 Create TypeScript type definitions for API request/response models
- [ ] 5.3 Implement composables/useWebSocket.ts - WebSocket connection management with auto-reconnect
- [ ] 5.4 Implement composables/useAgent.ts - task submission, step state management, cancellation

## 6. Frontend - Settings Page

- [x] 6.1 Implement components/LlmConfigForm.vue - **Decision: intentionally not extracted.** The LLM config is implemented inline in `SettingsView.vue` (the first `<section class="card">` block, lines 3-44 in the current file). Extracting to a separate component would require hoisting 8+ refs (`apiKey`, `baseUrl`, `model`, `protocol`, `validating`, `validResult`, `saveResult`, etc.) and the `save()` / `validate()` handlers via props/events. That adds a props/emit surface for purely organizational gain — `SettingsView.vue` is 416 lines and remains a single coherent page with three configuration cards (LLM / Browser / Trading). When the file grows past ~600 lines or the LLM form needs to be reused elsewhere, this task is the right next step.
- [x] 6.2 Implement SettingsView.vue - LLM config forms for all providers, Ollama connectivity check, browser mode selection
- [x] 6.3 Wire up SettingsView to config API endpoints (load config, save config, validate keys, check Ollama)

## 7. Frontend - Home Page

- [ ] 7.1 Implement components/TaskInput.vue - task textarea, model selector (only configured models), execute/cancel buttons
- [ ] 7.2 Implement components/StepLog.vue - step list with status indicators (pending/running/done/error), action description
- [ ] 7.3 Implement components/ScreenshotView.vue - display base64 screenshot image, update in real-time
- [ ] 7.4 Implement components/ResultDisplay.vue - show final result text and execution metadata
- [ ] 7.5 Implement HomeView.vue - compose TaskInput, StepLog, ScreenshotView, ResultDisplay, wire up with useAgent composable

## 8. Frontend - App Shell

- [ ] 8.1 Implement App.vue - navigation bar with Home/Settings links, app title
- [ ] 8.2 Add basic styling (clean, minimal UI)

## 9. Integration & Deployment

- [ ] 9.1 End-to-end test: configure LLM via settings, run task on home page, verify real-time updates
- [ ] 9.2 Create Dockerfile (multi-stage: Node.js build frontend, Python runtime with Chromium)
- [ ] 9.3 Create docker-compose.yml
- [ ] 9.4 Create README.md with setup and usage instructions
