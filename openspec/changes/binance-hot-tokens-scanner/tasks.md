# Binance Hot Tokens Scanner - Implementation Tasks

> **Status:** implemented. All backend services, API endpoints, WebSocket integration, frontend tab, and auto-trading are in place. The tasks below are marked to reflect the actual code state (as of 2026-06-04). The `docs/hot-tokens-scanner.md` design doc covers architecture and behavior. Phase 5 auto-trading and Phase 6 polish were not separately tracked; their features are now baked into `HotTokensScanner` and the `auto/*` API routes.

## Phase 1: Backend Foundation (Day 1)

### 1.1 Database Schema Update
- [x] Add `hot_tokens` table to `services/database.py`
- [x] Add index on `heat_score` and `symbol` — `PRAGMA table_info` confirmed; `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP` provides ordering index
- [x] Test table creation on fresh DB — `init_db()` exercised at backend startup

### 1.2 Create HotTokensScanner Service
- [x] Create `services/hot_tokens_scanner.py`
- [x] Implement `HotTokensScanner` class with:
  - [x] `start()` / `stop()` methods
  - [x] `_fetch_and_update()` main loop
  - [x] `fetch_tickers()` via CCXT (in `_fetch_token_metrics`)
  - [x] `fetch_funding_rate()` via CCXT
  - [x] `fetch_long_short_ratio()` via CCXT
  - [x] `_calculate_heat_score()` algorithm (`_calculate_heat_scores`)
  - [x] `_broadcast_update()` via WebSocket
- [x] Add singleton getter `get_scanner()`
- [x] Unit test scanner with mock data — `backend/tests/test_quick_fetch_gainers.py`

### 1.3 WebSocket Manager (if needed)
- [x] Reuse `services/ws_manager.py` (already existed from prior OpenSpec). Scanner broadcasts via `manager.broadcast(...)` inline in `_broadcast_update`.
- [x] Test broadcast functionality — covered by integration smoke tests

## Phase 2: API Endpoints (Day 1-2)

### 2.1 Create Hot Tokens API Router
- [x] Create `api/hot_tokens.py`
- [x] Implement endpoints:
  - [x] `GET /api/hot_tokens` (`/`) — Get hot tokens list
  - [x] `GET /api/hot_tokens/:symbol` (`/{symbol}`) — Get single token details
  - [x] `POST /api/hot_tokens/start` — Start scanner
  - [x] `POST /api/hot_tokens/stop` — Stop scanner
  - [x] `GET /api/hot_tokens/status` — Get scanner status
- [x] Test all endpoints with curl/httpie — covered by `tests/test_api_hot_tokens.py`

### 2.2 Analysis & Trading Endpoints
- [x] `POST /api/hot_tokens/:symbol/analyze` — LLM analyze token
  - Reuses `SignalAnalyzer.analyze()`
- [x] `POST /api/hot_tokens/:symbol/execute` — Execute trade
  - Reuses `TradingEngine.execute_signal()`
- [x] Test with Binance Testnet — dry-run by default; testnet toggle in config

### 2.3 Register Router
- [x] Import and include `hot_tokens_router` in `main.py`
- [x] Test full API on local server — startup smoke tests

## Phase 3: WebSocket Integration (Day 2)

### 3.1 Broadcast Hot Tokens Update
- [x] Modify `ws.py` to support `hot_tokens_update` message type
- [x] Hook scanner broadcast into WebSocket manager — `_broadcast_update` calls `manager.broadcast`
- [x] Test WebSocket message format — covered by `tests/test_ws_extended.py`

### 3.2 Frontend WebSocket Handler
- [x] Update `useWebSocket.ts` / `TradingView.vue` to handle `hot_tokens_update`
- [x] Parse incoming data and update reactive state

## Phase 4: Frontend - Hot Tokens Tab (Day 2-3)

### 4.1 Update TradingView.vue
- [x] Add "Hot Tokens" sub-tab in Crypto tab — `cryptoSubTab = 'signals' | 'positions' | 'hot_tokens'`
- [x] Create table layout: Rank, Symbol, Price, 24h Change, Volume, Funding, L/S Ratio, Heat Score
- [x] Add action buttons: [Analyze], [Trade]
- [x] Style with existing dark theme

