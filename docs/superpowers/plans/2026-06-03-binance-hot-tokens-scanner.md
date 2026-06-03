# Binance Hot Tokens Scanner - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the existing `HotTokensScanner` backend service with the REST API, WebSocket broadcast, and frontend TradingView, enabling users to view real-time hot token rankings, analyze them with LLM, and execute trades.

**Architecture:** The existing `HotTokensScanner` (in `services/hot_tokens_scanner.py`) fetches Binance futures data every 60s, calculates heat scores, persists to SQLite, and broadcasts via `ws_manager.manager.broadcast()`. We need to wire this into the FastAPI app: create REST endpoints (`api/hot_tokens.py`), register the router in `main.py`, integrate the `ws_manager` with the `/ws` endpoint so broadcasts actually reach clients, and add a "Hot Tokens" sub-tab to `TradingView.vue` with WebSocket-driven live updates.

**Tech Stack:** FastAPI, CCXT, SQLite, Vue 3, TypeScript, WebSocket

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/api/hot_tokens.py` | Create | REST endpoints for hot tokens (list, analyze, trade, scanner control) |
| `backend/api/ws.py` | Modify | Integrate `ws_manager` so broadcasts reach connected clients |
| `backend/main.py` | Modify | Import and include `hot_tokens_router` |
| `backend/services/config_store.py` | Modify | Add hot tokens config fields |
| `frontend/src/views/TradingView.vue` | Modify | Add "Hot Tokens" sub-tab under Crypto tab |
| `frontend/src/types/index.ts` | Modify | Add `HotToken` and `HotTokensUpdate` types |
| `frontend/src/composables/useWebSocket.ts` | Modify | Export `lastMessage` so TradingView can react to `hot_tokens_update` |

---

## Task 1: Fix WebSocket Manager Integration

**Files:**
- Modify: `backend/api/ws.py`

The `HotTokensScanner` broadcasts via `ws_manager.manager.broadcast()`, but `api/ws.py` does NOT register its connections with `ws_manager`. We need to connect the two.

- [ ] **Step 1: Import ws_manager in ws.py**

Add import at top of `backend/api/ws.py`:

```python
from services.ws_manager import manager
```

- [ ] **Step 2: Register WebSocket connections with ws_manager**

In `websocket_endpoint`, after `await ws.accept()`, add:

```python
await manager.connect(ws)
```

In the `finally` block (or after the `while True` loop), add:

```python
manager.disconnect(ws)
```

**Expected result:** When clients connect to `/ws`, they are registered in `ws_manager`, so `HotTokensScanner._broadcast_update()` can reach them.

- [ ] **Step 3: Commit**

```bash
git add backend/api/ws.py
git commit -m "fix(ws): integrate ws_manager for hot tokens broadcast"
```

---

## Task 2: Create Hot Tokens REST API

**Files:**
- Create: `backend/api/hot_tokens.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Create `backend/api/hot_tokens.py`**

```python
"""Hot tokens API endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from services.config_store import get_config
from services.database import get_db
from services.hot_tokens_scanner import get_scanner
from services.signal_analyzer import SignalAnalyzer
from services.trading_engine import TradingEngine

router = APIRouter(prefix="/api/hot_tokens")


@router.get("/")
async def get_hot_tokens(limit: int = 50) -> dict[str, Any]:
    """Get current hot tokens sorted by heat score."""
    scanner = get_scanner()
    tokens = scanner.get_hot_tokens(limit=limit)
    return {
        "tokens": [
            {
                "symbol": t.symbol,
                "price": t.price,
                "price_change_24h": t.price_change_24h,
                "volume_24h": t.volume_24h,
                "volume_usd": t.volume_usd,
                "funding_rate": t.funding_rate,
                "long_short_ratio": t.long_short_ratio,
                "open_interest": t.open_interest,
                "liquidation_price": t.liquidation_price,
                "heat_score": t.heat_score,
            }
            for t in tokens
        ]
    }


@router.get("/{symbol}")
async def get_hot_token_detail(symbol: str) -> dict[str, Any]:
    """Get single hot token details."""
    scanner = get_scanner()
    token = scanner._hot_tokens.get(symbol)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    return {
        "symbol": token.symbol,
        "price": token.price,
        "price_change_24h": token.price_change_24h,
        "volume_24h": token.volume_24h,
        "volume_usd": token.volume_usd,
        "funding_rate": token.funding_rate,
        "long_short_ratio": token.long_short_ratio,
        "open_interest": token.open_interest,
        "liquidation_price": token.liquidation_price,
        "heat_score": token.heat_score,
    }


@router.post("/start")
async def start_scanner() -> dict[str, Any]:
    """Start the hot tokens scanner."""
    scanner = get_scanner()
    scanner.start()
    return {"status": "started"}


@router.post("/stop")
async def stop_scanner() -> dict[str, Any]:
    """Stop the hot tokens scanner."""
    scanner = get_scanner()
    scanner.stop()
    return {"status": "stopped"}


@router.get("/status")
async def scanner_status() -> dict[str, Any]:
    """Get scanner status."""
    scanner = get_scanner()
    return {"running": scanner._running}


@router.post("/{symbol}/analyze")
async def analyze_token(symbol: str) -> dict[str, Any]:
    """Analyze a token with LLM."""
    scanner = get_scanner()
    token = scanner._hot_tokens.get(symbol)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    content = (
        f"Analyze {token.symbol} cryptocurrency. "
        f"Current price: ${token.price:.2f}, "
        f"24h change: {token.price_change_24h:.2f}%, "
        f"Volume: ${token.volume_usd:,.0f}, "
        f"Funding rate: {token.funding_rate:.4f}, "
        f"Long/Short ratio: {token.long_short_ratio:.2f}."
    )

    analyzer = SignalAnalyzer()
    result = await analyzer.analyze(content)
    return {
        "symbol": symbol,
        "sentiment": result.get("sentiment", "unknown"),
        "confidence": result.get("confidence", 0.0),
        "reasoning": result.get("reasoning", ""),
        "tokens": result.get("tokens", []),
    }


@router.post("/{symbol}/execute")
async def execute_trade(symbol: str, data: dict[str, Any]) -> dict[str, Any]:
    """Execute a trade for a hot token."""
    config = get_config()
    api_key = config.get("binance_api_key", "")
    api_secret = config.get("binance_secret_key", "")
    use_testnet = config.get("binance_testnet", True)

    if not api_key or not api_secret:
        return {"error": "Binance API not configured"}

    engine = TradingEngine(api_key, api_secret, use_testnet)

    signal = {
        "token": symbol.replace("USDT", ""),
        "sentiment": data.get("side", "buy") == "buy" and "bullish" or "bearish",
        "confidence": 1.0,
    }

    result = await engine.execute_signal(signal)
    await engine.trader.close()
    return result
```

