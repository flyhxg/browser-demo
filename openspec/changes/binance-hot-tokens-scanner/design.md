# Binance Hot Tokens Scanner - Design Document

## 1. Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Frontend (Vue 3)                                │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ TradingView.vue - Crypto Tab                                          │   │
│  │  ┌──────────┐  ┌──────────┐  ┌─────────────────────────────────────┐  │   │
│  │  │Signals   │  │Positions │  │ 🔥 Hot Tokens (新增)                │  │   │
│  │  └────┬─────┘  └────┬─────┘  │  ┌───────────────────────────────┐  │  │   │
│  │       │             │        │  │ 综合热度排行榜                │  │  │   │
│  │       │             │        │  │ ┌────┬───────┬──────┐        │  │  │   │
│  │       │             │        │  │ │Rank│Symbol │Heat  │        │  │  │   │
│  │       │             │        │  │ └────┴───────┴──────┘        │  │  │   │
│  │       │             │        │  │ [Analyze] [Trade]            │  │  │   │
│  │       │             │        │  └───────────────────────────────┘  │  │   │
│  └───────┼─────────────┼────────┴─────────────────────────────────────┘  │   │
│          │             │                                                  │
│          │  REST API   │  WebSocket                                       │
└──────────┼─────────────┼──────────────────────────────────────────────────┘
           │             │
┌──────────┼─────────────┼──────────────────────────────────────────────────┐
│          │             │                                      Backend      │
│          │             │  (FastAPI)                                     │
│          │  ┌──────────┼─────────────────────────────────────────────┐     │
│          │  │ api/hot_tokens.py                                    │     │
│          │  │  GET  /hot_tokens        → 查询热榜                  │     │
│          │  │ POST  /hot_tokens/start  → 启动扫描器               │     │
│          │  │ POST  /hot_tokens/stop   → 停止扫描器               │     │
│          │  │ POST  /:symbol/analyze   → LLM 分析                │     │
│          │  │ POST  /:symbol/execute   → 执行交易                │     │
│          │  └──────────┼─────────────────────────────────────────────┘     │
│          │             │                                                │
│          │  ┌──────────┴─────────────────────────────┐                  │
│          │  │ services/hot_tokens_scanner.py        │                  │
│          │  │  ┌─────────────────────────────────┐  │                  │
│          │  │  │ HotTokensScanner               │  │                  │
│          │  │  │  ├ start()                     │  │                  │
│          │  │  │  ├ _fetch_and_update()         │  │                  │
│          │  │  │  │  ├ fetch_tickers()           │  │                  │
│          │  │  │  │  ├ fetch_funding_rate()      │  │                  │
│          │  │  │  │  ├ fetch_long_short_ratio()  │  │                  │
│          │  │  │  │  └ _calculate_heat_score()  │  │                  │
│          │  │  │  └ _broadcast_update()         │  │                  │
│          │  │  └─────────────────────────────────┘  │                  │
│          │  └──────────────────────────────────────────┘                  │
│          │             │                                                │
│          │  ┌──────────┴─────────────────────────────┐                  │
│          │  │ Reuse Layer                            │                  │
│          │  │  ├ binance_trader.py  (CCXT 连接)     │                  │
│          │  │  ├ signal_analyzer.py (LLM 分析)      │                  │
│          │  │  ├ trading_engine.py  (交易执行)     │                  │
│          │  │  ├ ws_manager.py      (WebSocket 广播)│                  │
│          │  │  └ database.py        (SQLite + hot_tokens 表)│        │
│          │  └──────────────────────────────────────────┘                  │
└──────────┼─────────────┼──────────────────────────────────────────────────┘
           │             │
     ┌─────┴──────┐ ┌────┴────┐
     │ Binance    │ │ SQLite  │
     │ Futures    │ │ Database│
     │ (CCXT)     │ └─────────┘
     └────────────┘
```

## 2. Data Flow

### 2.1 Scanner Flow (every 60 seconds)
```
Cron Trigger
    │
    ▼
