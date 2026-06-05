# Auto-LLM Signal Pipeline + Decision Visibility — Design Spec

**Date:** 2026-06-05
**Status:** Draft
**Supersedes:** `2026-06-05-binance-square-real-scraper-design.md` (scraper strategy changes from HTML parsing to API response interception; everything else in that spec is still valid)
**Related:** `2026-06-03-ai-trading-system-design.md` (vision), `2026-06-04-signal-scan-scheduler-design.md` (scheduler foundation)

## Problem

A Binance Square post hits the `signals` table, then sits there as text + likes/comments. The user has no way to know:

1. **Is this an actual trade signal?** LLM judgment is never applied automatically — `SignalAnalyzer.analyze()` is a manual button (`POST /api/trading/signals/{id}/validate`).
2. **Why did the LLM say what it said?** Reasoning is buried in `signal_analysis.reasoning` and shown small; no easy comparison to the original post.
3. **Is the LLM reliable?** No feedback loop. After a long call, the user can't mark "this was right" or "this was hype" — so the same unreliable signals keep coming.
4. **The scraper itself is broken on Windows.** `chromium.launch()` raises `NotImplementedError` in Python 3.14 asyncio subprocess on Windows. The existing HTML-parse approach in `binance_square_browser.py` was approved in the previous spec but cannot actually run on this machine.

Without a working scraper + automatic LLM + visible decision chain, the trading desk can't be evaluated.

## Goals

- Scraper works on Windows (Python 3.14) by switching from `chromium.launch()` to `chromium.launch_persistent_context()` and from HTML parsing to API response interception.
- Every newly inserted signal row is automatically analyzed by LLM (`fire-and-forget` background task; never blocks the scheduler tick).
- LLM output is fully visible: tokens, sentiment, `is_trade_signal`, `action`, `confidence`, **and a one-sentence reasoning chain that names the project's quality / context / why the post matters**.
- User can mark a signal 👍 / 👎 on every card. Feedback is persisted and exposed in a small stats strip so the user can watch reliability trend.
- User can still choose to Execute or Skip manually. No auto-execution. Goal is observation first, automation later.

## Non-Goals

- Auto-executing trades based on LLM output
- Backfilling LLM analysis onto the 113 existing rows (only new posts get analyzed)
- Changing the trading engine or risk config
- KOL detection / follower-based filtering (out of scope; can be added later as a dimension)
- Hot-tab ranking (separately scoped — keep the spec tight)

## Architecture

```
SignalScanScheduler._tick (every 30 min)
    │
    ▼
BinanceSquareScraper.scrape(limit=20)
    │
    ▼
BinanceSquareBrowser.fetch_posts (Playwright persistent context)
    │  - launch_persistent_context with user_data_dir (one-time login)
    │  - page.on("response") intercepts /pgc/feed JSON
    │  - _scan_for_posts recursively walks JSON, picks "post-shaped" objects
    │  - returns list[dict] with author, content, likes, comments, shares, posted_at, tradingPairs
    │
    ▼
save_to_db → INSERT OR IGNORE
    │
    ▼  (returns inserted signal_ids)
for each new signal_id:
    asyncio.create_task(_analyze_and_persist(signal_id))  ← NEW: auto-LLM
        │
        ▼
    SignalAnalyzer.analyze(content)
        prompt: "Read this post. Use your knowledge of the project / market to decide:
                 tokens, sentiment, is_trade_signal, action, confidence, reasoning"
        │
        ▼
    UPDATE signal_analysis SET is_trade_signal, action, confidence, reasoning
    UPDATE signals      SET trade_action, trade_confidence, is_trade_signal, analyzed_at
    ws broadcast "signal:analyzed"
```

**Reasoning/verification UI lives in TradingView and is the centerpiece of this spec** (see UI section below).

## Components

### 1. Scraper — port AlphaHunter's API interception pattern

**Replace** the current `_parse_html` HTML-parse path with an API-response interception path. Rationale:
- API responses are stable JSON. DOM is fragile.
- Binance's `/pgc/feed` endpoint already returns author + likes + comments + shares + `tradingPairs` + real `posted_at` timestamp.
- `chromium.launch_persistent_context` + `user_data_dir` lets the login state persist on disk → no need to re-login every scrape (one-time manual login via a new `scripts/login_binance.py`).

