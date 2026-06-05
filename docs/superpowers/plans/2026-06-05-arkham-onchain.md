# Arkham On-Chain & Prediction Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Arkham Intelligence API for on-chain data (holder concentration, smart money flow, exchange reserves, whale movements, entity predictions) into the short-selling analysis pipeline, with API key configurable from the Settings UI.

**Architecture:** Fix 2 existing broken Arkham functions (wrong base URL + auth header), add 5 new on-chain functions, expose 3 as `analyze()` dimensions, plumb the API key through `config_store` + Settings card. No new dependencies; use stdlib `unittest.mock` for httpx mocking.

**Tech Stack:** FastAPI, httpx, tenacity, Vue 3, pytest

**Spec:** `docs/superpowers/specs/2026-06-05-arkham-onchain-design.md`
**Reference doc:** Vyntral's [ARKHAM_API_DOCUMENTATION.md](https://github.com/Vyntral/arkham-intelligence-claude-skill/blob/main/ARKHAM_API_DOCUMENTATION.md) (1.0.4)

---

## File Structure

### Modified files (5 prod, 3 test)

| File | Responsibility | Change scope |
|---|---|---|
| `backend/services/config_store.py` | Read/write/JSON-file-backed config | Add 1 field + 1 masked alias + 1 allowlist prefix |
| `backend/services/datasources/arkham.py` | Arkham REST client | Rewrite base URL + auth; fix 2 fns; add 5 fns + helpers |
| `backend/services/short_selling_engine.py` | Multi-dim analyzer | Extend `dimension_map` with 3 keys; update onchain key |
| `frontend/src/types/index.ts` | TS types | Add 1 field to `AppConfig` |
| `frontend/src/views/SettingsView.vue` | Settings page | Add 1 card with 1 input + save handler |
| `backend/tests/datasources/test_arkham.py` | Tests for arkham.py | Expand 1 test → 8 |
| `backend/tests/test_config_store.py` | Tests for config_store | New file, 2 tests |
| `backend/tests/test_short_selling_engine.py` | Tests for engine | Add 2 tests for dimension_map + onchain wiring |

### Untouched but referenced

- `backend/services/event_pipeline.py` — also imports from arkham indirectly; not modified here
- `backend/api/analysis.py` — API endpoint unchanged; new dimensions are opt-in via request body
- `frontend/src/composables/useWebSocket.ts` — receives hot_tokens data; no change

---

## Task 1: Add `arkham_api_key` to config_store

**Files:**
- Modify: `backend/services/config_store.py:7-32` (DEFAULT_CONFIG), `:145-148` (allowlist in update_config)
- Test: `backend/tests/test_config_store.py` (new file)

- [ ] **Step 1: Create the test file with the round-trip test**

Create `backend/tests/test_config_store.py`:

```python
import os
import tempfile
import pytest
from pathlib import Path


@pytest.fixture
def isolated_config(monkeypatch):
    """Point config_store at a temp file so tests don't clobber the real one."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tmp.write("{}")
    tmp.close()
    monkeypatch.setattr("services.config_store.CONFIG_PATH", Path(tmp.name))
    yield Path(tmp.name)
    tmp.unlink()


def test_arkham_key_round_trip(isolated_config):
    from services import config_store

    config_store.update_config({"arkham_api_key": "test-key-1234"})

    loaded = config_store.get_config()
    assert loaded["arkham_api_key"] == "test-key-1234"


def test_arkham_key_appears_in_masked(isolated_config):
    from services import config_store

    config_store.update_config({"arkham_api_key": "test-key-1234"})

    masked = config_store.get_masked_config()
    assert masked["arkham_api_key_masked"] == "****1234"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_config_store.py -v`