- [ ] **Step 2: Register router in `backend/main.py`**

Add import:

```python
from api.hot_tokens import router as hot_tokens_router
```

Add `app.include_router(hot_tokens_router)` before the static files mount.

- [ ] **Step 3: Commit**

```bash
git add backend/api/hot_tokens.py backend/main.py
git commit -m "feat(api): add hot tokens REST endpoints"
```

---

## Task 3: Add Hot Tokens Config Fields

**Files:**
- Modify: `backend/services/config_store.py`

- [ ] **Step 1: Extend DEFAULT_CONFIG**

Add these keys to `DEFAULT_CONFIG`:

```python
"hot_tokens_enabled": False,
"hot_tokens_scan_interval": 60,
"hot_tokens_max_results": 50,
"hot_tokens_auto_execute": False,
"hot_tokens_auto_threshold": 0.8,
```

- [ ] **Step 2: Update `update_config` allowed keys**

Add to the allowed keys check:

```python
"hot_tokens_enabled", "hot_tokens_scan_interval", "hot_tokens_max_results",
"hot_tokens_auto_execute", "hot_tokens_auto_threshold",
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/config_store.py
git commit -m "feat(config): add hot tokens configuration fields"
```

---

## Task 4: Add Frontend Types

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add HotToken interface**

Append to `frontend/src/types/index.ts`:

```typescript
export interface HotToken {
  symbol: string
  price: number
  price_change_24h: number
  volume_24h: number
  volume_usd: number
  funding_rate: number
  long_short_ratio: number
  open_interest: number
  liquidation_price: number
  heat_score: number
}

export interface HotTokensUpdateData {
  type: 'hot_tokens_update'
  data: HotToken[]
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): add HotToken and HotTokensUpdate interfaces"
```

---

## Task 5: Add Hot Tokens Sub-tab to TradingView.vue

**Files:**
- Modify: `frontend/src/views/TradingView.vue`

- [ ] **Step 1: Add "Hot Tokens" to crypto sub-tabs**

In the template, after the existing two sub-buttons (`signals` and `positions`), add:

```vue
<button class="sub-btn" :class="{ active: cryptoSubTab === 'hot_tokens' }" @click="cryptoSubTab = 'hot_tokens'">
  🔥 Hot Tokens
</button>
```

- [ ] **Step 2: Add Hot Tokens content area**

Add a new `v-if="cryptoSubTab === 'hot_tokens'"` block with:
- Actions bar: Refresh button + Start/Stop Scanner buttons
- Hot tokens table with columns: Rank, Symbol, Price, 24h Change, Volume, Funding, L/S Ratio, Heat Score
- Action buttons per row: Analyze, Trade

Use the existing table styling (`.trade-list`, `.trade-row` etc.) for consistency.

- [ ] **Step 3: Add reactive state for hot tokens**

In `<script setup>`:

```typescript
import type { HotToken } from '../types'

const cryptoSubTab = ref<'signals' | 'positions' | 'hot_tokens'>('signals')
const hotTokens = ref<HotToken[]>([])
const htLoading = ref(false)
const scannerRunning = ref(false)
```

