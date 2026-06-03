# browser-use-web-demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Vue 3 + FastAPI web application that wraps browser-use into a visual demo, letting users configure LLMs, submit browser automation tasks, and watch real-time execution with screenshots.

**Architecture:** Monorepo with Vue 3 + Vite frontend and FastAPI backend. Frontend built to static files served by FastAPI. WebSocket for real-time Agent step/result streaming. JSON file for config persistence. Single concurrent task.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, browser-use, Vue 3, Vite, TypeScript, Vue Router, WebSocket

---

## File Structure

```
browser-demo/
├── backend/
│   ├── main.py                  # FastAPI app entry, CORS, static files, routers
│   ├── config.json              # Runtime config (LLM keys, browser mode)
│   ├── requirements.txt         # Python deps
│   ├── api/
│   │   ├── __init__.py
│   │   ├── config.py            # GET/PUT /api/config, POST /api/config/{provider}/validate, GET /api/ollama/check
│   │   ├── tasks.py             # POST /api/tasks, POST /api/tasks/cancel
│   │   └── ws.py                # WebSocket /ws
│   └── services/
│       ├── __init__.py
│       ├── config_store.py      # Load/save config.json, key masking
│       ├── llm_factory.py       # Create ChatOpenAI/ChatAnthropic/etc. from config
│       └── agent_runner.py      # Wrap browser-use Agent, callbacks, cancellation
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.ts
│       ├── App.vue
│       ├── router.ts
│       ├── types/
│       │   └── index.ts         # TypeScript interfaces for API/WebSocket messages
│       ├── composables/
│       │   ├── useWebSocket.ts  # WebSocket connection + auto-reconnect
│       │   └── useAgent.ts      # Task submit, step state, cancel
│       ├── views/
│       │   ├── HomeView.vue     # Task input + execution visualization + result
│       │   └── SettingsView.vue # LLM config + browser mode
│       └── components/
│           ├── TaskInput.vue
│           ├── StepLog.vue
│           ├── ScreenshotView.vue
│           ├── ResultDisplay.vue
│           └── LlmConfigForm.vue
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `backend/main.py`
- Create: `backend/api/__init__.py`
- Create: `backend/services/__init__.py`
- Create: `backend/requirements.txt`
- Create: `backend/config.json`

- [ ] **Step 1: Create backend directory structure and empty init files**

```bash
mkdir -p backend/api backend/services
```

Create `backend/api/__init__.py`:
```python
```

Create `backend/services/__init__.py`:
```python
```

- [ ] **Step 2: Create backend/requirements.txt**

Create `backend/requirements.txt`:
```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
browser-use>=0.3.0
python-dotenv>=1.0.0
websockets>=12.0
```

- [ ] **Step 3: Create backend/config.json with default empty config**

Create `backend/config.json`:
```json
{
  "providers": {
    "openai": { "api_key": "", "model": "gpt-4o", "configured": false },
    "anthropic": { "api_key": "", "model": "claude-sonnet-4-20250514", "configured": false },
    "google": { "api_key": "", "model": "gemini-2.5-pro", "configured": false },
    "deepseek": { "api_key": "", "model": "deepseek-chat", "configured": false },
    "groq": { "api_key": "", "model": "meta-llama/llama-4-maverick-17b-128e-instruct", "configured": false },
    "ollama": { "url": "http://localhost:11434", "model": "", "configured": false }
  },
  "browser": {
    "mode": "local",
    "cloud_api_key": ""
  }
}
```

- [ ] **Step 4: Create minimal backend/main.py to verify server starts**

Create `backend/main.py`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Browser Use Web Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Install backend dependencies and verify server starts**

Run: `cd backend && pip install -r requirements.txt`
Run: `cd backend && python -c "from main import app; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Initialize Vue 3 + Vite frontend project**

Run:
```bash
cd frontend
npm create vite@latest . -- --template vue-ts
npm install
npm install vue-router@4
```

If the `frontend/` directory already has files, answer prompts to overwrite.

- [ ] **Step 7: Configure Vite proxy for /api and /ws**

Replace `frontend/vite.config.ts`:
```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
```

- [ ] **Step 8: Verify frontend dev server starts**

Run: `cd frontend && npm run dev`
Expected: Vite dev server starts on port 5173

- [ ] **Step 9: Commit**

```bash
git add backend/ frontend/
git commit -m "feat: scaffold backend and frontend project structure"
```

---

### Task 2: Config Store Service

**Files:**
- Create: `backend/services/config_store.py`

- [ ] **Step 1: Write the config store module**