Expected: Both tests FAIL (AttributeError or KeyError — `arkham_api_key` doesn't exist yet).

- [ ] **Step 3: Add `arkham_api_key` to DEFAULT_CONFIG**

In `backend/services/config_store.py`, extend the dict (after `"chat_use_llm_analysis"`):

```python
DEFAULT_CONFIG = {
    "api_key": "",
    "base_url": "https://api.anthropic.com",
    "model": "claude-sonnet-4-20250514",
    "protocol": "anthropic",
    "browser_mode": "local",
    "browser_use_api_key": "",
    "proxy_url": "",
    "binance_api_key": "",
    "binance_secret_key": "",
    "binance_mode": "futures",
    "trading_enabled": False,
    "max_position_size_usd": 100.0,
    "tp_percentage": 5.0,
    "sl_percentage": 3.0,
    "position_pct": 0.02,
    "max_open_positions": 5,
    "min_confidence": 0.7,
    "scan_interval_minutes": 5,
    "hot_tokens_enabled": False,
    "hot_tokens_scan_interval": 60,
    "hot_tokens_max_results": 50,
    "hot_tokens_auto_execute": False,
    "hot_tokens_auto_threshold": 0.8,
    "chat_use_llm_analysis": False,
    "arkham_api_key": "",  # NEW
}
```

- [ ] **Step 4: Add the masked field to `get_masked_config()`**

In `backend/services/config_store.py`, add to the returned dict (anywhere; place after `chat_use_llm_analysis` is not in masked — append at end):

```python
def get_masked_config() -> dict:
    config = _load_config()
    return {
        # ... existing fields unchanged ...
        "hot_tokens_auto_threshold": config.get("hot_tokens_auto_threshold", 0.8),
        "arkham_api_key_masked": mask_key(config.get("arkham_api_key", "")),  # NEW
    }
```

- [ ] **Step 5: Extend the `update_config` allowlist**

In `backend/services/config_store.py:update_config()`, update the allowlist tuple to include the `arkham_` prefix:

```python
def update_config(data: dict) -> dict:
    config = _load_config()
    for key in data:
        if key in config or key.startswith(("api_key", "base_url", "model", "protocol", "browser_mode",
                                            "browser_use_api_key", "binance_", "trading_enabled",
                                            "max_position_size", "tp_percentage", "sl_percentage",
                                            "position_pct", "max_open_positions",
                                            "min_confidence", "scan_interval", "hot_tokens_",
                                            "arkham_")):  # NEW: "arkham_"
            config[key] = data[key]
    _save_config(config)
    return get_masked_config()
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_config_store.py -v`
Expected: Both tests PASS.

- [ ] **Step 7: Commit**

```bash
cd backend && git add tests/test_config_store.py services/config_store.py
git commit -m "feat(config): add arkham_api_key field with masked display"
```

---

## Task 2: Frontend — add `arkham_api_key_masked` to AppConfig + Settings card

**Files:**
- Modify: `frontend/src/types/index.ts:1-22` (AppConfig interface)
- Modify: `frontend/src/views/SettingsView.vue` (new section + new ref + new save handler)

No automated test (frontend has no headless spec pattern in repo).

- [ ] **Step 1: Add the masked field to AppConfig**

In `frontend/src/types/index.ts`, append one line at the end of the `AppConfig` interface (before the closing `}`):

```typescript
export interface AppConfig {
  api_key_masked: string
  // ... all existing fields ...
  scan_interval_minutes: number
  arkham_api_key_masked: string  // NEW
}
```

- [ ] **Step 2: Add the On-chain / Arkham card to SettingsView.vue**

Insert this section immediately after the "Trading Configuration" `</section>` closing tag (line 136) and before the template's closing `</div>`:

```vue
    <section class="card" style="margin-top: 20px;">
      <h3>On-chain / Arkham Configuration</h3>
      <p class="desc">
        Configure Arkham Intelligence API for on-chain analytics: token holder
        concentration, smart money flow, exchange reserves, whale movements, and
        entity predictions.
      </p>
      <div class="form-row">
        <label>API Key</label>
        <input v-model="arkhamApiKey" type="password" placeholder="Arkham API key (arkm-…)" />
        <span v-if="config?.arkham_api_key_masked" class="badge ok">OK</span>
        <span v-else class="badge no">--</span>
      </div>
      <div class="form-actions">
        <button class="btn-primary" @click="saveArkham">Save</button>
        <span v-if="arkhamSaveResult === true" class="valid-text ok">Saved</span>
        <span v-if="arkhamSaveResult === false" class="valid-text err">Save failed</span>
      </div>
    </section>
```

- [ ] **Step 3: Add the script-side state + handler**

In `frontend/src/views/SettingsView.vue`, in the `<script setup>` block, add the ref and handler. Place after `const tradingSaveResult = ref<boolean | null>(null)` (line 165):

```typescript
const arkhamApiKey = ref('')
const arkhamSaveResult = ref<boolean | null>(null)
```

Add the handler function after `async function saveTrading()` closes (line 299):

```typescript
async function saveArkham() {
  const data: Record<string, string> = {}
  if (arkhamApiKey.value) {
    data.arkham_api_key = arkhamApiKey.value
  }
  try {
    const resp = await fetch('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (resp.ok) {
      arkhamApiKey.value = ''
      await loadConfig()
      arkhamSaveResult.value = true
      setTimeout(() => { arkhamSaveResult.value = null }, 2000)
    } else {
      arkhamSaveResult.value = false
      setTimeout(() => { arkhamSaveResult.value = null }, 2000)
    }
  } catch {
    arkhamSaveResult.value = false
    setTimeout(() => { arkhamSaveResult.value = null }, 2000)
  }
}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx vue-tsc --noEmit 2>&1 | head -30`
Expected: No errors related to `AppConfig` or `arkhamApiKey`.

If `vue-tsc` is not configured in this project, run instead: `cd frontend && npx tsc --noEmit -p . 2>&1 | head -30`
Expected: No errors.

If neither tool runs, do a manual sanity check: confirm the new field name matches exactly between type, template, and script.

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/types/index.ts src/views/SettingsView.vue
git commit -m "feat(settings): add Arkham API key configuration card"
```

---

## Task 3: Rewrite `arkham.py` base + auth + helpers

**Files:**
- Modify: `backend/services/datasources/arkham.py` (full rewrite, ~30 lines)
- Test: `backend/tests/datasources/test_arkham.py` (extend existing)

This task sets up the foundation (base URL, auth header, key resolution, SYMBOL_TO_CG_ID, _gini). Function implementations come in Tasks 4-6.

- [ ] **Step 1: Add tests for the new helpers**

Extend `backend/tests/datasources/test_arkham.py`. Append:

```python
import os


def test_arkham_base_url_is_arkm():
    from services.datasources import arkham
    assert arkham.ARKHAM_API == "https://api.arkm.com"


def test_gini_perfect_equality():
    from services.datasources.arkham import _gini
    assert _gini([100, 100, 100, 100]) == 0.0


def test_gini_perfect_inequality():
    from services.datasources.arkham import _gini
    # One holder owns everything
    assert abs(_gini([0, 0, 0, 1000]) - 0.75) < 0.01


def test_gini_empty():
    from services.datasources.arkham import _gini
    assert _gini([]) == 0.0
    assert _gini([0, 0, 0]) == 0.0


def test_symbol_to_cg_id_known():
    from services.datasources.arkham import SYMBOL_TO_CG_ID
    assert SYMBOL_TO_CG_ID["BTC"] == "bitcoin"
    assert SYMBOL_TO_CG_ID["ETH"] == "ethereum"


def test_get_api_key_prefers_config_store(monkeypatch):
    from services.datasources import arkham
    monkeypatch.setattr(arkham, "_key_from_config", lambda: "from-config")
    monkeypatch.delenv("ARKHAM_API_KEY", raising=False)
    assert arkham._get_api_key() == "from-config"


def test_get_api_key_falls_back_to_env(monkeypatch):
    from services.datasources import arkham
    monkeypatch.setattr(arkham, "_key_from_config", lambda: "")
    monkeypatch.setenv("ARKHAM_API_KEY", "from-env")
    assert arkham._get_api_key() == "from-env"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd backend && python -m pytest tests/datasources/test_arkham.py -v`
Expected: New tests FAIL (AttributeError — `ARKHAM_API` wrong, `_gini` missing, `SYMBOL_TO_CG_ID` missing, `_key_from_config` missing).

- [ ] **Step 3: Rewrite `backend/services/datasources/arkham.py`**

Replace the entire file contents with:

```python
"""Arkham Intelligence API client.

Endpoint contracts: Vyntral/arkham-intelligence-claude-skill
ARKHAM_API_DOCUMENTATION.md (1.0.4).

All functions return dicts and never raise. On missing key, 4xx, 5xx, or
network error, the function returns {"error": "..."}; the calling engine
treats error dims as soft-unavailable.
"""
import os
import asyncio
import logging
from typing import Any
from tenacity import retry, stop_after_attempt, wait_exponential
import httpx

logger = logging.getLogger(__name__)

ARKHAM_API = "https://api.arkm.com"

SYMBOL_TO_CG_ID = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
    "XRP": "ripple", "ADA": "cardano", "DOGE": "dogecoin", "AVAX": "avalanche-2",
    "MATIC": "matic-network", "DOT": "polkadot", "LINK": "chainlink",
    "TON": "the-open-network", "TRX": "tron", "LTC": "litecoin",
    "BCH": "bitcoin-cash", "NEAR": "near", "ATOM": "cosmos", "UNI": "uniswap",
    "APT": "aptos", "ARB": "arbitrum", "OP": "optimism", "INJ": "injective-protocol",
    "SUI": "sui", "SEI": "sei-network", "TIA": "celestia", "WLD": "worldcoin-wld",
    "PEPE": "pepe", "WIF": "dogwifcoin", "BONK": "bonk", "FLOKI": "floki",
    "SHIB": "shiba-inu", "JUP": "jupiter-exchange-solana",
    "USDT": "tether", "USDC": "usd-coin", "DAI": "dai", "FDUSD": "first-digital-usd",
}