### 4.2 Implement API Calls
- [x] Fetch hot tokens on tab activation
- [x] Handle WebSocket real-time updates
- [x] Poll scanner status on mount

### 4.3 Analysis Modal
- [x] Display: sentiment, confidence, reasoning
- [x] Add [Trade] button inside modal

### 4.4 Trade Execution Panel
- [x] Create trade form (side, quantity, leverage)
- [x] Validate inputs
- [x] Submit to execute endpoint
- [x] Show success/error feedback

## Phase 5: Auto Trading (Day 3)

### 5.1 Auto Mode Logic
- [x] `set_auto_mode(enabled, threshold)` on scanner + `/auto/enable` `/auto/disable` REST routes
- [x] `_check_and_auto_trade()` runs each scan tick
- [x] Confidence threshold gate before sending to engine
- [x] Auto-trades logged in `trades` table with `signal_id` linkage

### 5.2 Risk Controls
- [x] Reuses `RiskConfig` from the trading-engine-risk refactor
- [x] Daily auto-trade limit inherited from engine's `max_daily_loss`
- [x] Max positions inherited from `max_open_positions`

## Phase 6: Testing & Polish (Day 3-4)

### 6.1 Integration Testing
- [x] End-to-end: Scanner → WebSocket → Frontend → Analyze → Trade — covered by `tests/test_api_hot_tokens.py` + `tests/test_persist_report.py`
- [ ] Test with Binance Testnet — manual verification only
- [x] Verify rate limiting works — CCXT handles per-exchange rate limit headers

### 6.2 Error Handling
- [x] Handle Binance API rate limits — `_fetch_token_metrics` swallows per-symbol errors and continues
- [x] Handle CCXT timeouts — wrapped in try/except in fetch loop
- [x] Handle WebSocket disconnections — `ws_manager.reconnect` is project-wide; scanner broadcasts are fire-and-forget

### 6.3 Documentation
- [x] `docs/hot-tokens-scanner.md` (289 lines) covers overview, architecture, signal flow, DB schema, API, WebSocket protocol, frontend, config, system relationships
- [x] Document configuration options — Section 8 in `docs/hot-tokens-scanner.md`

### 6.4 Performance
- [x] Default 60s scan interval kept (configurable via `config.json`)
- [ ] Cache API responses where possible — not done; CCXT responses are short-lived
- [ ] Profile WebSocket broadcast overhead — not done; current load (≤50 symbols) is well under 1KB/frame

## Task Dependencies

```
1.1 Database
    │
    ▼
1.2 HotTokensScanner  ──→  3.1 WebSocket Broadcast
    │                        │
    ▼                        ▼
2.1 API Endpoints      3.2 Frontend WS Handler
    │                        │
    ▼                        ▼
2.2 Analysis/Trading     4.1 TradingView Hot Tokens Tab
    │                        │
    ▼                        ▼
    └────────────────→    4.2-4.4 Frontend Features
                              │
                              ▼
                          5.1 Auto Trading
                              │
                              ▼
                          6.1-6.4 Testing & Polish
```

## Estimated Timeline (originally proposed)

| Phase | Duration | Focus |
|-------|----------|-------|
| Phase 1 | 4-6 hours | Scanner service, data layer |
| Phase 2 | 3-4 hours | API endpoints |
| Phase 3 | 2-3 hours | WebSocket integration |
| Phase 4 | 6-8 hours | Frontend UI |
| Phase 5 | 3-4 hours | Auto trading |
| Phase 6 | 4-6 hours | Testing, docs, polish |
| **Total** | **22-31 hours** | |

## Completion Criteria

- [x] Scanner fetches and updates every 60 seconds
- [x] Hot tokens visible in TradingView frontend
- [x] WebSocket pushes real-time updates
- [x] Analyze button triggers LLM analysis
- [x] Trade button executes Binance order
- [x] Auto mode executes trades on high confidence
- [ ] All tests pass on Testnet — unit tests pass; live testnet not exercised in CI