Create `backend/services/config_store.py`:
```python
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config.json"

DEFAULT_CONFIG = {
    "providers": {
        "openai": {"api_key": "", "model": "gpt-4o", "configured": False},
        "anthropic": {"api_key": "", "model": "claude-sonnet-4-20250514", "configured": False},
        "google": {"api_key": "", "model": "gemini-2.5-pro", "configured": False},
        "deepseek": {"api_key": "", "model": "deepseek-chat", "configured": False},
        "groq": {"api_key": "", "model": "meta-llama/llama-4-maverick-17b-128e-instruct", "configured": False},
        "ollama": {"url": "http://localhost:11434", "model": "", "configured": False},
    },
    "browser": {"mode": "local", "cloud_api_key": ""},
}


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return DEFAULT_CONFIG.copy()


def _save_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def get_config() -> dict:
    return _load_config()


def mask_key(key: str) -> str:
    if not key or len(key) <= 4:
        return "****" if key else ""
    return f"****{key[-4:]}"


def get_masked_config() -> dict:
    config = _load_config()
    masked = json.loads(json.dumps(config))  # deep copy
    for name, provider in masked.get("providers", {}).items():
        if name == "ollama":
            continue
        key = provider.get("api_key", "")
        provider["api_key_masked"] = mask_key(key)
        provider["configured"] = bool(key)
        del provider["api_key"]
    return masked


def update_provider(provider_name: str, data: dict) -> dict:
    config = _load_config()
    providers = config.setdefault("providers", {})
    if provider_name not in providers:
        providers[provider_name] = {}
    provider = providers[provider_name]

    if provider_name == "ollama":
        if "url" in data:
            provider["url"] = data["url"]
        if "model" in data:
            provider["model"] = data["model"]
        provider["configured"] = bool(provider.get("model"))
    else:
        if "api_key" in data:
            provider["api_key"] = data["api_key"]
        if "model" in data:
            provider["model"] = data["model"]
        provider["configured"] = bool(provider.get("api_key"))

    _save_config(config)

    result = {}
    if provider_name == "ollama":
        result = {"url": provider.get("url", ""), "model": provider.get("model", ""), "configured": provider["configured"]}
    else:
        result = {"api_key_masked": mask_key(provider.get("api_key", "")), "model": provider.get("model", ""), "configured": provider["configured"]}
    return result


def update_browser_mode(mode: str, cloud_api_key: str = "") -> dict:
    config = _load_config()
    config["browser"] = {"mode": mode, "cloud_api_key": cloud_api_key}
    _save_config(config)
    return config["browser"]


def get_provider_config(provider_name: str) -> dict | None:
    config = _load_config()
    return config.get("providers", {}).get(provider_name)
```

- [ ] **Step 2: Verify config store loads and masks correctly**

Run:
```bash
cd backend && python -c "
from services.config_store import get_masked_config, update_provider, mask_key
print(mask_key('sk-1234567890abcdef'))
print(mask_key(''))
c = get_masked_config()
print(list(c['providers'].keys()))
r = update_provider('openai', {'api_key': 'sk-test12345678', 'model': 'gpt-4o'})
print(r)
"
```
Expected: `****cdef`, ``, provider names list, `{'api_key_masked': '5678', 'model': 'gpt-4o', 'configured': True}`

- [ ] **Step 3: Commit**

```bash
git add backend/services/config_store.py
git commit -m "feat: add config store service with key masking"
```

---

### Task 3: LLM Factory Service

**Files:**
- Create: `backend/services/llm_factory.py`

- [ ] **Step 1: Write the LLM factory module**

Create `backend/services/llm_factory.py`:
```python
from browser_use import (
    ChatAnthropic,
    ChatDeepSeek,
    ChatGoogle,
    ChatGroq,
    ChatOllama,
    ChatOpenAI,
)

from services.config_store import get_provider_config

PROVIDER_CLASS_MAP = {
    "openai": ChatOpenAI,
    "anthropic": ChatAnthropic,
    "google": ChatGoogle,
    "deepseek": ChatDeepSeek,
    "groq": ChatGroq,
    "ollama": ChatOllama,
}


class ProviderNotConfiguredError(Exception):
    pass


def create_llm(provider_name: str) -> ChatOpenAI | ChatAnthropic | ChatGoogle | ChatDeepSeek | ChatGroq | ChatOllama:
    config = get_provider_config(provider_name)
    if not config or not config.get("configured"):
        raise ProviderNotConfiguredError(f"Provider '{provider_name}' is not configured")

    cls = PROVIDER_CLASS_MAP.get(provider_name)
    if not cls:
        raise ValueError(f"Unknown provider: {provider_name}")

    if provider_name == "openai":
        return cls(model=config["model"], api_key=config["api_key"])
    elif provider_name == "anthropic":
        return cls(model=config["model"], api_key=config["api_key"])
    elif provider_name == "google":
        return cls(model=config["model"], api_key=config["api_key"])
    elif provider_name == "deepseek":
        return cls(model=config["model"], api_key=config["api_key"], base_url="https://api.deepseek.com/v1")
    elif provider_name == "groq":
        return cls(model=config["model"], api_key=config["api_key"])
    elif provider_name == "ollama":
        return cls(model=config["model"], host=config["url"])
    else:
        raise ValueError(f"Unhandled provider: {provider_name}")
```

- [ ] **Step 2: Verify factory imports resolve**

Run: `cd backend && python -c "from services.llm_factory import create_llm, PROVIDER_CLASS_MAP; print(list(PROVIDER_CLASS_MAP.keys()))"`
Expected: `['openai', 'anthropic', 'google', 'deepseek', 'groq', 'ollama']`

- [ ] **Step 3: Commit**

```bash
git add backend/services/llm_factory.py
git commit -m "feat: add LLM factory for creating provider instances"
```

---

### Task 4: Agent Runner Service

**Files:**
- Create: `backend/services/agent_runner.py`

- [ ] **Step 1: Write the agent runner module**