**Files:**
- `backend/services/binance_square_browser.py` — replace `_get_or_launch_page` with `launch_persistent_context`; add `page.on("response", _handle_response)`; add `_scan_for_posts` recursive walker; keep HTML parser as `fallback=True` opt-in.
- `scripts/login_binance.py` — new; one-time manual login (headless=False), writes cookies to `.env`, saves browser profile to `data/playwright_user_data/`.
- `backend/services/square_scraper.py` — new; wraps `BinanceSquareBrowser` as a singleton `ScraperManager` with health checks (see below).
- `backend/services/signal_scraper.py` — keep `save_to_db` API, expand to capture `shares` + `posted_at` + `tradingPairs` from API responses (new columns, see schema).
- `backend/tests/fixtures/binance_square/pgc_feed.json` — new; captured API response for offline tests.
- `backend/tests/test_binance_square_browser.py` — extend with API-interception test.

**ScraperManager** — minimal, not the AlphaHunter version:

```python
class ScraperManager:
    """Long-lived playwright context. Restart only on disconnect or memory pressure."""

    _instance = None
    _playwright = None
    _context = None
    MEMORY_THRESHOLD_MB = 800   # higher than AlphaHunter's 600 — we run 30 min idle, no leak pressure
    IDLE_RELOAD_SECONDS = 20 * 60   # match existing

    async def get_context(self) -> BrowserContext: ...
    async def _restart_if_unhealthy(self) -> None: ...
```

