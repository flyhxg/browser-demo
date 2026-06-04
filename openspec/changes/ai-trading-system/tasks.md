# AI Trading System - Tasks

## Phase 1: Foundation
- [x] 1.1 Create database models and initialization
- [x] 1.2 Create Binance API trading module (inspired by nofx-trading)
- [x] 1.3 Create signal scraper service (Binance Square via browser automation)
- [x] 1.4 Create signal analysis service (LLM integration)
- [x] **1.5 Create short-selling analytics engine**
  - [x] 1.5.1 Refactor `token_analyzer.py` to support multi-dimension queries
  - [x] 1.5.2 Add on-chain data module (Arkham/Whale Alert)
  - [x] 1.5.3 Add token unlock / FDV data module (CoinGecko extended)
  - [x] 1.5.4 Add technical indicator module (K-lines + pandas-ta)
  - [x] 1.5.5 Implement dynamic planning (Layer 3) vs fixed pipeline (Layer 2) routing — `services/intent_router.py`, commit 07f47d5

## Phase 2: Core Logic
- [x] 2.1 Create filtering engine with configurable rules — `services/filter_engine.py` exists, wired into `api/trading.py:validate_signal_endpoint` in commit a4d0b95
- [x] **2.2 Create short-selling analysis pipeline**
  - [x] 2.2.1 Single-token deep analysis (funding + OI + liquidation) — `ShortSellingEngine.analyze()`
  - [x] 2.2.2 Multi-token comparison (sector/rank analysis) — `IntentRouter._route_layer3` + `compare()`
  - [ ] 2.2.3 Event-driven analysis ("why did it drop?") — Layer 3 LLM synthesis handles free-form questions; dedicated event-driven sub-pipeline not yet built
- [x] 2.3 Create trading execution engine (position sizing, TP/SL)
- [ ] 2.4 Create cron/scheduler for automatic signal discovery — **still missing**
- [x] 2.5 Create WebSocket event system for real-time updates

## Phase 3: API & Frontend
- [x] 3.1 Create FastAPI endpoints (signals, trades, config)
- [x] **3.2 Create short-selling analysis endpoint**
  - [x] 3.2.1 `POST /api/analyze/short` — `api/analysis.py:analyze_short`
  - [x] 3.2.2 `POST /api/analyze/compare` — `api/analysis.py:analyze_compare`
  - [x] 3.2.3 `GET /api/analyze/report/{token}` — `api/analysis.py:get_cached_report`
- [x] 3.3 Create frontend Signal Feed component
- [x] 3.4 Create frontend Positions dashboard
- [x] 3.5 Create frontend Trading Settings page
- [x] 3.6 **Create frontend Short-Selling Analysis dashboard**
  - [x] 3.6.1 Token selector with auto-complete
  - [x] 3.6.2 Dimension toggles (derivatives / on-chain / technical / unlock)
  - [x] 3.6.3 Visual report display (charts + LLM analysis)
- [x] 3.7 Integrate WebSocket for real-time updates

## Phase 4: Testing & Polish
- [ ] 4.1 Test end-to-end flow with Binance Testnet
- [ ] **4.2 Test short-selling analysis with real tokens**
  - [ ] 4.2.1 Validate data accuracy across all 5 dimensions
  - [ ] 4.2.2 Compare LLM analysis quality vs manual analysis
  - [ ] 4.2.3 Stress test: multi-token concurrent analysis
- [x] 4.3 Add error handling and recovery — `_run_llm_analysis` never raises; `IntentRouter._llm_plan` + `_synthesize` time out gracefully
- [x] 4.4 Add logging and monitoring
- [x] 4.5 Documentation

## Short-Selling MVP Wrap-Up (2026-06-04)

The "做空分析 MVP" subset was delivered in 4 commits on top of the
prior work:

- `a4d0b95` — real LLM analysis in `ShortSellingEngine` + wired
  `filter_engine` into the signal validation endpoint
- `07f47d5` — Layer 2/3 `IntentRouter` with LLM planning + cross-
  token synthesis
- `d48dda7` — sector memory + search index in `memory_manager`
- 36 new tests across 3 new test files (test_short_selling_llm,
  test_intent_router, test_memory_manager_sectors). All pass.
- Master HEAD now at d48dda7 with 108 backend tests passing.

**Remaining gaps in this OpenSpec:**

1. **Phase 2.4 — scheduler** — no `services/scheduler.py` for cron-
   triggered signal discovery. The signal_scraper / signal_poller
   pattern is in place; wiring it to a cron is a small lift (~2-3h).
2. **Phase 2.2.3 — dedicated event-driven sub-pipeline** — Layer 3
   LLM synthesis handles free-form "why did X drop" questions via
   plan-then-execute, but no specialized "news + on-chain +
   derivatives" pipeline exists.
3. **Phase 4.1 / 4.2 — live testnet + multi-token stress tests** —
   no CI-runnable test exercises the full Binance testnet flow.