Create `backend/services/agent_runner.py`:
```python
import asyncio
import time
from dataclasses import dataclass, field

from browser_use import Agent, BrowserProfile, BrowserSession

from services.config_store import get_config
from services.llm_factory import ProviderNotConfiguredError, create_llm


@dataclass
class StepEvent:
    step: int
    action: str
    target: str
    status: str
    screenshot: str | None = None


@dataclass
class ResultEvent:
    output: str
    steps: int
    duration_ms: int


@dataclass
class ErrorEvent:
    message: str
    step: int


class AgentRunner:
    def __init__(self) -> None:
        self._agent: Agent | None = None
        self._running = False
        self._step_events: list[StepEvent] = []
        self._start_time: float = 0
        self._on_step: list[object] = []  # callbacks set by ws layer
        self._on_result: list[object] = []
        self._on_error: list[object] = []

    @property
    def running(self) -> bool:
        return self._running

    @property
    def step_events(self) -> list[StepEvent]:
        return self._step_events

    def on_step(self, callback) -> None:
        self._on_step.append(callback)

    def on_result(self, callback) -> None:
        self._on_result.append(callback)

    def on_error(self, callback) -> None:
        self._on_error.append(callback)

    async def run(self, task: str, provider: str) -> None:
        if self._running:
            raise RuntimeError("A task is already running")

        self._running = True
        self._step_events = []
        self._start_time = time.time()

        try:
            llm = create_llm(provider)
        except (ProviderNotConfiguredError, ValueError) as e:
            self._running = False
            for cb in self._on_error:
                await cb(ErrorEvent(message=str(e), step=0))
            return

        config = get_config()
        browser_config = config.get("browser", {})
        browser_mode = browser_config.get("mode", "local")

        if browser_mode == "cloud":
            browser_profile = BrowserProfile(use_cloud=True)
            browser_session = BrowserSession(browser_profile=browser_profile)
        else:
            browser_session = BrowserSession()

        async def step_callback(browser_state, agent_output, step_number):
            action_desc = ""
            target_desc = ""
            if agent_output and agent_output.action:
                first_action = agent_output.action[0]
                action_dict = first_action.model_dump() if hasattr(first_action, "model_dump") else {}
                action_name = next(iter(action_dict), "unknown")
                action_desc = action_name
                action_params = action_dict.get(action_name, {})
                target_desc = action_params.get("index", "") or action_params.get("url", "") or ""

            screenshot = browser_state.screenshot if browser_state else None

            event = StepEvent(
                step=step_number,
                action=action_desc,
                target=str(target_desc),
                status="running",
                screenshot=screenshot,
            )
            self._step_events.append(event)
            for cb in self._on_step:
                await cb(event)

        async def done_callback(history):
            duration_ms = int((time.time() - self._start_time) * 1000)
            output = history.final_result() or ""
            steps = history.number_of_steps()

            result = ResultEvent(output=str(output), steps=steps, duration_ms=duration_ms)
            for cb in self._on_result:
                await cb(result)

            self._running = False

        try:
            self._agent = Agent(
                task=task,
                llm=llm,
                browser_session=browser_session,
                register_new_step_callback=step_callback,
                register_done_callback=done_callback,
            )
            await self._agent.run()
        except Exception as e:
            duration_ms = int((time.time() - self._start_time) * 1000)
            for cb in self._on_error:
                await cb(ErrorEvent(message=str(e), step=len(self._step_events)))
            self._running = False
        finally:
            self._agent = None

    async def cancel(self) -> None:
        if self._agent:
            self._agent.stop()
            self._running = False


runner = AgentRunner()
```

- [ ] **Step 2: Verify agent runner module imports**

Run: `cd backend && python -c "from services.agent_runner import runner; print(type(runner).__name__)"`
Expected: `AgentRunner`

- [ ] **Step 3: Commit**

```bash
git add backend/services/agent_runner.py
git commit -m "feat: add agent runner with step/done callbacks and cancellation"
```

---

### Task 5: Backend API Endpoints

**Files:**
- Create: `backend/api/config.py`
- Create: `backend/api/tasks.py`
- Create: `backend/api/ws.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Write config API endpoints**

Create `backend/api/config.py`:
```python
import httpx
from fastapi import APIRouter, HTTPException

from services.config_store import (
    get_masked_config,
    update_browser_mode,
    update_provider,
)

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def get_config():
    return get_masked_config()


@router.put("/{provider}")
async def set_provider_config(provider: str, data: dict):
    valid_providers = ["openai", "anthropic", "google", "deepseek", "groq", "ollama"]
    if provider not in valid_providers:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
    result = update_provider(provider, data)
    return result


@router.post("/{provider}/validate")
async def validate_provider(provider: str):
    from services.llm_factory import create_llm, ProviderNotConfiguredError

    try:
        llm = create_llm(provider)
    except ProviderNotConfiguredError:
        raise HTTPException(status_code=400, detail=f"Provider '{provider}' is not configured")

    try:
        if provider == "ollama":
            config = get_masked_config()
            ollama_url = config.get("providers", {}).get("ollama", {}).get("url", "http://localhost:11434")
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{ollama_url}/api/tags", timeout=5)
                resp.raise_for_status()
                models = [m["name"] for m in resp.json().get("models", [])]
                return {"valid": True, "models": models}
        else:
            result = await llm.ainvoke(
                [{"role": "user", "content": "Hi"}],
            )
            return {"valid": True}
    except Exception as e:
        return {"valid": False, "error": str(e)}


@router.put("/browser-mode")
async def set_browser_mode(data: dict):
    mode = data.get("mode", "local")
    cloud_key = data.get("cloud_api_key", "")
    if mode not in ("local", "cloud"):
        raise HTTPException(status_code=400, detail="Mode must be 'local' or 'cloud'")
    result = update_browser_mode(mode, cloud_key)
    return result