# Arkham entity slugs (verified from public docs examples + common exchange/fund labels)
SMART_MONEY_ENTITIES = [
    "jump-trading", "wintermute", "cumberland", "galaxy-digital", "alameda-research",
]
EXCHANGE_ENTITIES = [
    "binance", "coinbase", "kraken", "okx", "bybit", "bitfinex", "htx", "kucoin",
]


def _key_from_config() -> str:
    """Read the configured API key. Returns "" if unset or config unavailable."""
    try:
        from services.config_store import get_config
        return get_config().get("arkham_api_key", "") or ""
    except Exception:
        return ""


def _get_api_key() -> str:
    """Prefer config_store; fall back to ARKHAM_API_KEY env var (CI / docker)."""
    key = _key_from_config()
    if key:
        return key
    return os.getenv("ARKHAM_API_KEY", "")


def _auth_headers() -> dict[str, str]:
    return {"API-Key": _get_api_key()}


def _gini(values: list[float]) -> float:
    """Gini coefficient. 0=perfect equality, 1=one holder owns everything."""
    if not values or sum(values) == 0:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    cum = sum((i + 1) * v for i, v in enumerate(sorted_v))
    return (2 * cum) / (n * sum(sorted_v)) - (n + 1) / n


def _symbol_to_cg_id(symbol: str) -> str:
    """Resolve Binance USDT-margined symbol to CoinGecko pricing ID.

    Falls back to lowercased symbol (best-effort; endpoint will 404 if not found).
    """
    base = symbol.upper().replace("USDT", "").replace("/USDT", "").replace(":USDT", "")
    return SYMBOL_TO_CG_ID.get(base, base.lower())


def _safe_note(message: str) -> dict[str, Any]:
    return {"error": message, "data_source": "arkham"}


async def _get_json(url: str, params: dict | None = None) -> dict | None:
    """GET with retry; return None on persistent failure (caller maps to error dict)."""
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _do() -> httpx.Response:
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await client.get(url, headers=_auth_headers(), params=params or {})

    try:
        return await _do()
    except (httpx.HTTPError, asyncio.TimeoutError) as exc:
        logger.warning(f"Arkham request failed: {url} ({exc})")
        return None
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `cd backend && python -m pytest tests/datasources/test_arkham.py -v`
Expected: All 7 new tests PASS. The original `test_get_exchange_netflow_returns_dict` may now FAIL because the signature changed — that's expected and will be fixed in Task 4.

- [ ] **Step 5: Commit**

```bash
cd backend && git add services/datasources/arkham.py tests/datasources/test_arkham.py
git commit -m "refactor(arkham): correct base URL + API-Key auth + add helpers"
```

---

## Task 4: Fix `get_exchange_netflow` (per-token CEX netflow)

**Files:**
- Modify: `backend/services/datasources/arkham.py` (add function)
- Modify: `backend/tests/datasources/test_arkham.py` (add tests)

- [ ] **Step 1: Add tests**

Append to `backend/tests/datasources/test_arkham.py`:

