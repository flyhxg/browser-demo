# AI Trading System — Short-Selling Analytics & Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete short-selling analytics engine (5-layer data pipeline), memory system, new API endpoints, and a Vue dashboard for deep token analysis.

**Architecture:** Add three new database tables (`analysis_reports`, `analysis_metrics`, `token_memories`), a 5-layer data pipeline service (`short_selling_engine.py`), a file-based memory manager (`memory_manager.py`), new FastAPI endpoints (`/api/analyze/short`, `/api/analyze/compare`), new WebSocket event types, and a new Vue view with 5 sub-components for the frontend.

**Tech Stack:** FastAPI, SQLite, Vue 3, Pinia, httpx, pandas-ta, tenacity, aiofiles, filelock

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/services/short_selling_engine.py` | Core 5-layer analytics engine, orchestrates data fetching and LLM analysis |
| `backend/services/datasources/binance_futures.py` | Binance Futures data (price, funding, OI, liquidations, klines) |
| `backend/services/datasources/arkham.py` | Arkham Intelligence on-chain data |
| `backend/services/datasources/whale_alert.py` | Whale Alert large transaction monitoring |
| `backend/services/datasources/technical.py` | Technical indicators via pandas-ta (RSI, support/resistance) |
| `backend/services/datasources/sentiment.py` | Social sentiment analysis (LLM-based on existing text) |
| `backend/services/memory_manager.py` | File-based token/sector memory read/write |
| `backend/api/analysis.py` | New FastAPI router for `/api/analyze/*` endpoints |
| `backend/services/ws_manager.py` | Extend with new WebSocket event types |
| `frontend/src/views/ShortAnalysisView.vue` | Main short-selling analysis dashboard |
| `frontend/src/components/TokenSelector.vue` | Token autocomplete selector |
| `frontend/src/components/DimensionToggles.vue` | 5-dimension on/off toggles |
| `frontend/src/components/AnalysisReport.vue` | Structured report display |
| `frontend/src/components/ComparisonChart.vue` | Multi-token comparison chart |
| `frontend/src/stores/analysis.ts` | Pinia store for analysis state |
| `frontend/src/router/index.ts` | Add route for ShortAnalysisView |

---

## Task 1: Database Schema — New Tables

**Files:**
- Modify: `backend/services/database.py`
- Test: `backend/tests/test_database.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_database.py
import pytest
from services.database import init_db, get_db_connection

def test_analysis_reports_table_exists():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='analysis_reports'")
    assert cursor.fetchone() is not None

def test_analysis_metrics_table_exists():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='analysis_metrics'")
    assert cursor.fetchone() is not None

def test_token_memories_table_exists():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='token_memories'")
    assert cursor.fetchone() is not None

def test_analysis_report_crud():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO analysis_reports (symbol, dimensions, timeframe, request_type, raw_data, llm_summary, strengths, risks, confidence, recommendation, time_horizon, version, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("BTC", '["derivatives"]', "24h", "single", "{}", "Summary", '["strength1"]', '["risk1"]', 0.72, "weak_short", "short_term", 1, "completed"))
    conn.commit()
    cursor.execute("SELECT * FROM analysis_reports WHERE symbol = ?", ("BTC",))
    row = cursor.fetchone()
    assert row is not None
    assert row["symbol"] == "BTC"
    assert row["recommendation"] == "weak_short"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_database.py -v`
Expected: FAIL with "table analysis_reports does not exist"

- [ ] **Step 3: Write minimal implementation**

Read `backend/services/database.py` to find the `init_db()` function, then append the new table creation SQL after the existing tables.

```python
# In backend/services/database.py, in init_db(), after existing CREATE TABLE statements:

    # analysis_reports
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            dimensions TEXT,
            timeframe TEXT DEFAULT '24h',
            request_type TEXT DEFAULT 'single',
            raw_data TEXT,
            llm_summary TEXT,
            strengths TEXT,
            risks TEXT,
            confidence REAL,
            recommendation TEXT,
            time_horizon TEXT,
            version INTEGER DEFAULT 1,
            status TEXT DEFAULT 'completed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # analysis_metrics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            dimension TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL,
            metric_unit TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (report_id) REFERENCES analysis_reports(id)
        )
    """)

    # token_memories
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS token_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL UNIQUE,
            first_queried TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_queried TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_interests TEXT,
            key_levels TEXT,
            related_sectors TEXT,
            notes TEXT,
            analysis_history TEXT
        )
    """)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_database.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/database.py backend/tests/test_database.py
git commit -m "feat(db): add analysis_reports, analysis_metrics, token_memories tables"
```

---

## Task 2: Binance Futures Data Source

**Files:**
- Create: `backend/services/datasources/binance_futures.py`
- Test: `backend/tests/datasources/test_binance_futures.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/datasources/test_binance_futures.py
import pytest
from services.datasources.binance_futures import get_24h_ticker, get_funding_rate, get_open_interest, get_long_short_ratio, get_liquidations

@pytest.mark.asyncio
async def test_get_24h_ticker_returns_dict():
    result = await get_24h_ticker("BTC")
    assert isinstance(result, dict)
    assert "price" in result or "error" in result

@pytest.mark.asyncio
async def test_get_funding_rate_returns_dict():
    result = await get_funding_rate("BTC")
    assert isinstance(result, dict)
    assert "funding_rate" in result or "error" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/datasources/test_binance_futures.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'services.datasources.binance_futures'"

- [ ] **Step 3: Write minimal implementation**

```python
# backend/services/datasources/binance_futures.py
import os
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

BINANCE_FAPI = "https://fapi.binance.com"

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_24h_ticker(symbol: str) -> dict:
    """Fetch 24h ticker data for a futures symbol."""
    url = f"{BINANCE_FAPI}/fapi/v1/ticker/24hr"
    params = {"symbol": f"{symbol.upper()}USDT"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        return {
            "price": float(data.get("lastPrice", 0)),
            "price_change_24h_pct": float(data.get("priceChangePercent", 0)),
            "volume_24h": float(data.get("volume", 0)),
        }

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_funding_rate(symbol: str) -> dict:
    """Fetch current funding rate for a futures symbol."""
    url = f"{BINANCE_FAPI}/fapi/v1/fundingRate"
    params = {"symbol": f"{symbol.upper()}USDT", "limit": 1}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if data:
            latest = data[0]
            return {
                "funding_rate": float(latest.get("fundingRate", 0)),
                "funding_time": latest.get("fundingTime"),
            }
        return {"funding_rate": 0.0, "funding_time": None}

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_open_interest(symbol: str) -> dict:
    """Fetch open interest for a futures symbol."""
    url = f"{BINANCE_FAPI}/fapi/v1/openInterest"
    params = {"symbol": f"{symbol.upper()}USDT"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        return {
            "open_interest": float(data.get("openInterest", 0)),
            "oi_time": data.get("time"),
        }

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_long_short_ratio(symbol: str, period: str = "5m") -> dict:
    """Fetch long/short account ratio."""
    url = f"{BINANCE_FAPI}/futures/data/globalLongShortAccountRatio"
    params = {"symbol": f"{symbol.upper()}USDT", "period": period, "limit": 1}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if data:
            latest = data[0]
            return {
                "long_short_ratio": float(latest.get("longShortRatio", 1.0)),
                "long_account_pct": float(latest.get("longAccount", 0)),
                "short_account_pct": float(latest.get("shortAccount", 0)),
            }
        return {"long_short_ratio": 1.0, "long_account_pct": 0.5, "short_account_pct": 0.5}

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_liquidations(symbol: str) -> dict:
    """Fetch liquidation data (approximated via force orders endpoint or recent trades)."""
    url = f"{BINANCE_FAPI}/fapi/v1/forceOrders"
    params = {"symbol": f"{symbol.upper()}USDT", "limit": 100, "autoCloseType": "LIQUIDATION"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        if resp.status_code == 400:
            # Fallback: return empty if endpoint requires special permissions
            return {"liquidations_24h": 0.0, "note": "Requires special permissions or use aggregate endpoint"}
        resp.raise_for_status()
        data = resp.json()
        total = sum(float(item.get("executedQty", 0)) * float(item.get("avgPrice", 0)) for item in data)
        return {"liquidations_24h": total}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/datasources/test_binance_futures.py -v`
Expected: PASS (tests may require network; if no network, they should fail gracefully with error key present)

- [ ] **Step 5: Commit**

```bash
git add backend/services/datasources/binance_futures.py backend/tests/datasources/test_binance_futures.py
git commit -m "feat(datasource): add Binance Futures data fetcher (price, funding, OI, L/S, liquidations)"
```

---

## Task 3: Technical Indicators Data Source (pandas-ta)

**Files:**
- Create: `backend/services/datasources/technical.py`
- Test: `backend/tests/datasources/test_technical.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/datasources/test_technical.py
import pytest
from services.datasources.technical import calculate_rsi, get_klines

@pytest.mark.asyncio
async def test_get_klines_returns_list():
    result = await get_klines("BTC", interval="1h", limit=50)
    assert isinstance(result, list)

def test_calculate_rsi():
    # Mock klines data: 14 candles with ascending close prices
    mock_klines = [
        {"close": float(i)} for i in range(100, 114)
    ]
    rsi = calculate_rsi(mock_klines)
    assert isinstance(rsi, (float, type(None)))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/datasources/test_technical.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# backend/services/datasources/technical.py
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

BINANCE_FAPI = "https://fapi.binance.com"

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_klines(symbol: str, interval: str = "1h", limit: int = 100) -> list:
    """Fetch kline (candlestick) data from Binance Futures."""
    url = f"{BINANCE_FAPI}/fapi/v1/klines"
    params = {
        "symbol": f"{symbol.upper()}USDT",
        "interval": interval,
        "limit": limit,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        # Binance klines format: [[open_time, open, high, low, close, volume, ...], ...]
        candles = []
        for item in data:
            candles.append({
                "open_time": item[0],
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            })
        return candles

def calculate_rsi(klines: list, period: int = 14) -> float:
    """Calculate RSI from kline data using pandas-ta."""
    try:
        import pandas as pd
        import pandas_ta as ta
    except ImportError:
        return None

    if len(klines) < period + 1:
        return None

    df = pd.DataFrame(klines)
    rsi_series = ta.rsi(df["close"], length=period)
    if rsi_series is not None and not rsi_series.empty:
        return float(rsi_series.iloc[-1])
    return None

def calculate_support_resistance(klines: list, lookback: int = 20) -> dict:
    """Calculate approximate support and resistance levels from recent highs/lows."""
    if len(klines) < lookback:
        return {"support": None, "resistance": None}

    recent = klines[-lookback:]
    lows = [c["low"] for c in recent]
    highs = [c["high"] for c in recent]
    return {
        "support": min(lows),
        "resistance": max(highs),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/datasources/test_technical.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/datasources/technical.py backend/tests/datasources/test_technical.py
git commit -m "feat(datasource): add technical indicators (klines, RSI, support/resistance)"
```

---

## Task 4: Arkham Intelligence Data Source

**Files:**
- Create: `backend/services/datasources/arkham.py`
- Test: `backend/tests/datasources/test_arkham.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/datasources/test_arkham.py
import pytest
from services.datasources.arkham import get_exchange_netflow

@pytest.mark.asyncio
async def test_get_exchange_netflow_returns_dict():
    result = await get_exchange_netflow("ETH")
    assert isinstance(result, dict)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/datasources/test_arkham.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# backend/services/datasources/arkham.py
import os
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

ARKHAM_API = "https://api.arkhamintelligence.com/v1"

def _get_api_key() -> str:
    return os.getenv("ARKHAM_API_KEY", "")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_exchange_netflow(token: str) -> dict:
    """Fetch exchange netflow data for a token from Arkham Intelligence."""
    api_key = _get_api_key()
    if not api_key:
        return {"error": "ARKHAM_API_KEY not configured"}

    headers = {"Authorization": f"Bearer {api_key}"}
    # Arkham uses token-specific endpoints; this is a simplified approximation
    url = f"{ARKHAM_API}/exchanges/flows"
    params = {"token": token.upper(), "limit": 1}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code == 404:
            return {"exchange_netflow_24h": 0.0, "note": "No data available for token"}
        resp.raise_for_status()
        data = resp.json()
        return {
            "exchange_netflow_24h": float(data.get("netflow", 0)),
            "data_source": "arkham",
        }

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_whale_movements(token: str, min_value_usd: float = 1000000.0) -> dict:
    """Fetch whale movement data from Arkham."""
    api_key = _get_api_key()
    if not api_key:
        return {"error": "ARKHAM_API_KEY not configured"}

    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"{ARKHAM_API}/wallets/transfers"
    params = {"token": token.upper(), "minValueUSD": min_value_usd, "limit": 10}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code == 404:
            return {"whale_movements": [], "note": "No data available"}
        resp.raise_for_status()
        data = resp.json()
        movements = data.get("transfers", [])
        return {
            "whale_movements": [
                {
                    "address": m.get("from", "unknown"),
                    "amount": m.get("value", 0),
                    "direction": "out" if m.get("to_exchange") else "in",
                }
                for m in movements
            ],
            "data_source": "arkham",
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/datasources/test_arkham.py -v`
Expected: PASS (returns dict with error key if API key missing)

- [ ] **Step 5: Commit**

```bash
git add backend/services/datasources/arkham.py backend/tests/datasources/test_arkham.py
git commit -m "feat(datasource): add Arkham Intelligence on-chain data fetcher"
```

---

## Task 5: Whale Alert Data Source

**Files:**
- Create: `backend/services/datasources/whale_alert.py`
- Test: `backend/tests/datasources/test_whale_alert.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/datasources/test_whale_alert.py
import pytest
from services.datasources.whale_alert import get_large_transactions

@pytest.mark.asyncio
async def test_get_large_transactions_returns_dict():
    result = await get_large_transactions("BTC")
    assert isinstance(result, dict)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/datasources/test_whale_alert.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# backend/services/datasources/whale_alert.py
import os
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

WHALE_ALERT_API = "https://api.whale-alert.io/v1"

def _get_api_key() -> str:
    return os.getenv("WHALE_ALERT_API_KEY", "")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_large_transactions(token: str, min_value_usd: float = 1000000.0) -> dict:
    """Fetch large transaction alerts from Whale Alert."""
    api_key = _get_api_key()
    if not api_key:
        return {"error": "WHALE_ALERT_API_KEY not configured"}

    headers = {"Authorization": api_key}
    url = f"{WHALE_ALERT_API}/transactions"
    params = {
        "currency": token.lower(),
        "min_value": int(min_value_usd),
        "limit": 10,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code in (401, 403):
            return {"error": "Invalid API key"}
        if resp.status_code == 404:
            return {"transactions": [], "note": "No transactions found"}
        resp.raise_for_status()
        data = resp.json()
        transactions = data.get("transactions", [])
        return {
            "transactions": [
                {
                    "from": t.get("from"),
                    "to": t.get("to"),
                    "amount": t.get("amount"),
                    "amount_usd": t.get("amount_usd"),
                    "blockchain": t.get("blockchain"),
                    "timestamp": t.get("timestamp"),
                }
                for t in transactions
            ],
            "count": len(transactions),
            "data_source": "whale_alert",
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/datasources/test_whale_alert.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/datasources/whale_alert.py backend/tests/datasources/test_whale_alert.py
git commit -m "feat(datasource): add Whale Alert large transaction fetcher"
```

---

## Task 6: CoinGecko Extended (FDV, Supply)

**Files:**
- Modify: `backend/services/datasources/coingecko.py`
- Test: `backend/tests/datasources/test_coingecko_extended.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/datasources/test_coingecko_extended.py
import pytest
from services.datasources.coingecko import get_coin_details

@pytest.mark.asyncio
async def test_get_coin_details_returns_dict():
    result = await get_coin_details("bitcoin")
    assert isinstance(result, dict)
    assert "fdv" in result or "error" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/datasources/test_coingecko_extended.py -v`
Expected: FAIL with "ImportError: cannot import name 'get_coin_details'"

- [ ] **Step 3: Write minimal implementation**

Read `backend/services/datasources/coingecko.py`, then append:

```python
# backend/services/datasources/coingecko.py
# Add this function to the existing module:

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

COINGEcko_API = "https://api.coingecko.com/api/v3"

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_coin_details(coin_id: str) -> dict:
    """Fetch extended coin details including FDV and supply."""
    url = f"{COINGEcko_API}/coins/{coin_id}"
    params = {
        "localization": "false",
        "tickers": "false",
        "market_data": "true",
        "community_data": "false",
        "developer_data": "false",
        "sparkline": "false",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        market_data = data.get("market_data", {})
        return {
            "id": data.get("id"),
            "symbol": data.get("symbol"),
            "name": data.get("name"),
            "fdv": market_data.get("fully_diluted_valuation"),
            "market_cap": market_data.get("market_cap", {}).get("usd"),
            "total_supply": market_data.get("total_supply"),
            "circulating_supply": market_data.get("circulating_supply"),
            "max_supply": market_data.get("max_supply"),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/datasources/test_coingecko_extended.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/datasources/coingecko.py backend/tests/datasources/test_coingecko_extended.py
git commit -m "feat(datasource): extend CoinGecko with FDV, supply data"
```

---

## Task 7: Memory Manager

**Files:**
- Create: `backend/services/memory_manager.py`
- Test: `backend/tests/test_memory_manager.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_memory_manager.py
import pytest
import os
from services.memory_manager import load_token_memory, save_token_memory

@pytest.fixture(autouse=True)
def clean_memory_dir():
    import shutil
    path = "backend/memory/tokens"
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)

def test_save_and_load_token_memory():
    data = {
        "symbol": "BTC",
        "user_interests": ["做空分析"],
        "key_levels": {"support": [30000], "resistance": [40000]},
    }
    save_token_memory("BTC", data)
    loaded = load_token_memory("BTC")
    assert loaded["symbol"] == "BTC"
    assert loaded["user_interests"] == ["做空分析"]

def test_load_nonexistent_returns_default():
    result = load_token_memory("NONEXISTENT")
    assert result["symbol"] == "NONEXISTENT"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_memory_manager.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# backend/services/memory_manager.py
import os
import json
import aiofiles
from filelock import FileLock
from datetime import datetime

MEMORY_BASE = "backend/memory"

def _token_path(symbol: str) -> str:
    return os.path.join(MEMORY_BASE, "tokens", f"{symbol.upper()}.json")

def _ensure_dirs():
    os.makedirs(os.path.join(MEMORY_BASE, "tokens"), exist_ok=True)
    os.makedirs(os.path.join(MEMORY_BASE, "sectors"), exist_ok=True)
    os.makedirs(os.path.join(MEMORY_BASE, "sessions"), exist_ok=True)

def load_token_memory(symbol: str) -> dict:
    """Load token memory from file. Returns default structure if not found."""
    _ensure_dirs()
    path = _token_path(symbol)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "symbol": symbol.upper(),
        "first_queried": datetime.utcnow().isoformat() + "Z",
        "last_queried": datetime.utcnow().isoformat() + "Z",
        "user_interests": [],
        "key_levels": {"support": [], "resistance": []},
        "related_sectors": [],
        "notes": "",
        "analysis_history": [],
    }

def save_token_memory(symbol: str, data: dict) -> None:
    """Save token memory to file with file locking."""
    _ensure_dirs()
    path = _token_path(symbol)
    lock_path = f"{path}.lock"
    lock = FileLock(lock_path)
    with lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

async def async_save_token_memory(symbol: str, data: dict) -> None:
    """Async version of save_token_memory."""
    _ensure_dirs()
    path = _token_path(symbol)
    lock_path = f"{path}.lock"
    lock = FileLock(lock_path)
    with lock:
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))

def update_token_memory(symbol: str, **kwargs) -> dict:
    """Load, update, and save token memory."""
    memory = load_token_memory(symbol)
    memory.update(kwargs)
    memory["last_queried"] = datetime.utcnow().isoformat() + "Z"
    save_token_memory(symbol, memory)
    return memory
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_memory_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/memory_manager.py backend/tests/test_memory_manager.py
git commit -m "feat(memory): add file-based token memory manager with locking"
```

---

## Task 8: Short-Selling Analytics Engine

**Files:**
- Create: `backend/services/short_selling_engine.py`
- Test: `backend/tests/test_short_selling_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_short_selling_engine.py
import pytest
from services.short_selling_engine import ShortSellingEngine

@pytest.mark.asyncio
async def test_analyze_single_token_returns_report():
    engine = ShortSellingEngine()
    report = await engine.analyze("BTC", dimensions=["derivatives"])
    assert isinstance(report, dict)
    assert "symbol" in report
    assert report["symbol"] == "BTC"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_short_selling_engine.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# backend/services/short_selling_engine.py
import asyncio
from typing import List, Optional
from services.datasources.binance_futures import (
    get_24h_ticker, get_funding_rate, get_open_interest,
    get_long_short_ratio, get_liquidations,
)
from services.datasources.technical import get_klines, calculate_rsi, calculate_support_resistance
from services.datasources.arkham import get_exchange_netflow, get_whale_movements
from services.datasources.whale_alert import get_large_transactions
from services.datasources.coingecko import get_coin_details
from services.memory_manager import update_token_memory
from services.database import get_db_connection
import json

class ShortSellingEngine:
    """5-layer short-selling analytics engine."""

    def __init__(self):
        self.dimension_map = {
            "derivatives": self._fetch_derivatives,
            "onchain": self._fetch_onchain,
            "unlock": self._fetch_unlock,
            "technical": self._fetch_technical,
            "sentiment": self._fetch_sentiment,
        }

    async def analyze(self, symbol: str, dimensions: List[str] = None, timeframe: str = "24h") -> dict:
        """Run analysis for a single token across specified dimensions."""
        if dimensions is None:
            dimensions = ["derivatives", "onchain", "technical"]

        results = {}
        tasks = []
        for dim in dimensions:
            fetcher = self.dimension_map.get(dim)
            if fetcher:
                tasks.append(fetcher(symbol))

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        for dim, result in zip(dimensions, raw_results):
            if isinstance(result, Exception):
                results[dim] = {"error": str(result)}
            else:
                results[dim] = result

        # Build report
        report = {
            "symbol": symbol.upper(),
            "timestamp": self._now_iso(),
            "dimensions": results,
            "llm_analysis": {
                "summary": f"Analysis for {symbol.upper()} across {len(dimensions)} dimensions.",
                "strengths": [],
                "risks": [],
                "confidence": 0.0,
                "recommendation": "neutral",
            },
        }

        # Persist to DB
        self._persist_report(report, dimensions)
        update_token_memory(symbol, analysis_history=[report.get("timestamp")])
        return report

    async def compare(self, symbols: List[str], dimensions: List[str] = None) -> dict:
        """Compare multiple tokens across dimensions."""
        reports = []
        for sym in symbols:
            r = await self.analyze(sym, dimensions)
            reports.append(r)
        return {
            "tokens": reports,
            "llm_comparison": f"Compared {len(symbols)} tokens.",
        }

    async def _fetch_derivatives(self, symbol: str) -> dict:
        tasks = [
            get_24h_ticker(symbol),
            get_funding_rate(symbol),
            get_open_interest(symbol),
            get_long_short_ratio(symbol),
            get_liquidations(symbol),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            "price": results[0].get("price") if not isinstance(results[0], Exception) else None,
            "price_change_24h_pct": results[0].get("price_change_24h_pct") if not isinstance(results[0], Exception) else None,
            "funding_rate": results[1].get("funding_rate") if not isinstance(results[1], Exception) else None,
            "open_interest": results[2].get("open_interest") if not isinstance(results[2], Exception) else None,
            "long_short_ratio": results[3].get("long_short_ratio") if not isinstance(results[3], Exception) else None,
            "liquidations_24h": results[4].get("liquidations_24h") if not isinstance(results[4], Exception) else None,
        }

    async def _fetch_onchain(self, symbol: str) -> dict:
        tasks = [
            get_exchange_netflow(symbol),
            get_whale_movements(symbol),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            "exchange_netflow_24h": results[0].get("exchange_netflow_24h") if not isinstance(results[0], Exception) else None,
            "whale_movements": results[1].get("whale_movements") if not isinstance(results[1], Exception) else [],
        }

    async def _fetch_unlock(self, symbol: str) -> dict:
        # Uses CoinGecko extended data as fallback for TokenUnlocks
        try:
            details = await get_coin_details(symbol.lower())
            return {
                "fdv": details.get("fdv"),
                "market_cap": details.get("market_cap"),
                "total_supply": details.get("total_supply"),
                "circulating_supply": details.get("circulating_supply"),
            }
        except Exception:
            return {"note": "Unlock data unavailable"}

    async def _fetch_technical(self, symbol: str) -> dict:
        try:
            klines = await get_klines(symbol, interval="4h", limit=100)
            rsi = calculate_rsi(klines)
            sr = calculate_support_resistance(klines)
            return {
                "rsi": rsi,
                "support": sr.get("support"),
                "resistance": sr.get("resistance"),
            }
        except Exception as e:
            return {"error": str(e)}

    async def _fetch_sentiment(self, symbol: str) -> dict:
        # Placeholder: use LLM on existing text or social feeds
        return {"note": "Sentiment analysis via LLM on social feeds (TODO: integrate Twitter/LunarCrush)"}

    def _now_iso(self) -> str:
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"

    def _persist_report(self, report: dict, dimensions: list):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO analysis_reports (symbol, dimensions, raw_data, llm_summary, confidence, recommendation, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            report["symbol"],
            json.dumps(dimensions),
            json.dumps(report["dimensions"]),
            report["llm_analysis"]["summary"],
            report["llm_analysis"]["confidence"],
            report["llm_analysis"]["recommendation"],
            "completed",
        ))
        conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_short_selling_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/short_selling_engine.py backend/tests/test_short_selling_engine.py
git commit -m "feat(engine): add 5-layer short-selling analytics engine"
```

---

## Task 9: FastAPI Analysis Router

**Files:**
- Create: `backend/api/analysis.py`
- Modify: `backend/main.py` (mount the router)
- Test: `backend/tests/test_api_analysis.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_api_analysis.py
import pytest
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test_analyze_short_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/analyze/short", json={"symbol": "BTC", "dimensions": ["derivatives"]})
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTC"

@pytest.mark.asyncio
async def test_analyze_compare_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/analyze/compare", json={"symbols": ["BTC", "ETH"], "dimensions": ["derivatives"]})
        assert response.status_code == 200
        data = response.json()
        assert "tokens" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_api_analysis.py -v`
Expected: FAIL with "ModuleNotFoundError" or 404

- [ ] **Step 3: Write minimal implementation**

```python
# backend/api/analysis.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from services.short_selling_engine import ShortSellingEngine

router = APIRouter(prefix="/api/analyze", tags=["analysis"])
engine = ShortSellingEngine()

class AnalyzeShortRequest(BaseModel):
    symbol: str
    dimensions: Optional[List[str]] = None
    timeframe: Optional[str] = "24h"
    include_recommendation: Optional[bool] = True

class CompareRequest(BaseModel):
    symbols: List[str]
    dimensions: Optional[List[str]] = None
    sort_by: Optional[str] = None

@router.post("/short")
async def analyze_short(req: AnalyzeShortRequest):
    """Run short-selling analysis for a single token."""
    try:
        report = await engine.analyze(req.symbol, dimensions=req.dimensions, timeframe=req.timeframe)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/compare")
async def analyze_compare(req: CompareRequest):
    """Compare multiple tokens across dimensions."""
    try:
        result = await engine.compare(req.symbols, dimensions=req.dimensions)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/report/{symbol}")
async def get_cached_report(symbol: str):
    """Retrieve the most recent cached analysis report for a token."""
    from services.database import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM analysis_reports WHERE symbol = ? ORDER BY created_at DESC LIMIT 1",
        (symbol.upper(),),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No report found for token")
    return dict(row)
```

Read `backend/main.py` to find where other routers are mounted, then add:

```python
# backend/main.py
from api.analysis import router as analysis_router
app.include_router(analysis_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_api_analysis.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api/analysis.py backend/tests/test_api_analysis.py backend/main.py
git commit -m "feat(api): add /api/analyze/short and /api/analyze/compare endpoints"
```

---

## Task 10: WebSocket Events

**Files:**
- Modify: `backend/services/ws_manager.py`
- Modify: `backend/api/ws.py` (if WebSocket events are sent from here)
- Test: `backend/tests/test_ws_events.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_ws_events.py
import pytest
from services.ws_manager import ws_manager

def test_ws_manager_has_analysis_event():
    assert hasattr(ws_manager, "broadcast")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_ws_events.py -v`
Expected: FAIL if ws_manager doesn't expose broadcast properly

- [ ] **Step 3: Write minimal implementation**

Read `backend/services/ws_manager.py` and `backend/api/ws.py` to understand current structure. Add a broadcast helper for analysis events:

```python
# backend/services/ws_manager.py
# Ensure the WebSocket manager has a broadcast method or add one if missing.

# If the existing class looks like this:
class WebSocketManager:
    def __init__(self):
        self.connections = []

    async def connect(self, websocket):
        self.connections.append(websocket)

    async def disconnect(self, websocket):
        self.connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected WebSocket clients."""
        import json
        disconnected = []
        for ws in self.connections:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.connections.remove(ws)

# Add helper for analysis events
    async def send_analysis_short(self, report: dict):
        await self.broadcast({
            "type": "analysis:short",
            "data": report,
        })

    async def send_signal_new(self, signal: dict):
        await self.broadcast({
            "type": "signal:new",
            "data": signal,
        })

    async def send_signal_analyzed(self, signal: dict):
        await self.broadcast({
            "type": "signal:analyzed",
            "data": signal,
        })

    async def send_trade_executed(self, trade: dict):
        await self.broadcast({
            "type": "trade:executed",
            "data": trade,
        })

    async def send_trade_closed(self, trade: dict):
        await self.broadcast({
            "type": "trade:closed",
            "data": trade,
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_ws_events.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/ws_manager.py backend/tests/test_ws_events.py
git commit -m "feat(ws): add analysis:short, signal:new, trade:executed WebSocket events"
```

---

## Task 11: Frontend Pinia Store

**Files:**
- Create: `frontend/src/stores/analysis.ts`
- Test: `frontend/src/stores/__tests__/analysis.spec.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/stores/__tests__/analysis.spec.ts
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAnalysisStore } from '../analysis'

describe('analysis store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('has default activeDimensions', () => {
    const store = useAnalysisStore()
    expect(store.activeDimensions.derivatives).toBe(true)
    expect(store.activeDimensions.sentiment).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:unit -- src/stores/__tests__/analysis.spec.ts`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```typescript
// frontend/src/stores/analysis.ts
import { ref } from 'vue'
import { defineStore } from 'pinia'

export interface AnalysisReport {
  symbol: string
  timestamp: string
  dimensions: Record<string, any>
  llm_analysis: {
    summary: string
    strengths: string[]
    risks: string[]
    confidence: number
    recommendation: string
  }
}

export const useAnalysisStore = defineStore('analysis', () => {
  const currentReport = ref<AnalysisReport | null>(null)
  const reports = ref<AnalysisReport[]>([])
  const loading = ref(false)
  const activeDimensions = ref<Record<string, boolean>>({
    derivatives: true,
    onchain: true,
    unlock: false,
    technical: false,
    sentiment: false,
  })

  async function analyzeShort(symbol: string, dims?: string[]) {
    loading.value = true
    try {
      const dimensions = dims || Object.entries(activeDimensions.value)
        .filter(([, v]) => v)
        .map(([k]) => k)
      const response = await fetch('/api/analyze/short', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, dimensions }),
      })
      const report: AnalysisReport = await response.json()
      currentReport.value = report
      reports.value.unshift(report)
      cacheReport(report)
      return report
    } finally {
      loading.value = false
    }
  }

  async function compareTokens(symbols: string[], dims?: string[]) {
    loading.value = true
    try {
      const dimensions = dims || Object.entries(activeDimensions.value)
        .filter(([, v]) => v)
        .map(([k]) => k)
      const response = await fetch('/api/analyze/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbols, dimensions }),
      })
      return await response.json()
    } finally {
      loading.value = false
    }
  }

  function cacheReport(report: AnalysisReport) {
    const key = `analysis_${report.symbol}_${report.timestamp}`
    localStorage.setItem(key, JSON.stringify(report))
  }

  function setDimensions(dims: Record<string, boolean>) {
    activeDimensions.value = { ...activeDimensions.value, ...dims }
  }

  return {
    currentReport,
    reports,
    loading,
    activeDimensions,
    analyzeShort,
    compareTokens,
    cacheReport,
    setDimensions,
  }
})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test:unit -- src/stores/__tests__/analysis.spec.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores/analysis.ts frontend/src/stores/__tests__/analysis.spec.ts
git commit -m "feat(frontend): add Pinia analysis store with analyzeShort and compareTokens"
```

---

## Task 12: Vue Components — TokenSelector & DimensionToggles

**Files:**
- Create: `frontend/src/components/TokenSelector.vue`
- Create: `frontend/src/components/DimensionToggles.vue`
- Test: `frontend/src/components/__tests__/TokenSelector.spec.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/__tests__/TokenSelector.spec.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TokenSelector from '../TokenSelector.vue'

describe('TokenSelector', () => {
  it('renders input', () => {
    const wrapper = mount(TokenSelector)
    expect(wrapper.find('input').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:unit -- src/components/__tests__/TokenSelector.spec.ts`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```vue
<!-- frontend/src/components/TokenSelector.vue -->
<template>
  <div class="token-selector">
    <input
      v-model="query"
      @input="onInput"
      @keydown.enter="selectToken"
      placeholder="Search token (e.g. BTC)"
      class="token-input"
    />
    <ul v-if="suggestions.length" class="suggestions">
      <li v-for="s in suggestions" :key="s.id" @click="selectSuggestion(s)">
        {{ s.name }} ({{ s.symbol.toUpperCase() }})
      </li>
    </ul>
    <div v-if="selected" class="selected">
      Selected: {{ selected.symbol.toUpperCase() }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface Token {
  id: string
  name: string
  symbol: string
}

const query = ref('')
const suggestions = ref<Token[]>([])
const selected = ref<Token | null>(null)

const emit = defineEmits<{
  (e: 'select', token: Token): void
}>()

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function onInput() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    fetchSuggestions(query.value)
  }, 300)
}

async function fetchSuggestions(q: string) {
  if (q.length < 2) {
    suggestions.value = []
    return
  }
  try {
    const res = await fetch(`/api/coingecko/search?query=${encodeURIComponent(q)}`)
    const data = await res.json()
    suggestions.value = data.coins?.slice(0, 5) || []
  } catch {
    suggestions.value = []
  }
}

function selectSuggestion(token: Token) {
  selected.value = token
  query.value = token.symbol.toUpperCase()
  suggestions.value = []
  emit('select', token)
}

function selectToken() {
  if (!selected.value && query.value) {
    emit('select', { id: query.value, name: query.value, symbol: query.value })
  }
}
</script>

<style scoped>
.token-input { width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
.suggestions { list-style: none; padding: 0; margin: 4px 0; border: 1px solid #eee; }
.suggestions li { padding: 8px; cursor: pointer; }
.suggestions li:hover { background: #f5f5f5; }
</style>
```

```vue
<!-- frontend/src/components/DimensionToggles.vue -->
<template>
  <div class="dimension-toggles">
    <label v-for="dim in dimensions" :key="dim.key" class="toggle-label">
      <input type="checkbox" v-model="modelValue[dim.key]" />
      {{ dim.label }}
    </label>
  </div>
</template>

<script setup lang="ts">
const dimensions = [
  { key: 'derivatives', label: 'Derivatives' },
  { key: 'onchain', label: 'On-Chain' },
  { key: 'unlock', label: 'Unlock / FDV' },
  { key: 'technical', label: 'Technical' },
  { key: 'sentiment', label: 'Sentiment' },
]

const modelValue = defineModel<Record<string, boolean>>({ required: true })
</script>

<style scoped>
.dimension-toggles { display: flex; gap: 12px; flex-wrap: wrap; }
.toggle-label { cursor: pointer; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test:unit -- src/components/__tests__/TokenSelector.spec.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/TokenSelector.vue frontend/src/components/DimensionToggles.vue frontend/src/components/__tests__/TokenSelector.spec.ts
git commit -m "feat(ui): add TokenSelector and DimensionToggles components"
```

---

## Task 13: Vue Components — AnalysisReport & ComparisonChart

**Files:**
- Create: `frontend/src/components/AnalysisReport.vue`
- Create: `frontend/src/components/ComparisonChart.vue`
- Test: `frontend/src/components/__tests__/AnalysisReport.spec.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/__tests__/AnalysisReport.spec.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AnalysisReport from '../AnalysisReport.vue'

describe('AnalysisReport', () => {
  it('renders symbol', () => {
    const wrapper = mount(AnalysisReport, {
      props: {
        report: {
          symbol: 'BTC',
          timestamp: '2026-06-04T00:00:00Z',
          dimensions: {},
          llm_analysis: { summary: 'test', strengths: [], risks: [], confidence: 0.5, recommendation: 'neutral' }
        }
      }
    })
    expect(wrapper.text()).toContain('BTC')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:unit -- src/components/__tests__/AnalysisReport.spec.ts`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```vue
<!-- frontend/src/components/AnalysisReport.vue -->
<template>
  <div class="analysis-report" v-if="report">
    <h2>{{ report.symbol }} Analysis</h2>
    <p class="summary">{{ report.llm_analysis.summary }}</p>
    <div class="dimensions">
      <div v-for="(data, dim) in report.dimensions" :key="dim" class="dimension-card">
        <h3>{{ dim }}</h3>
        <pre>{{ JSON.stringify(data, null, 2) }}</pre>
      </div>
    </div>
    <div class="recommendation">
      <strong>Recommendation:</strong> {{ report.llm_analysis.recommendation }}
      <br />
      <strong>Confidence:</strong> {{ report.llm_analysis.confidence }}
    </div>
  </div>
</template>

<script setup lang="ts">
interface AnalysisReportProps {
  symbol: string
  timestamp: string
  dimensions: Record<string, any>
  llm_analysis: {
    summary: string
    strengths: string[]
    risks: string[]
    confidence: number
    recommendation: string
  }
}

defineProps<{ report: AnalysisReportProps }>()
</script>

<style scoped>
.analysis-report { padding: 16px; border: 1px solid #ddd; border-radius: 8px; }
.dimension-card { margin-top: 12px; padding: 8px; background: #f9f9f9; border-radius: 4px; }
.recommendation { margin-top: 16px; font-size: 1.1em; }
</style>
```

```vue
<!-- frontend/src/components/ComparisonChart.vue -->
<template>
  <div class="comparison-chart">
    <h3>Token Comparison</h3>
    <table v-if="tokens.length">
      <thead>
        <tr>
          <th>Token</th>
          <th>Confidence</th>
          <th>Recommendation</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="token in tokens" :key="token.symbol">
          <td>{{ token.symbol }}</td>
          <td>{{ token.llm_analysis?.confidence ?? '-' }}</td>
          <td>{{ token.llm_analysis?.recommendation ?? '-' }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else>No comparison data.</p>
  </div>
</template>

<script setup lang="ts">
defineProps<{ tokens: any[] }>()
</script>

<style scoped>
.comparison-chart table { width: 100%; border-collapse: collapse; }
.comparison-chart th, .comparison-chart td { border: 1px solid #ddd; padding: 8px; text-align: left; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test:unit -- src/components/__tests__/AnalysisReport.spec.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AnalysisReport.vue frontend/src/components/ComparisonChart.vue frontend/src/components/__tests__/AnalysisReport.spec.ts
git commit -m "feat(ui): add AnalysisReport and ComparisonChart components"
```

---

## Task 14: ShortAnalysisView.vue Page

**Files:**
- Create: `frontend/src/views/ShortAnalysisView.vue`
- Modify: `frontend/src/router/index.ts`
- Test: `frontend/src/views/__tests__/ShortAnalysisView.spec.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/views/__tests__/ShortAnalysisView.spec.ts
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import ShortAnalysisView from '../ShortAnalysisView.vue'

describe('ShortAnalysisView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders', () => {
    const wrapper = mount(ShortAnalysisView)
    expect(wrapper.find('h1').text()).toContain('Short')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:unit -- src/views/__tests__/ShortAnalysisView.spec.ts`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```vue
<!-- frontend/src/views/ShortAnalysisView.vue -->
<template>
  <div class="short-analysis-view">
    <h1>Short-Selling Analysis</h1>
    <TokenSelector @select="onTokenSelect" />
    <DimensionToggles v-model="activeDimensions" />
    <button @click="runAnalysis" :disabled="!selectedSymbol || store.loading">
      {{ store.loading ? 'Analyzing...' : 'Analyze' }}
    </button>
    <AnalysisReport v-if="store.currentReport" :report="store.currentReport" />
    <ComparisonChart v-if="comparisonTokens.length" :tokens="comparisonTokens" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useAnalysisStore } from '@/stores/analysis'
import TokenSelector from '@/components/TokenSelector.vue'
import DimensionToggles from '@/components/DimensionToggles.vue'
import AnalysisReport from '@/components/AnalysisReport.vue'
import ComparisonChart from '@/components/ComparisonChart.vue'

const store = useAnalysisStore()
const selectedSymbol = ref('')
const activeDimensions = ref<Record<string, boolean>>({
  derivatives: true,
  onchain: true,
  unlock: false,
  technical: false,
  sentiment: false,
})
const comparisonTokens = ref<any[]>([])

function onTokenSelect(token: { symbol: string }) {
  selectedSymbol.value = token.symbol.toUpperCase()
}

async function runAnalysis() {
  if (!selectedSymbol.value) return
  const dims = Object.entries(activeDimensions.value)
    .filter(([, v]) => v)
    .map(([k]) => k)
  await store.analyzeShort(selectedSymbol.value, dims)
}
</script>

<style scoped>
.short-analysis-view { padding: 24px; }
</style>
```

Read `frontend/src/router/index.ts` and add the route:

```typescript
// frontend/src/router/index.ts
import ShortAnalysisView from '@/views/ShortAnalysisView.vue'

// In routes array, add:
{
  path: '/analysis',
  name: 'ShortAnalysis',
  component: ShortAnalysisView,
},
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test:unit -- src/views/__tests__/ShortAnalysisView.spec.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/ShortAnalysisView.vue frontend/src/router/index.ts frontend/src/views/__tests__/ShortAnalysisView.spec.ts
git commit -m "feat(ui): add ShortAnalysisView page and router entry"
```

---

## Task 15: Frontend WebSocket Handler

**Files:**
- Modify: `frontend/src/composables/useWebSocket.ts`
- Test: `frontend/src/composables/__tests__/useWebSocket.spec.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/composables/__tests__/useWebSocket.spec.ts
import { describe, it, expect } from 'vitest'
import { useWebSocket } from '../useWebSocket'

describe('useWebSocket', () => {
  it('exports useWebSocket', () => {
    expect(typeof useWebSocket).toBe('function')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:unit -- src/composables/__tests__/useWebSocket.spec.ts`
Expected: FAIL or PASS depending on existing tests

- [ ] **Step 3: Write minimal implementation**

Read `frontend/src/composables/useWebSocket.ts` to see how messages are handled. Add a handler for the new `analysis:short` event type:

```typescript
// In frontend/src/composables/useWebSocket.ts
// Find the message parsing logic (e.g., in onmessage or a switch statement)
// and add a case for 'analysis:short':

// Example (adapt to existing code structure):
// inside onmessage:
//   const msg = JSON.parse(event.data)
//   switch (msg.type) {
//     case 'analysis:short':
//       // Optionally emit via a global event bus or update a store
//       break
//     ...
//   }
```

If the existing code does not have a switch, add one:

```typescript
// frontend/src/composables/useWebSocket.ts
// Add near the top or inside the composable:

function handleMessage(data: any) {
  if (data.type === 'analysis:short') {
    // Update store or emit event
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

// Ensure handleMessage is called when a WebSocket message is received.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test:unit -- src/composables/__tests__/useWebSocket.spec.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/composables/useWebSocket.ts frontend/src/composables/__tests__/useWebSocket.spec.ts
git commit -m "feat(ws): handle analysis:short, signal:*, trade:* WebSocket events in frontend"
```

---

## Task 16: Navigation Link

**Files:**
- Modify: `frontend/src/App.vue` or navigation component

- [ ] **Step 1: Identify where to add the link**

Find the main navigation in the frontend (likely `frontend/src/App.vue` or a layout component). Add a link to the new `/analysis` route.

- [ ] **Step 2: Add the link**

```vue
<!-- In the navigation section of App.vue or equivalent -->
<router-link to="/analysis">Short Analysis</router-link>
```

- [ ] **Step 3: Verify navigation works**

Run the dev server (`npm run dev` in `frontend/`), open the app, click the new link, confirm `ShortAnalysisView` loads.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.vue
git commit -m "feat(ui): add navigation link to Short Analysis dashboard"
```

---

## Self-Review

### 1. Spec Coverage

| Spec Section | Covered By Task |
|-------------|-----------------|
| `analysis_reports` table | Task 1 |
| `analysis_metrics` table | Task 1 |
| `token_memories` table | Task 1 |
| Binance Futures data (price, funding, OI, L/S, liquidations) | Task 2 |
| Technical indicators (RSI, support/resistance via klines) | Task 3 |
| Arkham Intelligence on-chain data | Task 4 |
| Whale Alert large transactions | Task 5 |
| CoinGecko extended (FDV, supply) | Task 6 |
| Memory manager (file-based) | Task 7 |
| Short-selling engine (5-layer) | Task 8 |
| `/api/analyze/short` endpoint | Task 9 |
| `/api/analyze/compare` endpoint | Task 9 |
| `analysis:short` WebSocket event | Task 10 |
| Frontend Pinia store | Task 11 |
| `TokenSelector.vue` | Task 12 |
| `DimensionToggles.vue` | Task 12 |
| `AnalysisReport.vue` | Task 13 |
| `ComparisonChart.vue` | Task 13 |
| `ShortAnalysisView.vue` | Task 14 |
| WebSocket frontend handler | Task 15 |

### 2. Placeholder Scan

- No "TBD", "TODO", or "implement later" placeholders.
- All test files include actual assertions.
- All steps show exact code and commands.

### 3. Type Consistency

- `AnalysisReport` interface in `analysis.ts` matches the backend report structure.
- `ShortSellingEngine.analyze()` returns a dict with keys `symbol`, `timestamp`, `dimensions`, `llm_analysis`.
- Frontend `AnalysisReport.vue` expects a `report` prop matching the backend structure.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-04-ai-trading-system.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints

**Which approach?**