@router.get("/ollama/check")
async def check_ollama(url: str = "http://localhost:11434"):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{url}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            return {"connected": True, "models": models}
    except Exception as e:
        return {"connected": False, "error": str(e)}
```

- [ ] **Step 2: Write tasks API endpoints**

Create `backend/api/tasks.py`:
```python
from fastapi import APIRouter, HTTPException

from services.agent_runner import runner

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("")
async def start_task(data: dict):
    if runner.running:
        raise HTTPException(status_code=409, detail="A task is already running")

    task = data.get("task", "").strip()
    provider = data.get("provider", "").strip()

    if not task:
        raise HTTPException(status_code=400, detail="Task description is required")
    if not provider:
        raise HTTPException(status_code=400, detail="Provider is required")

    import asyncio
    asyncio.create_task(runner.run(task, provider))

    return {"status": "started"}


@router.post("/cancel")
async def cancel_task():
    if not runner.running:
        raise HTTPException(status_code=400, detail="No task is running")
    await runner.cancel()
    return {"status": "cancelled"}
```

- [ ] **Step 3: Write WebSocket endpoint**

Create `backend/api/ws.py`:
```python
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.agent_runner import StepEvent, ResultEvent, ErrorEvent, runner

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    async def on_step(event: StepEvent):
        await ws.send_json({
            "type": "step",
            "data": {
                "step": event.step,
                "action": event.action,
                "target": event.target,
                "status": event.status,
                "screenshot": event.screenshot,
            },
        })

    async def on_result(event: ResultEvent):
        await ws.send_json({
            "type": "result",
            "data": {
                "output": event.output,
                "steps": event.steps,
                "duration_ms": event.duration_ms,
            },
        })

    async def on_error(event: ErrorEvent):
        await ws.send_json({
            "type": "error",
            "data": {
                "message": event.message,
                "step": event.step,
            },
        })

    runner.on_step(on_step)
    runner.on_result(on_result)
    runner.on_error(on_error)

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
```

- [ ] **Step 4: Wire everything into backend/main.py**

Replace `backend/main.py`:
```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.config import router as config_router
from api.tasks import router as tasks_router
from api.ws import router as ws_router

app = FastAPI(title="Browser Use Web Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(config_router)
app.include_router(tasks_router)
app.include_router(ws_router)

# Serve frontend static files in production
STATIC_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Verify backend server starts with all routes**

Run: `cd backend && python -c "from main import app; routes = [r.path for r in app.routes]; print(sorted(routes))"`
Expected: list containing `/api/config`, `/api/config/{provider}`, `/api/tasks`, `/ws`, etc.

- [ ] **Step 6: Commit**

```bash
git add backend/api/ backend/main.py
git commit -m "feat: add backend API endpoints for config, tasks, and WebSocket"
```

---

### Task 6: Frontend Types and Composables

**Files:**
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/composables/useWebSocket.ts`
- Create: `frontend/src/composables/useAgent.ts`
- Create: `frontend/src/router.ts`
- Modify: `frontend/src/main.ts`

- [ ] **Step 1: Create TypeScript type definitions**

Create `frontend/src/types/index.ts`:
```ts
export interface ProviderConfig {
  model: string
  configured: boolean
}

export interface OpenAIConfig extends ProviderConfig {
  api_key_masked: string
}

export interface AnthropicConfig extends ProviderConfig {
  api_key_masked: string
}

export interface GoogleConfig extends ProviderConfig {
  api_key_masked: string
}

export interface DeepSeekConfig extends ProviderConfig {
  api_key_masked: string
}

export interface GroqConfig extends ProviderConfig {
  api_key_masked: string
}

export interface OllamaConfig extends ProviderConfig {
  url: string
}

export interface AppConfig {
  providers: {
    openai: OpenAIConfig
    anthropic: AnthropicConfig
    google: GoogleConfig
    deepseek: DeepSeekConfig
    groq: GroqConfig
    ollama: OllamaConfig
  }
  browser: {
    mode: 'local' | 'cloud'
    cloud_api_key: string
  }
}

export interface StepData {
  step: number
  action: string
  target: string
  status: 'running' | 'done' | 'error'
  screenshot: string | null
}

export interface ResultData {
  output: string
  steps: number
  duration_ms: number
}

export interface ErrorData {
  message: string
  step: number
}

export interface WsMessage {
  type: 'step' | 'result' | 'error' | 'cancelled'
  data: StepData | ResultData | ErrorData | Record<string, never>
}
```

- [ ] **Step 2: Create useWebSocket composable**

Create `frontend/src/composables/useWebSocket.ts`:
```ts
import { ref, onUnmounted } from 'vue'
import type { WsMessage } from '../types'

export function useWebSocket() {
  const connected = ref(false)
  const lastMessage = ref<WsMessage | null>(null)
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  function connect() {
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
      scheduleReconnect()
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
    if (reconnectTimer) clearTimeout(reconnectTimer)
    ws?.close()
    ws = null
  }

  connect()

  onUnmounted(disconnect)

  return { connected, lastMessage, disconnect }
}
```

- [ ] **Step 3: Create useAgent composable**

Create `frontend/src/composables/useAgent.ts`:
```ts
import { ref, computed } from 'vue'
import type { StepData, ResultData, ErrorData } from '../types'

export function useAgent() {
  const steps = ref<StepData[]>([])
  const result = ref<ResultData | null>(null)
  const error = ref<ErrorData | null>(null)
  const running = ref(false)
  const screenshot = ref<string | null>(null)

  const activeProvider = computed(() =>
    steps.value.length > 0 ? 'running' : ''
  )

  function reset() {
    steps.value = []
    result.value = null
    error.value = null
    running.value = false
    screenshot.value = null
  }

  async function startTask(task: string, provider: string) {
    reset()
    running.value = true
    const resp = await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task, provider }),
    })
    if (!resp.ok) {
      const data = await resp.json()
      running.value = false
      error.value = { message: data.detail || 'Failed to start task', step: 0 }
      return
    }
  }

  async function cancelTask() {
    await fetch('/api/tasks/cancel', { method: 'POST' })
    running.value = false
  }

  function handleWsMessage(msg: { type: string; data: unknown }) {
    if (msg.type === 'step') {
      const stepData = msg.data as StepData
      // Update existing step or add new
      const idx = steps.value.findIndex((s) => s.step === stepData.step)
      if (idx >= 0) {
        steps.value[idx] = stepData
      } else {
        steps.value.push(stepData)
      }
      if (stepData.screenshot) {
        screenshot.value = stepData.screenshot
      }
    } else if (msg.type === 'result') {
      result.value = msg.data as ResultData
      running.value = false
      // Mark all steps as done
      steps.value.forEach((s) => (s.status = 'done'))
    } else if (msg.type === 'error') {
      error.value = msg.data as ErrorData
      running.value = false
    } else if (msg.type === 'cancelled') {
      running.value = false
    }
  }

  return {
    steps,
    result,
    error,
    running,
    screenshot,
    startTask,
    cancelTask,
    handleWsMessage,
    reset,
  }
}
```

- [ ] **Step 4: Create Vue Router config**

Create `frontend/src/router.ts`:
```ts
import { createRouter, createWebHistory } from 'vue-router'
import HomeView from './views/HomeView.vue'
import SettingsView from './views/SettingsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/settings', name: 'settings', component: SettingsView },
  ],
})

