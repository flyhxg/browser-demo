# AI Trading System - Tasks

## Phase 1: Foundation
- [x] 1.1 Create database models and initialization
- [ ] 1.2 Create Binance API trading module (inspired by nofx-trading)
- [ ] 1.3 Create signal scraper service (Binance Square via browser automation)
- [ ] 1.4 Create signal analysis service (LLM integration)
- [ ] **1.5 Create short-selling analytics engine**
  - [ ] 1.5.1 Refactor `token_analyzer.py` to support multi-dimension queries
  - [ ] 1.5.2 Add on-chain data module (Arkham/Whale Alert)
  - [ ] 1.5.3 Add token unlock / FDV data module (CoinGecko extended)
  - [ ] 1.5.4 Add technical indicator module (K-lines + pandas-ta)
  - [ ] 1.5.5 Implement dynamic planning (Layer 3) vs fixed pipeline (Layer 2) routing

## Phase 2: Core Logic
- [ ] 2.1 Create filtering engine with configurable rules
- [ ] **2.2 Create short-selling analysis pipeline**
  - [ ] 2.2.1 Single-token deep analysis (funding + OI + liquidation)
  - [ ] 2.2.2 Multi-token comparison (sector/rank analysis)
  - [ ] 2.2.3 Event-driven analysis ("why did it drop?")
- [ ] 2.3 Create trading execution engine (position sizing, TP/SL)
- [ ] 2.4 Create cron/scheduler for automatic signal discovery
- [ ] 2.5 Create WebSocket event system for real-time updates

## Phase 3: API & Frontend
- [ ] 3.1 Create FastAPI endpoints (signals, trades, config)
- [ ] **3.2 Create short-selling analysis endpoint**
  - [ ] 3.2.1 `POST /api/analyze/short` - Deep short analysis for single token
  - [ ] 3.2.2 `POST /api/analyze/compare` - Multi-token comparison
  - [ ] 3.2.3 `GET /api/analyze/report/{token}` - Get cached analysis
- [ ] 3.3 Create frontend Signal Feed component
- [ ] 3.4 Create frontend Positions dashboard
- [ ] 3.5 Create frontend Trading Settings page
- [ ] 3.6 **Create frontend Short-Selling Analysis dashboard**
  - [ ] 3.6.1 Token selector with auto-complete
  - [ ] 3.6.2 Dimension toggles (derivatives / on-chain / technical / unlock)
  - [ ] 3.6.3 Visual report display (charts + LLM analysis)
- [ ] 3.7 Integrate WebSocket for real-time updates

## Phase 4: Testing & Polish
- [ ] 4.1 Test end-to-end flow with Binance Testnet
- [ ] **4.2 Test short-selling analysis with real tokens**
  - [ ] 4.2.1 Validate data accuracy across all 5 dimensions
  - [ ] 4.2.2 Compare LLM analysis quality vs manual analysis
  - [ ] 4.2.3 Stress test: multi-token concurrent analysis
- [ ] 4.3 Add error handling and recovery
- [ ] 4.4 Add logging and monitoring
- [ ] 4.5 Documentation