_fetch_and_update()
    │
    ├─→ fetch_tickers() via CCXT (1 request, all pairs)
    │   GET /fapi/v1/ticker/24hr
    │   Returns: All USDT pairs with price, volume, change, etc.
    │
    ├─→ fetch_funding_rates() via CCXT (1 request, all pairs)
    │   GET /fapi/v1/fundingRate
    │   Returns: All funding rates (cached, updated every 8h)
    │
    ├─→ fetch_top_long_short_ratio() via CCXT (1 request, all pairs)
    │   GET /futures/data/globalLongShortAccountRatio
    │   Note: Fetched every 300s (5 min), not every scan
    │
    ├─→ _calculate_heat_score()
    │   heat = volume_score * 0.5 + change_score * 0.3 + funding_score * 0.2
    │
    ├─→ Sort by heat_score DESC
    │
    ├─→ Upsert to hot_tokens_cache table (keep only latest)
    │
    └─→ _broadcast_update() via WebSocket
        type: "hot_tokens_update"
```
**Rate Limit Note**: Each scan cycle makes ~3 API requests (tickers, funding rates, L/S ratio), well within Binance's 1200 req/min limit. Funding rate and L/S ratio are fetched every 5 minutes and cached in memory.


### 2.2 Manual Trading Flow
```
User clicks [Analyze] on Hot Token
    │
    ▼
POST /api/hot_tokens/:symbol/analyze
    │
    ▼
signal_analyzer.analyze()
    LLM 分析代币走势
    Returns: {sentiment, confidence, reasoning}
    │
    ▼
Frontend displays analysis result
    │
User clicks [Trade]
    │
    ▼
POST /api/hot_tokens/:symbol/execute
    │
    ▼
trading_engine.execute_signal()
    Position sizing (2% balance, max $100)
    Check max 5 positions
    Place market order via CCXT
    Set TP/SL orders
    │
    ▼
Save to trades table
Broadcast via WebSocket
```

### 2.3 Auto Trading Flow
```
HotTokensScanner._fetch_and_update()
    │
    ▼
For tokens with heat_score > threshold:
    │
    ▼
signal_analyzer.analyze()
    │
    ▼
If confidence >= auto_execute_threshold (0.8):
    │
    ▼
trading_engine.execute_signal()
    │
    ▼
Save to trades table + signals table (source='hot_token_auto')
Broadcast via WebSocket
```

## 3. Heat Score Calculation

### 3.1 Normalized Scores (0-1)

```python
def calculate_heat_score(token):
    # Volume score: higher is better
    volume_score = token.volume_usd / max_volume

    # Price change score: absolute change (volatility)
    change_score = abs(token.price_change_24h) / max_abs_change

    # Funding rate score: absolute value (extreme funding = crowded trade)
    funding_score = abs(token.funding_rate) / max_abs_funding

    # Weighted combination
    heat_score = (
        volume_score * 0.5 +    # Volume is the most important
        change_score * 0.3 +     # Volatility indicates interest
        funding_score * 0.2     # Extreme funding can signal reversals
    )

    return heat_score
```

### 3.2 Score Components

| Component | Weight | Formula | Rationale |
|-----------|--------|---------|-----------|
| Volume | 50% | token.volume / max_volume | High volume = high interest |
| Price Change | 30% | abs(change) / max_abs_change | Volatility = activity |
| Funding Rate | 20% | abs(funding) / max_abs_funding | Extreme funding = crowded trade |

## 4. Database Schema

### 4.1 hot_tokens Table

```sql
CREATE TABLE hot_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,                -- e.g. "BTCUSDT"
    price REAL DEFAULT 0,                -- Current price
    price_change_24h REAL DEFAULT 0,     -- 24h price change %
    volume_24h REAL DEFAULT 0,           -- 24h volume (base asset)
    volume_usd REAL DEFAULT 0,           -- 24h volume in USD
    funding_rate REAL DEFAULT 0,         -- Current funding rate
    long_short_ratio REAL DEFAULT 0,     -- Long/Short account ratio
    open_interest REAL DEFAULT 0,        -- Open interest
    liquidation_price REAL DEFAULT 0,  -- Estimated liquidation price
    heat_score REAL DEFAULT 0,           -- Calculated heat score
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.3 Data Retention