```python
@pytest.mark.asyncio
async def test_get_exchange_netflow_no_key(monkeypatch):
    from services.datasources import arkham
    monkeypatch.setattr(arkham, "_get_api_key", lambda: "")
    result = await arkham.get_exchange_netflow("BTC")
    assert result == {"error": "ARKHAM_API_KEY not configured"}


@pytest.mark.asyncio
async def test_get_exchange_netflow_happy_path(monkeypatch):
    from services.datasources import arkham

    monkeypatch.setattr(arkham, "_get_api_key", lambda: "fake-key")

    class FakeResp:
        status_code = 200
        def json(self):
            return {
                "tokens": [{
                    "token": {"id": "bitcoin", "symbol": "btc"},
                    "current": {
                        "inflowCexVolume": 100.0,
                        "outflowCexVolume": 30.0,
                    },
                }],
            }

    async def fake_get(url, params=None, **kwargs):
        return FakeResp()

    monkeypatch.setattr(arkham.httpx.AsyncClient, "get", fake_get)
    result = await arkham.get_exchange_netflow("BTC")
    assert result["cex_netflow_24h"] == 70.0  # 100 - 30
    assert result["data_source"] == "arkham"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/datasources/test_arkham.py::test_get_exchange_netflow_no_key tests/datasources/test_arkham.py::test_get_exchange_netflow_happy_path -v`
Expected: FAIL (the function does not exist in the new module yet).

- [ ] **Step 3: Add `get_exchange_netflow` to arkham.py**

Append to `backend/services/datasources/arkham.py`:

```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_exchange_netflow(token: str) -> dict[str, Any]:
    """Per-token CEX netflow over the last 24h.

    Endpoint: GET /token/top?tokenIds={cg_id}&orderByAgg=netflow&timeframe=24h
    Returns: {"cex_netflow_24h": float, "data_source": "arkham"}
    """
    if not _get_api_key():
        return {"error": "ARKHAM_API_KEY not configured"}

    cg_id = _symbol_to_cg_id(token)
    url = f"{ARKHAM_API}/token/top"
    params = {
        "tokenIds": cg_id,
        "orderByAgg": "netflow",
        "timeframe": "24h",
        "from": 0,
        "size": 1,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=_auth_headers(), params=params)
        if resp.status_code == 401:
            return {"error": "Invalid API key"}
        if resp.status_code == 404:
            return {"error": "Token not found", "data_source": "arkham"}
        resp.raise_for_status()
        data = resp.json()
        tokens = data.get("tokens", [])
        if not tokens:
            return {"error": "No data", "data_source": "arkham"}
        current = tokens[0].get("current", {})
        inflow = float(current.get("inflowCexVolume", 0) or 0)
        outflow = float(current.get("outflowCexVolume", 0) or 0)
        return {
            "cex_netflow_24h": inflow - outflow,
            "cex_inflow_24h": inflow,
            "cex_outflow_24h": outflow,
            "data_source": "arkham",
        }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/datasources/test_arkham.py::test_get_exchange_netflow_no_key tests/datasources/test_arkham.py::test_get_exchange_netflow_happy_path -v`
Expected: Both PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && git add services/datasources/arkham.py tests/datasources/test_arkham.py
git commit -m "feat(arkham): fix get_exchange_netflow via /token/top endpoint"
```

---

## Task 5: Fix `get_whale_movements` (high-value transfers)

**Files:**
- Modify: `backend/services/datasources/arkham.py` (add function)
- Modify: `backend/tests/datasources/test_arkham.py` (add tests)

- [ ] **Step 1: Add tests**

Append to `backend/tests/datasources/test_arkham.py`:

```python
@pytest.mark.asyncio
async def test_get_whale_movements_no_key(monkeypatch):
    from services.datasources import arkham
    monkeypatch.setattr(arkham, "_get_api_key", lambda: "")
    result = await arkham.get_whale_movements("BTC")
    assert result == {"error": "ARKHAM_API_KEY not configured"}


@pytest.mark.asyncio
async def test_get_whale_movements_happy_path(monkeypatch):
    from services.datasources import arkham

    monkeypatch.setattr(arkham, "_get_api_key", lambda: "fake-key")

    class FakeResp:
        status_code = 200
        def json(self):
            return {
                "transfers": [
                    {"from": "0xaaa", "to": "0xbbb", "amount": 5.0,
                     "amountUsd": 250000.0, "timestamp": "2026-06-05T00:00:00Z",
                     "blockchain": "ethereum"},
                ],
            }

    async def fake_get(url, params=None, **kwargs):
        return FakeResp()

    monkeypatch.setattr(arkham.httpx.AsyncClient, "get", fake_get)
    result = await arkham.get_whale_movements("ETH", min_value_usd=100000.0)
    assert len(result["whale_movements"]) == 1
    assert result["whale_movements"][0]["from"] == "0xaaa"
    assert result["data_source"] == "arkham"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/datasources/test_arkham.py::test_get_whale_movements_no_key tests/datasources/test_arkham.py::test_get_whale_movements_happy_path -v`
Expected: FAIL (function doesn't exist).

- [ ] **Step 3: Add `get_whale_movements` to arkham.py**

Append to `backend/services/datasources/arkham.py`:

```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_whale_movements(token: str, min_value_usd: float = 1_000_000.0) -> dict[str, Any]:
    """Top high-value transfers for a token in the last 24h.

    Endpoint: GET /transfers?tokens={cg_id}&timeLast=24h&usdGte={min}&limit=10
    """
    if not _get_api_key():
        return {"error": "ARKHAM_API_KEY not configured"}

    cg_id = _symbol_to_cg_id(token)
    url = f"{ARKHAM_API}/transfers"
    params = {
        "tokens": cg_id,
        "timeLast": "24h",
        "usdGte": min_value_usd,
        "limit": 10,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=_auth_headers(), params=params)
        if resp.status_code == 401:
            return {"error": "Invalid API key"}
        if resp.status_code == 404:
            return {"whale_movements": [], "note": "No transfers found"}
        resp.raise_for_status()
        data = resp.json()
        transfers = data.get("transfers", []) or data.get("transfersArray", [])
        return {
            "whale_movements": [
                {
                    "from": t.get("fromAddress", t.get("from")),
                    "to": t.get("toAddress", t.get("to")),
                    "amount": t.get("tokenAmount", t.get("amount")),
                    "amount_usd": t.get("usdValue", t.get("amountUsd")),
                    "blockchain": t.get("chain") or t.get("blockchain"),
                    "timestamp": t.get("blockTimestamp") or t.get("timestamp"),
                }
                for t in transfers
            ],
            "count": len(transfers),
            "data_source": "arkham",
        }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/datasources/test_arkham.py::test_get_whale_movements_no_key tests/datasources/test_arkham.py::test_get_whale_movements_happy_path -v`
Expected: Both PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && git add services/datasources/arkham.py tests/datasources/test_arkham.py
git commit -m "feat(arkham): fix get_whale_movements via /transfers endpoint"
```