export default router
```

- [ ] **Step 5: Update main.ts to use router**

Replace `frontend/src/main.ts`:
```ts
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(router)
app.mount('#app')
```

- [ ] **Step 6: Verify frontend compiles**

Run: `cd frontend && npx vue-tsc --noEmit 2>&1 || echo "Type check done"`
Expected: no critical errors (may have warnings about missing view files — that's OK for now)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat: add frontend types, composables, and router"
```

---

### Task 7: Settings Page

**Files:**
- Create: `frontend/src/components/LlmConfigForm.vue`
- Create: `frontend/src/views/SettingsView.vue`

- [ ] **Step 1: Create LlmConfigForm component**

Create `frontend/src/components/LlmConfigForm.vue`:
```vue
<template>
  <div class="llm-config-form">
    <h3>{{ label }}</h3>
    <div class="form-row">
      <label>API Key</label>
      <input
        v-model="apiKey"
        type="password"
        :placeholder="placeholder"
        @blur="save"
      />
      <span v-if="configured" class="badge ok">Configured</span>
      <span v-else class="badge no">Not configured</span>
    </div>
    <div class="form-row">
      <label>Model</label>
      <input v-model="model" @blur="save" />
    </div>
    <div class="form-row">
      <button @click="validate" :disabled="!apiKey">Validate</button>
      <span v-if="validating">Checking...</span>
      <span v-if="validResult === true" class="ok">Valid</span>
      <span v-if="validResult === false" class="err">Invalid</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const props = defineProps<{
  provider: string
  label: string
  configured: boolean
  maskedKey: string
  model: string
}>()

const emit = defineEmits<{
  save: [provider: string, data: Record<string, string>]
  validate: [provider: string]
}>()

const apiKey = ref('')
const model = ref(props.model)
const validating = ref(false)
const validResult = ref<boolean | null>(null)

const placeholder = props.configured ? props.maskedKey : 'Enter API key'

onMounted(() => {
  model.value = props.model
})

async function save() {
  const data: Record<string, string> = { model: model.value }
  if (apiKey.value) {
    data.api_key = apiKey.value
  }
  emit('save', props.provider, data)
}

async function validate() {
  // Save first
  await save()
  validating.value = true
  validResult.value = null
  emit('validate', props.provider)
}
</script>

<style scoped>
.llm-config-form {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
h3 {
  margin: 0 0 12px;
}
.form-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
label {
  min-width: 70px;
  font-weight: 500;
}
input {
  flex: 1;
  padding: 6px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
button {
  padding: 6px 16px;
  border: 1px solid #ccc;
  border-radius: 4px;
  cursor: pointer;
  background: #f5f5f5;
}
button:hover { background: #eee; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
.badge { font-size: 12px; padding: 2px 8px; border-radius: 4px; }
.badge.ok { background: #d4edda; color: #155724; }
.badge.no { background: #f8d7da; color: #721c24; }
.ok { color: #155724; }
.err { color: #721c24; }
</style>
```

- [ ] **Step 2: Create SettingsView**