To prevent database bloat, implement a cleanup strategy:

```sql
-- Keep only last 24 hours of hot tokens data
DELETE FROM hot_tokens WHERE created_at < datetime('now', '-1 day');
```

**Cleanup Trigger**: Run every time scanner fetches new data (before insert), or via a daily cron job.

**Alternative**: Use a cache-first approach where only the latest snapshot is kept in SQLite, and historical data is optionally logged to files.

### 4.4 hot_tokens_cache Table (Optional)

For real-time display without DB bloat, use an cache table that always holds only the latest scan:

```sql
CREATE TABLE hot_tokens_cache (
    symbol TEXT PRIMARY KEY,
    price REAL DEFAULT 0,
    price_change_24h REAL DEFAULT 0,
    volume_24h REAL DEFAULT 0,
    volume_usd REAL DEFAULT 0,
    funding_rate REAL DEFAULT 0,
    long_short_ratio REAL DEFAULT 0,
    open_interest REAL DEFAULT 0,
    liquidation_price REAL DEFAULT 0,
    heat_score REAL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

This table is cleared and repopulated on each scan cycle, keeping only the latest snapshot.


```sql
CREATE INDEX idx_hot_tokens_heat ON hot_tokens(heat_score DESC, symbol);
CREATE INDEX idx_hot_tokens_symbol ON hot_tokens(symbol, created_at DESC);
```

## 5. API Design

### 5.1 Hot Tokens

| Method | Path | Description | Query |
|--------|------|-------------|-------|
| GET | `/api/hot_tokens` | Get hot tokens list | `limit=50`, `sort=heat_score` |
| GET | `/api/hot_tokens/:symbol` | Get single token details | `symbol` |

### 5.2 Scanner Control

| Method | Path | Description | Body |
|--------|------|-------------|------|
| POST | `/api/hot_tokens/start` | Start scanner | — |
| POST | `/api/hot_tokens/stop` | Stop scanner | — |
| GET | `/api/hot_tokens/status` | Get scanner status | — |

### 5.3 Analysis & Trading

| Method | Path | Description | Body |
|--------|------|-------------|------|
| POST | `/api/hot_tokens/:symbol/analyze` | Analyze token with LLM | — |
| POST | `/api/hot_tokens/:symbol/execute` | Execute trade | `{side, quantity, leverage}` |

## 6. WebSocket Protocol

### 6.1 Server → Client: Hot Tokens Update

```json
{
  "type": "hot_tokens_update",
  "data": [
    {
      "symbol": "BTCUSDT",
      "price": 64320.5,
      "price_change_24h": 2.3,
      "volume_24h": 150000.0,
      "volume_usd": 9648000000.0,
      "funding_rate": 0.0001,
      "long_short_ratio": 1.25,
      "open_interest": 250000.0,
      "liquidation_price": 61000.0,
      "heat_score": 0.89
    },
    ...
  ]
}
```

### 6.2 Message Frequency
- **Broadcast**: Every 60 seconds (after scanner update)
- **On demand**: Client can request via REST API anytime

## 7. Frontend Integration

### 7.1 TradingView.vue - New "Hot Tokens" Sub-tab

**Hierarchy**: TradingView.vue has two top-level tabs: **Crypto** and **Prediction**.

The **Crypto** tab already has two sub-tabs: **Signals Feed** and **Positions**.

**Hot Tokens** is added as a **third sub-tab** under the Crypto tab, not as a top-level tab.

```
TradingView.vue
├── Crypto (Tab)
│   ├── Signals Feed (Sub-tab, existing)
│   ├── Positions (Sub-tab, existing)
│   └── 🔥 Hot Tokens (Sub-tab, NEW)
│       ├── Actions Bar
│       │   └── [Refresh] [Start Scanner] [Stop Scanner]
│       │
│       └── Hot Tokens Table
│           ┌──────┬─────────┬────────┬──────────┬──────────┬────────────┬──────────┬──────────┐
│           │ Rank │ Symbol  │ Price  │ 24h Chg  │ Volume   │ Funding    │ L/S      │ Heat     │
│           ├──────┼─────────┼────────┼──────────┼──────────┼────────────┼──────────┼──────────┤
│           │  1   │ BTCUSDT │ 64.3K  │ +2.3%    │ 9.6B     │ 0.01%      │ 1.25     │ 0.89 🔥  │
│           │  2   │ ETHUSDT │ 3.5K   │ +1.8%    │ 4.2B     │ -0.02%     │ 1.15     │ 0.82 🔥  │
│           │ ...  │ ...     │ ...    │ ...      │ ...      │ ...        │ ...      │ ...      │
│           └──────┴─────────┴────────┴──────────┴──────────┴────────────┴──────────┴──────────┘
│           │ [Analyze] [Trade] │
│
└── Prediction (Tab)
    ├── Signals (Sub-tab)
    ├── Positions (Sub-tab)
    └── Trades (Sub-tab)