Restart policy:
- If `context.browser is None or not context.browser.is_connected` → restart
- If RSS (process + children) > 800MB → restart
- **No round-count restart** (with 30-min scrape cadence, 30 rounds = 15 hours — restart would never fire anyway, and if it did it'd discard warm session)
- If `last_fetch_at` > 20 min ago → fresh `page.goto` (reuses context)

### 2. LLM auto-pipeline

**Modify `SignalScanScheduler._tick`** so after `save_to_db` returns the inserted ids, it spawns a background task per id:

```python
async def _tick(self) -> None:
    try:
        posts = await self.scraper.scrape(limit=20)
    except Exception as e:
        logger.warning(f"[SignalScanScheduler] scrape failed: {e}")
        return
    if not posts:
        self._last_run = time.time()
        return
    try:
        new_ids = self.scraper.save_to_db(posts)   # CHANGED: returns list of new signal_ids
    except Exception as e:
        logger.error(f"[SignalScanScheduler] save_to_db failed: {e}", exc_info=True)
        return
    self._last_run = time.time()
    for sid in new_ids:
        asyncio.create_task(self._analyze_one(sid), name=f"analyze-{sid}")
    if self._ws_broadcast:
        for post in posts:
            await self._ws_broadcast("signal:new", post)

async def _analyze_one(self, signal_id: int) -> None:
    try:
        sig = _load(signal_id)
        result = await SignalAnalyzer().analyze(sig["content"])
        _persist_analysis(signal_id, result)
        _persist_decision(signal_id, result)         # UPDATE signals
        if self._ws_broadcast:
            await self._ws_broadcast("signal:analyzed", {"id": signal_id, **result})
    except Exception as e:
        logger.warning(f"[SignalScanScheduler] analyze {signal_id} failed: {e}")
```

**Modify `SignalAnalyzer.analyze`** prompt to return the new structure:

```python
SYSTEM = """You are a senior crypto trading analyst. You know every major token
(BTC, ETH, SOL, BNB, ...) — its market cap, project quality, recent news,
typical volatility. You can distinguish a real signal from hype, sarcasm,
reshare, or paid shill."""

PROMPT = """Read this Binance Square post and decide if it's a trade signal.

Post:
\"\"\"
{content}
\"\"\"

Return JSON only, no prose:
{{
  "tokens": ["SOL"],                  // symbols actually discussed
  "sentiment": "bullish|bearish|neutral",
  "is_trade_signal": true,            // real actionable signal vs hype/sarcasm/reshare
  "action": "long|short|null",        // null when is_trade_signal=false
  "confidence": 0.82,                 // 0-1
  "reasoning": "One sentence: why this is/isn't a trade signal, naming the project or context that informed the judgment."
}}
"""
```

`_parse_response` keeps existing JSON-extraction (handles ```json``` blocks, thinking text, etc.) and additionally returns `is_trade_signal` and `action` from the parsed object. When the LLM is not configured, returns the existing default dict (all nulls) so the user sees a clear "not analyzed" state in the UI.

### 3. Schema extensions

In `services/database.py` `init_db()`:

```sql
-- signals table: one row per post. Add LLM decision columns.
ALTER TABLE signals ADD COLUMN trade_action TEXT;          -- 'long' | 'short' | null
ALTER TABLE signals ADD COLUMN trade_confidence REAL;      -- 0.0 - 1.0
ALTER TABLE signals ADD COLUMN is_trade_signal INTEGER DEFAULT 0;  -- 0|1
ALTER TABLE signals ADD COLUMN analyzed_at TIMESTAMP;      -- LLM finished
ALTER TABLE signals ADD COLUMN shares INTEGER DEFAULT 0;    -- from API interception
ALTER TABLE signals ADD COLUMN posted_at TEXT;             -- real post time (ms epoch ISO)
ALTER TABLE signals ADD COLUMN trading_pairs TEXT;         -- JSON list, from Binance

-- signal_analysis: history of analyses (1:N). Add same LLM columns.
ALTER TABLE signal_analysis ADD COLUMN is_trade_signal INTEGER;
ALTER TABLE signal_analysis ADD COLUMN action TEXT;
-- reasoning, confidence, sentiment, tokens, llm_model already exist

-- New: signal_feedback — user 👍/👎
CREATE TABLE IF NOT EXISTS signal_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL,
    feedback TEXT NOT NULL,             -- 'good' | 'bad'
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (signal_id) REFERENCES signals(id)
);
CREATE INDEX IF NOT EXISTS idx_signal_feedback_signal ON signal_feedback(signal_id);
```

All migrations idempotent via `PRAGMA table_info`.

`save_to_db` INSERT statement extended with the new columns. `INSERT OR IGNORE` still keyed on `source_url` UNIQUE index.

### 4. API additions

Extend existing endpoints — no new top-level routes:

| Method | Path | Change |
|---|---|---|
| GET | `/api/trading/signals` | response already includes all `signals.*` cols; verify `trade_action`/`trade_confidence`/`is_trade_signal`/`reasoning` are returned. Add `?feedback=mine` to filter to signals the user has 👍/👎'd. |
| POST | `/api/trading/signals/{id}/validate` | unchanged — still manual re-analyze |
| POST | `/api/trading/signals/{id}/skip` | **new** — sets `is_trade_signal=0` and `trade_action=null` (user override) |
| POST | `/api/trading/signals/{id}/feedback` | **new** — body `{feedback: "good"|"bad", comment?: str}` → INSERT into `signal_feedback` |
| GET | `/api/trading/signals/stats` | **new** — `{total, good, bad, accuracy_pct, last_24h: {total, good, bad}}` |

### 5. TradingView — Decision Visibility is the centerpiece

The user said: "我说的怎么验证" (how do I verify). UI must make the LLM's reasoning chain and the user's feedback loop unmissable.

**Per-signal card layout** (replacing the current compact `signal-analysis` block):

```
┌──────────────────────────────────────────────────────────────────┐
│ binance_square · 5m ago                                    [pending] │
│                                                                  │
│ 📈 LONG  SOL                                  confidence 82% ▓▓▓▓░ │
│                                                                  │
│ "$SOL is about to break out of the descending wedge.              │
│  Funding just flipped negative and the team shipped a major       │
│  update yesterday. Real momentum here."                           │
│                                                                  │
│ ── LLM reasoning ─────────────────────────────────────────────── │
│ "Project is top-10 by market cap, recently listed perps on        │
│  Binance, funding went negative suggesting short squeeze setup.   │
│  Post names specific technical level — not generic hype."         │
│                                                                  │
│ 👤 AuthorKOL · 18 ❤️ · 4 💬 · 2 ↗                                 │
│                                                                  │
│ [👍 Good signal]  [👎 Bad signal]  [Skip]  [Execute Long]          │
└──────────────────────────────────────────────────────────────────┘
```

Rules:
- **Action badge is the largest element on the card.** `📈 LONG` (green) / `📉 SHORT` (red) / `⚪ NO SIGNAL` (gray). No badge if LLM hasn't finished yet.
- **Reasoning block is a quoted block, visually distinct** from the post content. LLM's reasoning is the user's primary verification surface.
- **Confidence as a horizontal bar** (not a number alone).
- **Execute button is only enabled when `is_trade_signal=1`.** Style: solid green for long, solid red for short.
- **👍/👎 buttons always enabled.** Click → POST to `/feedback`. Selected state is sticky.
- **Skip** sets `is_trade_signal=0` via `/skip`. Distinct from "Bad signal" — skip is a UI-level hide, bad is a quality rating.

**Stats strip above the feed:**

```
┌────────────────────────────────────────────────────┐
│ 24h: 12 signals · 8 long · 3 short · 1 skip       │
│ 👍 7 / 👎 2  ·  accuracy 78%                       │
└────────────────────────────────────────────────────┘
```

Reload every 30s. Read from `/api/trading/signals/stats`.

### 6. TradingView changes — exact Vue deltas

In `frontend/src/views/TradingView.vue`:

- Replace the `signal-analysis` div with a new `signal-decision` div (action badge + confidence bar + reasoning block).
- Add `feedbackButtons` block below the reasoning.
- Wire `sendFeedback(signalId, 'good'|'bad')` and `skipSignal(signalId)` to the new endpoints.
- Add a `stats` ref fed by `/api/trading/signals/stats`; re-render every 30s.
- Pass the new fields through the existing `Signal` interface in `frontend/src/types/index.ts`.

### 7. Tests

- `test_binance_square_browser.py`: extend with API-interception mock. Inject a `page` whose `page.on("response", cb)` triggers a stubbed `/pgc/feed` response from a fixture; assert `_scan_for_posts` picks the right objects.
- `test_signal_scraper.py`: assert `save_to_db` returns new ids; assert new columns get populated.
- `test_signal_analyzer.py`: snapshot LLM response shape (mock `llm.ainvoke`); assert prompt contains the new fields.
- `test_scheduler.py`: assert `_tick` spawns `_analyze_one` tasks for each new id; assert a failing LLM does not break the next tick.
- `test_signals_api.py`: assert new fields returned; `/skip` updates; `/feedback` inserts; `/stats` aggregates.
- `test_signals_feedback.py` (new): feedback table CRUD.
- Headless e2e: `tests/test_signals_pipeline_headless.py` — fake scraper + fake analyzer + real DB + real API; assert end-to-end flow.

## Configuration

In `config_store.DEFAULT_CONFIG`:

```python
"binance_user_data_dir": "data/playwright_user_data",   # NEW
"binance_cookies": "",                                   # NEW: optional, written by login_binance.py
"signal_auto_analyze": True,                             # NEW: kill switch for the auto-LLM step
```

If `binance_cookies` is empty, scraper proceeds without login (public feed). The login is a one-time setup, not a per-tick requirement.

## Risks

- **Binance changes `/pgc/feed` shape.** Mitigated: `_looks_like_post` heuristic only needs `content` + `author` + `engagement` keys. If those three stay, we survive any field rename.
- **LLM latency under burst.** 20 posts / tick × ~3s LLM each = 60s of background work. Fire-and-forget tasks are fine; the next tick won't queue on them. If LLM provider rate-limits, analyze tasks fail individually; the signal still has `is_trade_signal=0` (the default) and the user can manually validate.
- **Login state corruption.** `user_data_dir` could expire (Binance rotates session cookies). Mitigated: `is_connected` check + retry-with-cookie path; if persistent context fails, fall back to public feed (no login) — same as today's behavior.
- **Existing 113 mock/historical rows have no LLM analysis.** Acceptable: not the goal. The user observes new signals going forward.
- **Stats accuracy is self-reported.** Users can lie with 👍/👎. Acceptable: this is for the user themselves, not for evaluation.

## Out of scope / Future

- Hot ranking tab (likes + comments × 2 + recency) — separate spec.
- Backfilling LLM analysis on historical rows — bulk analyzer task.
- Auto-execute on `is_trade_signal=1 && confidence>threshold` — would require risk config + trading_engine changes.
- Multi-LLM consensus (run two models, compare) — only after we've measured single-model accuracy.

## Open Questions

None — resolved in this conversation:
- Scraper: API interception via `launch_persistent_context` (handles Windows subprocess issue)
- LLM: per-post auto, no manual trigger
- Decision visibility: action badge + reasoning block + 👍/👎
- Execution: user-driven, no auto