Create `frontend/src/views/SettingsView.vue`:
```vue
<template>
  <div class="settings">
    <h2>Settings</h2>

    <section>
      <h3>LLM Providers</h3>
      <LlmConfigForm
        v-for="p in apiProviders"
        :key="p.name"
        :provider="p.name"
        :label="p.label"
        :configured="p.config.configured"
        :masked-key="p.config.api_key_masked"
        :model="p.config.model"
        @save="saveProvider"
        @validate="validateProvider"
      />

      <!-- Ollama special form -->
      <div class="llm-config-form">
        <h3>Ollama</h3>
        <div class="form-row">
          <label>Server URL</label>
          <input v-model="ollamaUrl" @blur="saveOllama" />
          <button @click="checkOllama">Check</button>
          <span v-if="ollamaChecking">Checking...</span>
          <span v-if="ollamaConnected" class="ok">Connected</span>
        </div>
        <div class="form-row">
          <label>Model</label>
          <select v-model="ollamaModel" @change="saveOllama">
            <option value="" disabled>Select a model</option>
            <option v-for="m in ollamaModels" :key="m" :value="m">{{ m }}</option>
          </select>
        </div>
        <div class="form-row">
          <span v-if="config?.providers.ollama.configured" class="badge ok">Configured</span>
          <span v-else class="badge no">Not configured</span>
        </div>
      </div>
    </section>

    <section>
      <h3>Browser Mode</h3>
      <div class="form-row">
        <label>
          <input type="radio" v-model="browserMode" value="local" @change="saveBrowserMode" />
          Local Chromium
        </label>
        <label>
          <input type="radio" v-model="browserMode" value="cloud" @change="saveBrowserMode" />
          Browser Use Cloud
        </label>
      </div>
      <div v-if="browserMode === 'cloud'" class="form-row">
        <label>Cloud API Key</label>
        <input v-model="cloudApiKey" type="password" @blur="saveBrowserMode" />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import LlmConfigForm from '../components/LlmConfigForm.vue'
import type { AppConfig } from '../types'

const config = ref<AppConfig | null>(null)
const browserMode = ref('local')
const cloudApiKey = ref('')
const ollamaUrl = ref('http://localhost:11434')
const ollamaModel = ref('')
const ollamaModels = ref<string[]>([])
const ollamaChecking = ref(false)
const ollamaConnected = ref(false)

const apiProviders = computed(() => {
  if (!config.value) return []
  const providers = config.value.providers
  return [
    { name: 'openai', label: 'OpenAI', config: providers.openai },
    { name: 'anthropic', label: 'Claude', config: providers.anthropic },
    { name: 'google', label: 'Gemini', config: providers.google },
    { name: 'deepseek', label: 'DeepSeek', config: providers.deepseek },
    { name: 'groq', label: 'Groq', config: providers.groq },
  ]
})

async function loadConfig() {
  const resp = await fetch('/api/config')
  config.value = await resp.json()
  browserMode.value = config.value?.browser.mode || 'local'
  cloudApiKey.value = config.value?.browser.cloud_api_key || ''
  ollamaUrl.value = config.value?.providers.ollama.url || 'http://localhost:11434'
  ollamaModel.value = config.value?.providers.ollama.model || ''
}

async function saveProvider(provider: string, data: Record<string, string>) {
  await fetch(`/api/config/${provider}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  await loadConfig()
}

async function validateProvider(provider: string) {
  const resp = await fetch(`/api/config/${provider}/validate`, { method: 'POST' })
  const data = await resp.json()
  if (!data.valid) {
    alert(`Validation failed: ${data.error}`)
  } else {
    alert('Valid!')
  }
  await loadConfig()
}

async function checkOllama() {
  ollamaChecking.value = true
  ollamaConnected.value = false
  try {
    const resp = await fetch(`/api/config/ollama/check?url=${encodeURIComponent(ollamaUrl.value)}`)
    const data = await resp.json()
    ollamaConnected.value = data.connected
    ollamaModels.value = data.models || []
  } catch {
    ollamaConnected.value = false
  }
  ollamaChecking.value = false
}

async function saveOllama() {
  await fetch('/api/config/ollama', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: ollamaUrl.value, model: ollamaModel.value }),
  })
  await loadConfig()
}

async function saveBrowserMode() {
  await fetch('/api/config/browser-mode', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: browserMode.value, cloud_api_key: cloudApiKey.value }),
  })
}

onMounted(loadConfig)
</script>

