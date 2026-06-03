# Binance Hot Tokens Scanner - Implementation Tasks

## Phase 1: Backend Foundation (Day 1)

### 1.1 Database Schema Update
- [ ] Add `hot_tokens` table to `services/database.py`
- [ ] Add index on `heat_score` and `symbol`
- [ ] Test table creation on fresh DB

### 1.2 Create HotTokensScanner Service
- [ ] Create `services/hot_tokens_scanner.py`
- [ ] Implement `HotTokensScanner` class with:
  - `start()` / `stop()` methods
  - `_fetch_and_update()` main loop
  - `fetch_tickers()` via CCXT
  - `fetch_funding_rate()` via CCXT
  - `fetch_long_short_ratio()` via CCXT
  - `_calculate_heat_score()` algorithm
  - `_broadcast_update()` via WebSocket
- [ ] Add singleton getter `get_scanner()`
- [ ] Unit test scanner with mock data

### 1.3 WebSocket Manager (if needed)
- [ ] Create `services/ws_manager.py` for broadcasting
- [ ] Test broadcast functionality

## Phase 2: API Endpoints (Day 1-2)

### 2.1 Create Hot Tokens API Router
- [ ] Create `api/hot_tokens.py`
- [ ] Implement endpoints:
  - `GET /api/hot_tokens` - Get hot tokens list
  - `GET /api/hot_tokens/:symbol` - Get single token details
  - `POST /api/hot_tokens/start` - Start scanner
  - `POST /api/hot_tokens/stop` - Stop scanner
  - `GET /api/hot_tokens/status` - Get scanner status
- [ ] Test all endpoints with curl/httpie

### 2.2 Analysis & Trading Endpoints
- [ ] `POST /api/hot_tokens/:symbol/analyze` - LLM analyze token
  - Reuse `SignalAnalyzer.analyze()`
- [ ] `POST /api/hot_tokens/:symbol/execute` - Execute trade
  - Reuse `TradingEngine.execute_signal()`
- [ ] Test with Binance Testnet

### 2.3 Register Router
- [ ] Import and include `hot_tokens_router` in `main.py`
- [ ] Test full API on local server

## Phase 3: WebSocket Integration (Day 2)

### 3.1 Broadcast Hot Tokens Update
- [ ] Modify `ws.py` to support `hot_tokens_update` message type
- [ ] Hook scanner broadcast into WebSocket manager
- [ ] Test WebSocket message format

### 3.2 Frontend WebSocket Handler
- [ ] Update `useWebSocket.ts` or `TradingView.vue` to handle `hot_tokens_update`
- [ ] Parse incoming data and update reactive state

## Phase 4: Frontend - Hot Tokens Tab (Day 2-3)

### 4.1 Update TradingView.vue
- [ ] Add "Hot Tokens" sub-tab in Crypto tab
- [ ] Create table layout:
  - Rank, Symbol, Price, 24h Change, Volume, Funding, L/S Ratio, Heat Score
- [ ] Add action buttons: [Analyze], [Trade]
- [ ] Style with existing dark theme

### 4.2 Implement API Calls
- [ ] Fetch hot tokens on tab activation
- [ ] Handle WebSocket real-time updates
- [ ] Poll scanner status on mount

### 4.3 Analysis Modal
- [ ] Create modal/dialog for LLM analysis results
- [ ] Display: sentiment, confidence, reasoning
- [ ] Add [Trade] button inside modal

### 4.4 Trade Execution Panel
- [ ] Create trade form (side, quantity, leverage)
- [ ] Validate inputs
- [ ] Submit to execute endpoint
- [ ] Show success/error feedback

## Phase 5: Auto Trading (Day 3)

### 5.1 Auto Mode Logic
- [ ] Add `hot_tokens_auto_execute` config
- [ ] Implement auto-analyze on high heat tokens
- [ ] Check confidence threshold before auto-trade
- [ ] Log auto-trades separately

### 5.2 Risk Controls
- [ ] Reuse TradingEngine risk management
- [ ] Add daily auto-trade limit
- [ ] Add max positions check

## Phase 6: Testing & Polish (Day 3-4)

### 6.1 Integration Testing
- [ ] End-to-end: Scanner → WebSocket → Frontend → Analyze → Trade
- [ ] Test with Binance Testnet
- [ ] Verify rate limiting works

### 6.2 Error Handling
- [ ] Handle Binance API rate limits
- [ ] Handle CCXT timeouts
- [ ] Handle WebSocket disconnections

### 6.3 Documentation
- [ ] Update `CONTEXT.md` with new terms
- [ ] Add API documentation to `docs/hot-tokens-scanner.md`
- [ ] Document configuration options

### 6.4 Performance
- [ ] Optimize scan interval (current: 60s)
- [ ] Cache API responses where possible
- [ ] Profile WebSocket broadcast overhead

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

## Estimated Timeline

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

- [ ] Scanner fetches and updates every 60 seconds
- [ ] Hot tokens visible in TradingView frontend
- [ ] WebSocket pushes real-time updates
- [ ] Analyze button triggers LLM analysis
- [ ] Trade button executes Binance order
- [ ] Auto mode executes trades on high confidence
- [ ] All tests pass on Testnet