---

## Task 6: Add `get_holder_concentration` + `_gini` integration

**Files:**
- Modify: `backend/services/datasources/arkham.py` (add function — `_gini` already exists from Task 3)
- Modify: `backend/tests/datasources/test_arkham.py` (add tests)

- [ ] **Step 1: Add tests**

Append to `backend/tests/datasources/test_arkham.py`:

```python
@pytest.mark.asyncio
async def test_get_holder_concentration_no_key(monkeypatch):
    from services.datasources import arkham
    monkeypatch.setattr(arkham, "_get_api_key", lambda: "")
    result = await arkham.get_holder_concentration("ETH")
    assert result == {"error": "ARKHAM_API_KEY not configured"}


@pytest.mark.asyncio
async def test_get_holder_concentration_happy_path(monkeypatch):
    from services.datasources import arkham

    monkeypatch.setattr(arkham, "_get_api_key", lambda: "fake-key")

    class FakeResp:
        status_code = 200
        def json(self):
            return {
                "token": {"symbol": "eth"},
                "holders": {
                    "ethereum": [
                        {"address": "0xa", "balance": 1000, "percentage": 40.0},
                        {"address": "0xb", "balance": 500, "percentage": 20.0},
                        {"address": "0xc", "balance": 100, "percentage": 5.0},
                    ],
                    "arbitrum": [
                        {"address": "0xd", "balance": 200, "percentage": 10.0},
                    ],
                },
            }

    async def fake_get(url, params=None, **kwargs):
        return FakeResp()

    monkeypatch.setattr(arkham.httpx.AsyncClient, "get", fake_get)
    result = await arkham.get_holder_concentration("ETH", top_n=10)
    # All 4 holders across chains
    assert result["holder_count"] == 4
    # Top 10% should be the 2 largest (40 + 20)
    assert abs(result["top_10_pct"] - 60.0) < 0.01
    # Gini should be > 0 (concentrated)
    assert result["gini"] > 0.0
    assert result["data_source"] == "arkham"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/datasources/test_arkham.py::test_get_holder_concentration_no_key tests/datasources/test_arkham.py::test_get_holder_concentration_happy_path -v`
