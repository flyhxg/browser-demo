# AI Trading System - Design Document

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Frontend (Vue 3)                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ Signal Feed  │  │  Positions   │  │   Settings   │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │
│  │ /api/signals│  │ /api/trades │  │ /api/config │  │   /ws    │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └──────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│ Signal Scraper │  │ Signal Analyzer│  │ Trading Engine │
│ (browser-use)  │  │    (LLM)       │  │ (Binance API) │
└────────────────┘  └────────────────┘  └────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│   CoinGecko    │  │      OKX       │  │  Hyperliquid │
└────────────────┘  └────────────────┘  └────────────────┘
```

## Data Flow

### 1. Signal Discovery (Cron: every 5 min)
```
Cron Trigger
    │
    ▼
browser-use → Binance Square
    │
    ▼
Extract posts (title, content, likes, comments, author)
    │
    ▼
Filter posts with token mentions ($XXX, #XXX)
    │
    ▼
Store in Signal Queue
```

### 2. Signal Analysis (Async)
```
Signal Queue
    │
    ▼
LLM Analysis (MiniMax-M2.7)
    │
    ├─→ Extract token symbols
    ├─→ Sentiment analysis (bullish/bearish/neutral)
    ├─→ Confidence score (0-1)
    └─→ Reasoning summary
    │
    ▼
Enriched Signal
```

### 3. Market Validation
```
Enriched Signal
    │
    ▼
Parallel Data Fetch:
    ├─→ CoinGecko: market_cap, 24h_change, volume
    ├─→ OKX: funding_rate, open_interest
    └─→ Hyperliquid: funding, mark_price
    │
    ▼
Filtering Engine (configurable rules)
    │
    ▼
Valid / Invalid Signal
```

### 4. Trade Execution
```
Valid Signal
    │
    ▼
Risk Management
    ├─→ Position sizing (based on balance %)
    ├─→ Max positions check
    └─→ Daily loss limit check
    │
    ▼
Binance API
    ├─→ Place market order (Spot or Futures)
    └─→ Set TP/SL orders
    │
    ▼
Trade Record → Database → WebSocket → Frontend
```

## Database Schema (SQLite)

```sql
-- Signals discovered from Binance Square
CREATE TABLE signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,              -- 'binance_square'
    source_url TEXT,
    author TEXT,
    content TEXT NOT NULL,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    raw_data TEXT,                    -- JSON of original post
    status TEXT DEFAULT 'pending',    -- pending/analyzed/valid/invalid/executed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- LLM Analysis results
CREATE TABLE signal_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL,
    token TEXT NOT NULL,
    sentiment TEXT,                  -- bullish/bearish/neutral
    confidence REAL,                   -- 0.0 - 1.0
    reasoning TEXT,
    llm_model TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (signal_id) REFERENCES signals(id)
);

-- Market data validation
CREATE TABLE signal_validation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL,
    token TEXT NOT NULL,
    cg_market_cap_rank INTEGER,
    cg_price_change_24h REAL,
    okx_funding_rate REAL,
    hyperliquid_funding REAL,
    validation_result TEXT,            -- pass/fail
    fail_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (signal_id) REFERENCES signals(id)
);

-- Trade execution records
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    token TEXT NOT NULL,
    side TEXT NOT NULL,                -- buy/sell
    exchange TEXT DEFAULT 'binance',
    market_type TEXT,                  -- spot/futures
    order_id TEXT,
    quantity REAL,
    price REAL,
    tp_price REAL,
    sl_price REAL,
    status TEXT DEFAULT 'pending',     -- pending/filled/cancelled/error
    pnl REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (signal_id) REFERENCES signals(id)
);

-- Trading configuration
CREATE TABLE trading_config (
    id INTEGER PRIMARY KEY,
    binance_api_key TEXT,
    binance_secret_key TEXT,
    use_testnet INTEGER DEFAULT 1,     -- 1 = testnet, 0 = production
    max_position_size_usd REAL DEFAULT 100.0,
    max_positions INTEGER DEFAULT 5,
    tp_percentage REAL DEFAULT 5.0,    -- 5% take profit
    sl_percentage REAL DEFAULT 3.0,    -- 3% stop loss
    min_confidence REAL DEFAULT 0.7,   -- minimum LLM confidence
    max_daily_loss REAL DEFAULT 100.0, -- max daily loss in USD
    scan_interval_minutes INTEGER DEFAULT 5
);
```

## API Design

### Signals
- `GET /api/signals` - List all signals with filters
- `GET /api/signals/{id}` - Get single signal with analysis
- `POST /api/signals/{id}/validate` - Manually trigger validation

### Trading
- `POST /api/trades` - Execute manual trade
- `GET /api/trades` - List trade history
- `GET /api/positions` - Current positions
- `POST /api/positions/{id}/close` - Close position

### Configuration
- `GET /api/trading/config` - Get trading configuration
- `PUT /api/trading/config` - Update configuration
- `POST /api/trading/config/test-connection` - Test Binance API

### WebSocket Events
- `signal:new` - New signal discovered
- `signal:analyzed` - Signal analyzed by LLM
- `trade:executed` - Trade executed
- `trade:closed` - Position closed

## Key Implementation Notes

### Binance Square Scraping
- Use browser-use with stealth mode to avoid detection
- Handle login if required (cookies/session)
- Extract: post content, likes, comments, author, timestamp
- Filter for token mentions using regex: `\$[A-Z]{2,10}` and `#?[A-Z]{2,10}`

### LLM Analysis Prompt
```
Analyze the following social media post about cryptocurrency trading.
Extract the following:
1. Token symbols mentioned (e.g., BTC, ETH, SOL)
2. Sentiment: bullish, bearish, or neutral
3. Confidence score (0.0 - 1.0)
4. Key reasoning points

Post: {content}

Respond in JSON format:
{
    "tokens": ["SOL", "ETH"],
    "sentiment": "bullish",
    "confidence": 0.85,
    "reasoning": "Post mentions..."
}
```

### Filtering Rules (Configurable)
- Token must have market cap rank < 500 (avoid super low-cap)
- 24h price change must be between -30% and +50% (avoid suspicious pumps)
- Funding rate must be < 0.05% (avoid overcrowded longs)
- LLM confidence must be > 0.7

### Risk Management
- Position size = min(balance * 0.02, max_position_size_usd)
- Max 5 concurrent positions
- Daily loss limit enforced
- Auto-cancel conflicting orders