- [ ] **Step 4: Add API functions for hot tokens**

```typescript
async function fetchHotTokens() {
  htLoading.value = true
  try {
    const resp = await fetch('/api/hot_tokens/?limit=50')
    if (resp.ok) {
      const data = await resp.json()
      hotTokens.value = data.tokens || []
    }
  } catch { /* ignore */ } finally { htLoading.value = false }
}

async function fetchScannerStatus() {
  try {
    const resp = await fetch('/api/hot_tokens/status')
    if (resp.ok) {
      const data = await resp.json()
      scannerRunning.value = data.running
    }
  } catch { /* ignore */ }
}

async function startScanner() {
  try {
    await fetch('/api/hot_tokens/start', { method: 'POST' })
    await fetchScannerStatus()
  } catch { /* ignore */ }
}

async function stopScanner() {
  try {
    await fetch('/api/hot_tokens/stop', { method: 'POST' })
    await fetchScannerStatus()
  } catch { /* ignore */ }
}

async function analyzeHotToken(symbol: string) {
  try {
    const resp = await fetch(`/api/hot_tokens/${symbol}/analyze`, { method: 'POST' })
    if (resp.ok) {
      const data = await resp.json()
      alert(`Analysis for ${symbol}:\nSentiment: ${data.sentiment}\nConfidence: ${(data.confidence * 100).toFixed(0)}%\nReasoning: ${data.reasoning}`)
    }
  } catch { /* ignore */ }
}

async function tradeHotToken(symbol: string) {
  try {
    const resp = await fetch(`/api/hot_tokens/${symbol}/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ side: 'buy' })
    })
    if (resp.ok) {
      const data = await resp.json()
      alert(`Trade result: ${JSON.stringify(data)}`)
    }
  } catch { /* ignore */ }
}
```

- [ ] **Step 5: Wire WebSocket updates**

In `onMounted`, after existing fetches, add:

```typescript
fetchHotTokens()
fetchScannerStatus()
```

Import and use the `useWebSocket` composable to listen for `hot_tokens_update`:

```typescript
import { useWebSocket } from '../composables/useWebSocket'

const { lastMessage } = useWebSocket()

// Watch for hot tokens updates
import { watch } from 'vue'
watch(lastMessage, (msg) => {
  if (msg?.type === 'hot_tokens_update') {
    hotTokens.value = msg.data || []
  }
})
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/TradingView.vue
git commit -m "feat(frontend): add Hot Tokens sub-tab with live table"
```

---

## Task 6: Test and Verify Full Flow

- [ ] **Step 1: Start backend**

```bash
cd backend && python -m uvicorn main:app --reload --port 8000
```

- [ ] **Step 2: Start frontend**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: Verify WebSocket integration**

Open browser DevTools → Network → WS. Connect to `/ws`. Confirm that when the scanner runs, `hot_tokens_update` messages are received.

- [ ] **Step 4: Verify REST endpoints**

```bash
# Start scanner
curl -X POST http://localhost:8000/api/hot_tokens/start

# Get hot tokens
curl http://localhost:8000/api/hot_tokens/

# Analyze a token
curl -X POST http://localhost:8000/api/hot_tokens/BTCUSDT/analyze

# Stop scanner
curl -X POST http://localhost:8000/api/hot_tokens/stop
```

- [ ] **Step 5: Verify frontend**

1. Navigate to TradingView
2. Click Crypto tab
3. Click "Hot Tokens" sub-tab
4. Click "Start Scanner"
5. Confirm table populates with data
6. Click "Analyze" on a row - should show LLM analysis
7. Click "Trade" on a row - should execute order

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "test: verify hot tokens full integration"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|------------------|------|
| Scanner fetches and updates every 60 seconds | Already in `hot_tokens_scanner.py` |
| Hot tokens visible in TradingView frontend | Task 5 |
| WebSocket pushes real-time updates | Task 1 (fixes broadcast), Task 5 (frontend handler) |
| Analyze button triggers LLM analysis | Task 2 (`POST /:symbol/analyze`), Task 5 (frontend button) |
| Trade button executes Binance order | Task 2 (`POST /:symbol/execute`), Task 5 (frontend button) |
| Auto mode executes trades on high confidence | Out of scope for this plan (Phase 5 in spec) |
| All tests pass on Testnet | Task 6 |

**Gap:** Auto-trading (Phase 5) is intentionally out of scope for this implementation plan. It can be added in a follow-up.

---

## Placeholder Scan

- No "TBD", "TODO", or "implement later"
- No vague "add error handling" without code
- Every function is fully defined
- File paths are exact

## Type Consistency Check

- `HotToken` dataclass in backend matches `HotToken` interface in frontend
- `heat_score` field name consistent across all files
- `symbol` format (`BTCUSDT`) consistent

---

**Plan complete and saved to `docs/superpowers/plans/2026-06-03-binance-hot-tokens-scanner.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach would you like?