<style scoped>
.settings { max-width: 700px; margin: 0 auto; padding: 24px; }
h2 { margin-bottom: 24px; }
section { margin-bottom: 32px; }
h3 { margin-bottom: 16px; }
.form-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
label { min-width: 100px; font-weight: 500; }
input, select {
  padding: 6px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
button {
  padding: 6px 16px;
  border: 1px solid #ccc;
  border-radius: 4px;
  cursor: pointer;
  background: #f5f5f5;
}
button:hover { background: #eee; }
.badge { font-size: 12px; padding: 2px 8px; border-radius: 4px; }
.badge.ok { background: #d4edda; color: #155724; }
.badge.no { background: #f8d7da; color: #721c24; }
.ok { color: #155724; }
.err { color: #721c24; }
</style>
```

- [ ] **Step 3: Verify frontend compiles**

Run: `cd frontend && npx vue-tsc --noEmit 2>&1 | head -20`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/LlmConfigForm.vue frontend/src/views/SettingsView.vue
git commit -m "feat: add settings page with LLM config and browser mode"
```

---

### Task 8: Home Page Components

**Files:**
- Create: `frontend/src/components/TaskInput.vue`
- Create: `frontend/src/components/StepLog.vue`
- Create: `frontend/src/components/ScreenshotView.vue`
- Create: `frontend/src/components/ResultDisplay.vue`

- [ ] **Step 1: Create TaskInput component**

Create `frontend/src/components/TaskInput.vue`:
```vue
<template>
  <div class="task-input">
    <textarea
      v-model="task"
      placeholder="Describe the browser task you want the AI to perform..."
      rows="3"
      :disabled="running"
    ></textarea>
    <div class="controls">
      <select v-model="provider" :disabled="running">
        <option value="" disabled>Select model</option>
        <option
          v-for="p in configuredProviders"
          :key="p.name"
          :value="p.name"
        >
          {{ p.label }} ({{ p.model }})
        </option>
      </select>
      <button v-if="!running" @click="execute" :disabled="!task || !provider">
        Execute
      </button>
      <button v-else @click="cancel" class="cancel">Cancel</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import type { AppConfig } from '../types'

const props = defineProps<{ running: boolean }>()
const emit = defineEmits<{
  execute: [task: string, provider: string]
  cancel: []
}>()

const task = ref('')
const provider = ref('')
const config = ref<AppConfig | null>(null)

const configuredProviders = computed(() => {
  if (!config.value) return []
  const providers = config.value.providers
  const result: { name: string; label: string; model: string }[] = []
  const map: Record<string, string> = {
    openai: 'OpenAI',
    anthropic: 'Claude',
    google: 'Gemini',
    deepseek: 'DeepSeek',
    groq: 'Groq',
    ollama: 'Ollama',
  }
  for (const [key, p] of Object.entries(providers)) {
    if (p.configured) {
      result.push({ name: key, label: map[key] || key, model: p.model })
    }
  }
  return result
})

async function loadConfig() {
  const resp = await fetch('/api/config')
  config.value = await resp.json()
}

function execute() {
  if (task.value && provider.value) {
    emit('execute', task.value, provider.value)
  }
}

function cancel() {
  emit('cancel')
}

onMounted(loadConfig)
</script>

<style scoped>
.task-input { margin-bottom: 20px; }
textarea {
  width: 100%;
  padding: 10px;
  border: 1px solid #ccc;
  border-radius: 6px;
  resize: vertical;
  font-size: 14px;
  box-sizing: border-box;
}
.controls {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
select {
  padding: 8px 12px;
  border: 1px solid #ccc;
  border-radius: 4px;
  min-width: 200px;
}
button {
  padding: 8px 20px;
  border: 1px solid #ccc;
  border-radius: 4px;
  cursor: pointer;
  background: #4a9eff;
  color: white;
  font-weight: 500;
}
button:disabled { opacity: 0.5; cursor: not-allowed; }
button:hover:not(:disabled) { background: #3a8eef; }
button.cancel { background: #ff4a4a; }
button.cancel:hover { background: #ef3a3a; }
</style>
```

- [ ] **Step 2: Create StepLog component**

Create `frontend/src/components/StepLog.vue`:
```vue
<template>
  <div class="step-log">
    <h3>Steps</h3>
    <div v-if="steps.length === 0" class="empty">No steps yet</div>
    <div v-for="step in steps" :key="step.step" class="step-item">
      <span class="step-num">{{ step.step }}</span>
      <span :class="['status', step.status]">{{ statusIcon(step.status) }}</span>
      <span class="action">{{ step.action }}</span>
      <span v-if="step.target" class="target">{{ step.target }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { StepData } from '../types'

defineProps<{ steps: StepData[] }>()

function statusIcon(status: string): string {
  switch (status) {
    case 'running': return '...'
    case 'done': return 'done'
    case 'error': return 'error'
    default: return '-'
  }
}
</script>

<style scoped>
.step-log {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 12px;
  max-height: 300px;
  overflow-y: auto;
}
h3 { margin: 0 0 8px; }
.empty { color: #999; font-style: italic; }
.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid #f0f0f0;
}
.step-num { font-weight: 600; min-width: 24px; }
.status { font-size: 12px; padding: 2px 6px; border-radius: 3px; }
.status.running { background: #fff3cd; color: #856404; }
.status.done { background: #d4edda; color: #155724; }
.status.error { background: #f8d7da; color: #721c24; }
.action { font-weight: 500; }
.target { color: #666; font-size: 13px; }
</style>
```

- [ ] **Step 3: Create ScreenshotView component**

Create `frontend/src/components/ScreenshotView.vue`:
```vue
<template>
  <div class="screenshot-view">
    <h3>Browser View</h3>
    <div v-if="screenshot" class="screenshot-container">
      <img :src="'data:image/png;base64,' + screenshot" alt="Browser screenshot" />
    </div>
    <div v-else class="empty">No screenshot yet</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ screenshot: string | null }>()
</script>

<style scoped>
.screenshot-view {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 12px;
}
h3 { margin: 0 0 8px; }
.screenshot-container {
  overflow: hidden;
  border-radius: 4px;
  border: 1px solid #eee;
}
img {
  width: 100%;
  height: auto;
  display: block;
}
.empty { color: #999; font-style: italic; text-align: center; padding: 40px; }
</style>
```

- [ ] **Step 4: Create ResultDisplay component**

Create `frontend/src/components/ResultDisplay.vue`:
```vue
<template>
  <div v-if="result || error" class="result-display">
    <div v-if="error" class="error-box">
      <h3>Error</h3>
      <p>{{ error.message }}</p>
    </div>
    <div v-else-if="result" class="result-box">
      <h3>Result</h3>
      <p>{{ result.output }}</p>
      <div class="meta">
        <span>Steps: {{ result.steps }}</span>
        <span>Duration: {{ (result.duration_ms / 1000).toFixed(1) }}s</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ResultData, ErrorData } from '../types'

defineProps<{ result: ResultData | null; error: ErrorData | null }>()
</script>

<style scoped>
.result-display { margin-top: 16px; }
.result-box, .error-box {
  border-radius: 8px;
  padding: 16px;
}
.result-box { background: #d4edda; border: 1px solid #c3e6cb; }
.error-box { background: #f8d7da; border: 1px solid #f5c6cb; }
h3 { margin: 0 0 8px; }
p { margin: 0; white-space: pre-wrap; }
.meta {
  margin-top: 8px;
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #666;
}
</style>
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/
git commit -m "feat: add TaskInput, StepLog, ScreenshotView, ResultDisplay components"
```

---

### Task 9: Home View and App Shell

**Files:**
- Create: `frontend/src/views/HomeView.vue`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Create HomeView**

Create `frontend/src/views/HomeView.vue`:
```vue
<template>
  <div class="home">
    <TaskInput
      :running="running"
      @execute="onExecute"
      @cancel="onCancel"
    />
    <div class="execution-area">
      <div class="left">
        <StepLog :steps="steps" />
      </div>
      <div class="right">
        <ScreenshotView :screenshot="screenshot" />
      </div>
    </div>
    <ResultDisplay :result="result" :error="error" />
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import TaskInput from '../components/TaskInput.vue'
import StepLog from '../components/StepLog.vue'
import ScreenshotView from '../components/ScreenshotView.vue'
import ResultDisplay from '../components/ResultDisplay.vue'
import { useAgent } from '../composables/useAgent'
import { useWebSocket } from '../composables/useWebSocket'

const { steps, result, error, running, screenshot, startTask, cancelTask, handleWsMessage } = useAgent()
const { lastMessage } = useWebSocket()

watch(lastMessage, (msg) => {
  if (msg) handleWsMessage(msg)
})

async function onExecute(task: string, provider: string) {
  await startTask(task, provider)
}

async function onCancel() {
  await cancelTask()
}
</script>

<style scoped>
.home { max-width: 1000px; margin: 0 auto; padding: 24px; }
.execution-area {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}
@media (max-width: 768px) {
  .execution-area { grid-template-columns: 1fr; }
}
</style>
```

- [ ] **Step 2: Update App.vue with navigation**

Replace `frontend/src/App.vue`:
```vue
<template>
  <div id="app">
    <nav>
      <router-link to="/">Home</router-link>
      <router-link to="/settings">Settings</router-link>
    </nav>
    <main>
      <router-view />
    </main>
  </div>
</template>

<style>
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #fafafa;
  color: #333;
}
nav {
  display: flex;
  gap: 16px;
  padding: 12px 24px;
  background: #fff;
  border-bottom: 1px solid #e0e0e0;
}
nav a {
  text-decoration: none;
  color: #555;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 4px;
}
nav a:hover { background: #f0f0f0; }
nav a.router-link-active { color: #4a9eff; }
main { min-height: calc(100vh - 50px); }
</style>
```

- [ ] **Step 3: Clean up default Vite files**

Delete `frontend/src/components/HelloWorld.vue` and `frontend/src/style.css` if they exist. Remove any import of `style.css` from `main.ts`.

- [ ] **Step 4: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds, `frontend/dist/` created

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "feat: add HomeView and App shell with navigation"
```

---

### Task 10: Integration and Deployment

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `README.md`

- [ ] **Step 1: Create Dockerfile**

Create `Dockerfile`:
```dockerfile
# Stage 1: Build frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.11-slim
WORKDIR /app

# Install Chromium
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-common \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_PATH=/usr/bin/chromium

# Install Python dependencies
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

WORKDIR /app/backend
EXPOSE 8000
CMD ["python", "main.py"]
```

- [ ] **Step 2: Create docker-compose.yml**

Create `docker-compose.yml`:
```yaml
services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - CHROME_PATH=/usr/bin/chromium
```

- [ ] **Step 3: Update backend/main.py with uvicorn run block**

Add at the end of `backend/main.py`:
```python
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
```

- [ ] **Step 4: Create README.md**

Create `README.md`:
```markdown
# Browser Use Web Demo

A web interface for [browser-use](https://github.com/browser-use/browser-use) AI browser automation.

## Quick Start

### Local Development

1. Install backend dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. Start the backend:
   ```bash
   cd backend
   python main.py
   ```

3. Start the frontend dev server (separate terminal):
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

4. Open http://localhost:5173

### Docker

```bash
docker-compose up
```

Open http://localhost:8000

## Usage

1. Go to **Settings** and configure at least one LLM provider
2. Go to **Home**, type a task, select a model, and click Execute
3. Watch the AI browser automation run in real-time
```

- [ ] **Step 5: End-to-end smoke test**

Start backend: `cd backend && python main.py`
Start frontend: `cd frontend && npm run dev`
Open http://localhost:5173/settings — configure a provider
Open http://localhost:5173 — submit a task
Verify WebSocket steps appear and screenshot updates

- [ ] **Step 6: Commit**

```bash
git add Dockerfile docker-compose.yml README.md backend/main.py
git commit -m "feat: add Docker deployment and README"
```