```

### 7.2 Data Binding

| Frontend | API / WebSocket | Data Fields |
|----------|----------------|-------------|
| Hot Tokens Table | WebSocket `hot_tokens_update` | All fields |
| Refresh Button | REST GET `/api/hot_tokens` | All fields |
| Start/Stop Scanner | REST POST `/api/hot_tokens/start\|stop` | Status |
| Analyze Button | REST POST `/:symbol/analyze` | sentiment, confidence, reasoning |
| Trade Button | REST POST `/:symbol/execute` | order_id, status |

## 8. Reuse Strategy

### 8.1 Reused Components

| Component | File | Reuse Method |
|-----------|------|-------------|
| Binance CCXT Connection | `binance_trader.py` | Direct import and instance |
| LLM Signal Analyzer | `signal_analyzer.py` | Direct import, pass token as content |
| Trading Engine | `trading_engine.py` | Direct import, wrap in execute method |
| WebSocket Broadcast | `api/ws.py` | Reuse existing runner.broadcast() or add broadcast method |
| Database Connection | `database.py` | Direct import, add `hot_tokens` table |

### 8.2 New Components

| Component | File | Purpose |
|-----------|------|---------|
| HotTokensScanner | `hot_tokens_scanner.py` | Core scanning logic |
| Hot Tokens API | `api/hot_tokens.py` | REST endpoints |
| Hot Tokens Tab | `TradingView.vue` sub-tab | Frontend display |

## 9. Configuration

### 9.1 config.json Fields (Added)

```json
{
  "hot_tokens_enabled": false,
  "hot_tokens_scan_interval": 60,
  "hot_tokens_max_results": 50,
  "hot_tokens_auto_execute": false,
  "hot_tokens_auto_threshold": 0.8,
  "hot_tokens_volume_weight": 0.5,
  "hot_tokens_change_weight": 0.3,
  "hot_tokens_funding_weight": 0.2
}
```

### 9.2 Default Values

| Config | Default | Description |
|--------|---------|-------------|
| enabled | false | Whether scanner is enabled |
| scan_interval | 60 | Seconds between scans |
| max_results | 50 | Max tokens to display |
| auto_execute | false | Auto trade on high confidence |
| auto_threshold | 0.8 | Confidence threshold for auto trade |

## 10. Error Handling & Recovery

### 10.1 Rate Limit
- **Strategy**: Use CCXT's built-in rate limiting (`enableRateLimit: True`)
- **Fallback**: If rate limited, retry after 1 second with exponential backoff

### 10.2 API Errors
- **Binance API unavailable**: Log warning, continue with cached data
- **CCXT timeout**: Retry up to 3 times, then skip this cycle
- **WebSocket disconnect**: Scanner continues, reconnect on next broadcast

### 10.3 Data Validation
- **Invalid price**: Filter out tokens with price <= 0
- **Invalid volume**: Filter out tokens with volume <= 0
- **Missing funding rate**: Default to 0, still include in ranking