Expected: FAIL (function doesn't exist).

- [ ] **Step 3: Add `get_holder_concentration` to arkham.py**

Append to `backend/services/datasources/arkham.py`:

```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_holder_concentration(token: str, top_n: int = 20) -> dict[str, Any]:
    """Holder concentration analysis (top-N % + Gini coefficient).

    Endpoint: GET /token/holders/{cg_id}?groupByEntity=true
    """
    if not _get_api_key():
        return {"error": "ARKHAM_API_KEY not configured"}

    cg_id = _symbol_to_cg_id(token)
    url = f"{ARKHAM_API}/token/holders/{cg_id}"
    params = {"groupByEntity": "true"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=_auth_headers(), params=params)
        if resp.status_code == 401:
            return {"error": "Invalid API key"}
        if resp.status_code == 404:
            return {"error": "Token not found", "data_source": "arkham"}
        resp.raise_for_status()
        data = resp.json()
        holders_by_chain: dict = data.get("holders", {})
        # Flatten across chains
        all_holders: list[dict] = []
        for chain_holders in holders_by_chain.values():
            all_holders.extend(chain_holders)
        # Sort by percentage desc, take top_n
        all_holders.sort(key=lambda h: h.get("percentage", 0) or 0, reverse=True)
        top = all_holders[:top_n]
        top_10_pct = sum(h.get("percentage", 0) or 0 for h in all_holders[:10])
        balances = [h.get("balance", 0) or 0 for h in all_holders]
        return {
            "top_10_pct": round(top_10_pct, 2),
            "top_n_pct": round(sum(h.get("percentage", 0) or 0 for h in top), 2),
            "gini": round(_gini(balances), 4),
            "holder_count": len(all_holders),
            "data_source": "arkham",
        }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/datasources/test_arkham.py::test_get_holder_concentration_no_key tests/datasources/test_arkham.py::test_get_holder_concentration_happy_path -v`
Expected: Both PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && git add services/datasources/arkham.py tests/datasources/test_arkham.py
git commit -m "feat(arkham): add get_holder_concentration with Gini coefficient"
```

---

## Task 7: Add `get_smart_money_flow` (multi-entity aggregator)

**Files:**
- Modify: `backend/services/datasources/arkham.py` (add function)
- Modify: `backend/tests/datasources/test_arkham.py` (add test)

- [ ] **Step 1: Add the test**

Append to `backend/tests/datasources/test_arkham.py`:

```python
@pytest.mark.asyncio
async def test_get_smart_money_flow_aggregates(monkeypatch):
    from services.datasources import arkham

    monkeypatch.setattr(arkham, "_get_api_key", lambda: "fake-key")

    # Per-entity fake responses
    entity_data = {
        "jump-trading": {"inflow": 100.0, "outflow": 200.0},
        "wintermute": {"inflow": 50.0, "outflow": 30.0},
        "cumberland": {"inflow": 0.0, "outflow": 0.0},  # net zero
    }

    class FakeResp:
        def __init__(self, entity):
            self.status_code = 200 if entity in entity_data else 404
            self._entity = entity
        def json(self):
            d = entity_data[self._entity]
            return {
                "ethereum": [{
                    "time": "2026-06-04T00:00:00Z",
                    "inflow": d["inflow"],
                    "outflow": d["outflow"],
                }],
            }

    async def fake_get(url, params=None, **kwargs):
        # Extract entity from URL path: /flow/entity/{entity}
        entity = url.split("/")[-1]
        return FakeResp(entity)

    monkeypatch.setattr(arkham.httpx.AsyncClient, "get", fake_get)
    result = await arkham.get_smart_money_flow("ETH", days=7)

    # jump-trading: 100 - 200 = -100
    # wintermute:    50 -  30 =   20
    # cumberland:    0  -  0  =    0
    # Total: -80
    assert abs(result["smart_money_netflow"] - (-80.0)) < 0.01
    assert "jump-trading" in result["by_entity"]
    assert result["by_entity"]["jump-trading"] == -100.0
    assert result["data_source"] == "arkham"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/datasources/test_arkham.py::test_get_smart_money_flow_aggregates -v`
Expected: FAIL (function doesn't exist).

- [ ] **Step 3: Add `get_smart_money_flow` to arkham.py**

Append to `backend/services/datasources/arkham.py`:

```python
async def get_smart_money_flow(token: str, days: int = 7) -> dict[str, Any]:
    """Sum of USD netflow across known smart-money entities, Ethereum chain.

    Endpoint: GET /flow/entity/{entity} (one call per known entity, in parallel)
    """
    if not _get_api_key():
        return {"error": "ARKHAM_API_KEY not configured"}

    async def fetch_one(entity: str) -> tuple[str, float]:
        try:
            url = f"{ARKHAM_API}/flow/entity/{entity}"
            resp = await _get_json(url, params={"chains": "ethereum"})
            if resp is None or resp.status_code != 200:
                return entity, 0.0
            data = resp.json()
            chain_data = data.get("ethereum", [])
            if not chain_data:
                return entity, 0.0
            # Use last entry as the "current" snapshot
            latest = chain_data[-1]
            net = float(latest.get("inflow", 0) or 0) - float(latest.get("outflow", 0) or 0)
            return entity, net
        except Exception as exc:
            logger.warning(f"smart-money fetch failed for {entity}: {exc}")
            return entity, 0.0

    results = await asyncio.gather(*(fetch_one(e) for e in SMART_MONEY_ENTITIES))
    by_entity = dict(results)
    total = sum(by_entity.values())
    return {
        "smart_money_netflow": round(total, 2),
        "by_entity": {k: round(v, 2) for k, v in by_entity.items()},
        "entity_count": len(by_entity),
        "data_source": "arkham",
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/datasources/test_arkham.py::test_get_smart_money_flow_aggregates -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && git add services/datasources/arkham.py tests/datasources/test_arkham.py
git commit -m "feat(arkham): add get_smart_money_flow aggregating 5 entities"
```

---

## Task 8: Add `get_exchange_reserves` (8-exchange aggregator)

**Files:**
- Modify: `backend/services/datasources/arkham.py` (add function)
- Modify: `backend/tests/datasources/test_arkham.py` (add test)

- [ ] **Step 1: Add the test**

Append to `backend/tests/datasources/test_arkham.py`:

```python
@pytest.mark.asyncio
async def test_get_exchange_reserves_aggregates(monkeypatch):
    from services.datasources import arkham

    monkeypatch.setattr(arkham, "_get_api_key", lambda: "fake-key")

    # Simulate balances: each exchange has WETH (id="weth") with some USD value
    exchange_balances = {
        "binance":  1_000_000.0,
        "coinbase": 500_000.0,
        "kraken":   100_000.0,  # we'll 404 this one to verify skip
    }

    class FakeResp:
        def __init__(self, entity):
            self.status_code = 200 if entity in exchange_balances else 404
            self._entity = entity
        def json(self):
            usd = exchange_balances[self._entity]
            return {
                "balances": {
                    "ethereum": [
                        {"symbol": "ETH", "id": "ethereum", "usd": usd},
                    ],
                },
            }

    async def fake_get(url, params=None, **kwargs):
        entity = url.split("/")[-1]
        return FakeResp(entity)

    monkeypatch.setattr(arkham.httpx.AsyncClient, "get", fake_get)
    result = await arkham.get_exchange_reserves("ETH")

    # binance + coinbase = 1.5M (kraken skipped due to 404)
    assert abs(result["exchange_reserves_usd"] - 1_500_000.0) < 0.01
    assert "binance" in result["by_exchange"]
    assert result["data_source"] == "arkham"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/datasources/test_arkham.py::test_get_exchange_reserves_aggregates -v`
Expected: FAIL (function doesn't exist).

- [ ] **Step 3: Add `get_exchange_reserves` to arkham.py**

Append to `backend/services/datasources/arkham.py`:

```python
async def get_exchange_reserves(token: str) -> dict[str, Any]:
    """Sum of exchange reserves for a token across known exchange entities.

    Endpoint: GET /balances/entity/{entity} (one call per exchange, in parallel)
    """
    if not _get_api_key():
        return {"error": "ARKHAM_API_KEY not configured"}

    cg_id = _symbol_to_cg_id(token)

    async def fetch_one(entity: str) -> tuple[str, float]:
        try:
            url = f"{ARKHAM_API}/balances/entity/{entity}"
            resp = await _get_json(url, params={"chains": "ethereum"})
            if resp is None or resp.status_code != 200:
                return entity, 0.0
            data = resp.json()
            chain_data = data.get("balances", {}).get("ethereum", [])
            # Sum USD for the target token
            total = sum(
                float(b.get("usd", 0) or 0)
                for b in chain_data
                if (b.get("id") or "").lower() == cg_id.lower()
            )
            return entity, total
        except Exception as exc:
            logger.warning(f"exchange balances fetch failed for {entity}: {exc}")
            return entity, 0.0

    results = await asyncio.gather(*(fetch_one(e) for e in EXCHANGE_ENTITIES))
    by_exchange = dict(results)
    total = sum(by_exchange.values())
    return {
        "exchange_reserves_usd": round(total, 2),
        "by_exchange": {k: round(v, 2) for k, v in by_exchange.items()},
        "exchange_count": len(by_exchange),
        "data_source": "arkham",
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/datasources/test_arkham.py::test_get_exchange_reserves_aggregates -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && git add services/datasources/arkham.py tests/datasources/test_arkham.py
git commit -m "feat(arkham): add get_exchange_reserves aggregating 8 exchanges"
```

---

## Task 9: Add `get_entity_predictions` (ML-predicted entity addresses)

**Files:**
- Modify: `backend/services/datasources/arkham.py` (add function)
- Modify: `backend/tests/datasources/test_arkham.py` (add test)

- [ ] **Step 1: Add the test**

Append to `backend/tests/datasources/test_arkham.py`:

```python
@pytest.mark.asyncio
async def test_get_entity_predictions_no_key(monkeypatch):
    from services.datasources import arkham
    monkeypatch.setattr(arkham, "_get_api_key", lambda: "")
    result = await arkham.get_entity_predictions("binance")
    assert result == {"error": "ARKHAM_API_KEY not configured"}


@pytest.mark.asyncio
async def test_get_entity_predictions_happy_path(monkeypatch):
    from services.datasources import arkham

    monkeypatch.setattr(arkham, "_get_api_key", lambda: "fake-key")

    class FakeResp:
        status_code = 200
        def json(self):
            return [
                {"address": "0xaaaa", "entityID": "binance", "usdBalance": 1_000_000.0},
                {"address": "0xbbbb", "entityID": "binance", "usdBalance": 500_000.0},
            ]

    async def fake_get(url, params=None, **kwargs):
        return FakeResp()

    monkeypatch.setattr(arkham.httpx.AsyncClient, "get", fake_get)
    result = await arkham.get_entity_predictions("binance")

    assert len(result["predictions"]) == 2
    assert result["predictions"][0]["address"] == "0xaaaa"
    assert result["data_source"] == "arkham"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/datasources/test_arkham.py::test_get_entity_predictions_no_key tests/datasources/test_arkham.py::test_get_entity_predictions_happy_path -v`
Expected: FAIL (function doesn't exist).

- [ ] **Step 3: Add `get_entity_predictions` to arkham.py**

Append to `backend/services/datasources/arkham.py`:

```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_entity_predictions(entity: str) -> dict[str, Any]:
    """ML-predicted addresses for an entity (e.g. 'binance', 'coinbase').

    Endpoint: GET /intelligence/entity_predictions/{entity}
    """
    if not _get_api_key():
        return {"error": "ARKHAM_API_KEY not configured"}

    url = f"{ARKHAM_API}/intelligence/entity_predictions/{entity}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=_auth_headers())
        if resp.status_code == 401:
            return {"error": "Invalid API key"}
        if resp.status_code == 404:
            return {"error": "Entity not found or no predictions", "data_source": "arkham"}
        resp.raise_for_status()
        data = resp.json()
        return {
            "predictions": [
                {
                    "address": p.get("address"),
                    "entity_id": p.get("entityID"),
                    "usd_balance": p.get("usdBalance"),
                }
                for p in data
            ],
            "entity": entity,
            "data_source": "arkham",
        }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/datasources/test_arkham.py::test_get_entity_predictions_no_key tests/datasources/test_arkham.py::test_get_entity_predictions_happy_path -v`
Expected: Both PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && git add services/datasources/arkham.py tests/datasources/test_arkham.py
git commit -m "feat(arkham): add get_entity_predictions for ML-predicted addresses"
```

---

## Task 10: Wire 3 new dimensions into `ShortSellingEngine` + update onchain key

**Files:**
- Modify: `backend/services/short_selling_engine.py:1-90` (imports, dimension_map, 3 new fetchers, _fetch_onchain return)
- Test: `backend/tests/test_short_selling_engine.py` (add 2 tests)

- [ ] **Step 1: Add tests**

Read `backend/tests/test_short_selling_engine.py` first to understand the existing fixture pattern. If it doesn't have an arkham-key fixture, append:

```python
def test_dimension_map_has_8_keys():
    from services.short_selling_engine import ShortSellingEngine
    engine = ShortSellingEngine()
    assert set(engine.dimension_map.keys()) == {
        "derivatives", "onchain", "holder_concentration", "smart_money",
        "exchange_reserves", "unlock", "technical", "sentiment",
    }


@pytest.mark.asyncio
async def test_fetch_onchain_returns_new_cex_netflow_key(monkeypatch):
    from services.short_selling_engine import ShortSellingEngine

    async def fake_netflow(token):
        return {"cex_netflow_24h": 42.0, "data_source": "arkham"}

    async def fake_whales(token):
        return {"whale_movements": [], "data_source": "arkham"}

    monkeypatch.setattr(
        "services.short_selling_engine.get_exchange_netflow", fake_netflow
    )
    monkeypatch.setattr(
        "services.short_selling_engine.get_whale_movements", fake_whales
    )

    engine = ShortSellingEngine()
    result = await engine._fetch_onchain("BTC")
    assert result["cex_netflow_24h"] == 42.0
    assert "whale_movements" in result
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_short_selling_engine.py::test_dimension_map_has_8_keys tests/test_short_selling_engine.py::test_fetch_onchain_returns_new_cex_netflow_key -v`
Expected: FAIL (either dimension_map missing keys, or _fetch_onchain not updated for the new key).

- [ ] **Step 3: Update imports in `short_selling_engine.py`**

Edit `backend/services/short_selling_engine.py` line 7:

```python
from services.datasources.arkham import (
    get_exchange_netflow,
    get_whale_movements,
    get_holder_concentration,    # NEW
    get_smart_money_flow,        # NEW
    get_exchange_reserves,       # NEW
)
```

- [ ] **Step 4: Extend `dimension_map` and add 3 fetchers**

In `backend/services/short_selling_engine.py`, replace the `__init__` body and add 3 new methods:

```python
class ShortSellingEngine:
    def __init__(self):
        self.dimension_map = {
            "derivatives": self._fetch_derivatives,
            "onchain": self._fetch_onchain,
            "holder_concentration": self._fetch_holder_concentration,   # NEW
            "smart_money": self._fetch_smart_money,                     # NEW
            "exchange_reserves": self._fetch_exchange_reserves,         # NEW
            "unlock": self._fetch_unlock,
            "technical": self._fetch_technical,
            "sentiment": self._fetch_sentiment,
        }

    # ... existing methods unchanged ...

    async def _fetch_holder_concentration(self, symbol: str) -> dict:
        return await get_holder_concentration(symbol)

    async def _fetch_smart_money(self, symbol: str) -> dict:
        return await get_smart_money_flow(symbol)

    async def _fetch_exchange_reserves(self, symbol: str) -> dict:
        return await get_exchange_reserves(symbol)
```

- [ ] **Step 5: Update `_fetch_onchain` to use the new return key**

In `backend/services/short_selling_engine.py`, replace the `_fetch_onchain` method body:

```python
    async def _fetch_onchain(self, symbol: str) -> dict:
        tasks = [get_exchange_netflow(symbol), get_whale_movements(symbol)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        netflow = results[0] if not isinstance(results[0], Exception) else {}
        whales = results[1] if not isinstance(results[1], Exception) else {}
        return {
            "cex_netflow_24h": netflow.get("cex_netflow_24h"),
            "cex_inflow_24h": netflow.get("cex_inflow_24h"),
            "cex_outflow_24h": netflow.get("cex_outflow_24h"),
            "whale_movements": whales.get("whale_movements", []),
        }
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_short_selling_engine.py::test_dimension_map_has_8_keys tests/test_short_selling_engine.py::test_fetch_onchain_returns_new_cex_netflow_key -v`
Expected: Both PASS.

- [ ] **Step 7: Run the full test suite to check for regressions**

Run: `cd backend && python -m pytest tests/ -v 2>&1 | tail -50`
Expected: All previously-passing tests still pass. The original `test_get_exchange_netflow_returns_dict` in `test_arkham.py` may still pass because `get_exchange_netflow` is still importable.

- [ ] **Step 8: Commit**

```bash
cd backend && git add services/short_selling_engine.py tests/test_short_selling_engine.py
git commit -m "feat(short-selling): wire 3 new on-chain dimensions and rename onchain key"
```

---

## Self-Review

### Spec coverage

| Spec section | Task |
|---|---|
| §3.1 backend/services/config_store.py | T1 |
| §3.1 backend/services/datasources/arkham.py (rewrite) | T3 |
| §3.1 backend/services/short_selling_engine.py (extend) | T10 |
| §3.1 frontend/src/types/index.ts | T2 |
| §3.1 frontend/src/views/SettingsView.vue | T2 |
| §4 function 1: `get_exchange_netflow` | T4 |
| §4 function 2: `get_whale_movements` | T5 |
| §4 function 3: `get_holder_concentration` | T6 |
| §4 function 4: `get_smart_money_flow` | T7 |
| §4 function 5: `get_exchange_reserves` | T8 |
| §4 function 6: `get_whale_portfolio_change` | **DEFERRED to Phase 2** (per spec §9) |
| §4 function 7: `get_entity_predictions` | T9 |
| §5 config_store changes | T1 |
| §6 ShortSellingEngine integration | T10 |
| §7 Settings UI | T2 |
| §8 test plan | T1 (config_store), T3-T9 (arkham), T10 (engine) |

`get_whale_portfolio_change` is intentionally omitted from v1 (requires an address, not a symbol; spec §9 lists as Phase 2).

### Placeholder scan

- No "TBD" / "TODO" / "implement later" in task bodies
- No "Add appropriate error handling" vague steps — every error path is in the function templates
- No "Similar to Task N" — every step has full code
- No references to functions not defined in any task (e.g. `validate_key` not used)

### Type / signature consistency

- `get_exchange_netflow(token)` signature matches across T4, T10 (call site)
- `get_whale_movements(token, min_value_usd=1e6)` signature matches T5 and T10
- `get_holder_concentration(token, top_n=20)` matches T6
- `get_smart_money_flow(token, days=7)` matches T7
- `get_exchange_reserves(token)` matches T8
- `get_entity_predictions(entity)` matches T9
- Return value of `get_exchange_netflow` changed (`exchange_netflow_24h` → `cex_netflow_24h`); T10 explicitly updates the one call site
- `_get_api_key`, `_auth_headers`, `_gini`, `_symbol_to_cg_id`, `SYMBOL_TO_CG_ID`, `SMART_MONEY_ENTITIES`, `EXCHANGE_ENTITIES` all defined in T3 and reused in later tasks
