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
save_to_db → INSERT OR IGNORE INTO posts
    │
    ▼  (returns inserted post_ids)
for each new post_id:
    asyncio.create_task(_analyze_one(post_id))
        │
        ▼
    _analyze_one(post_id):
        1. extract tokens (prefer post.tradingPairs, regex fallback)
        2. asyncio.gather token contexts: market_cap + RSI + MACD per token
        3. SignalAnalyzer.analyze(content, token_contexts)
           prompt: "Post + per-token basic analysis → is_opportunity + action + reasoning"
        4. for each opportunity in result.opportunities:
              INSERT INTO opportunities (post_id, token, action, confidence, is_opportunity, reasoning, ...)
              INSERT INTO token_metric_snapshots (post_id, opportunity_id, RSI, MACD, market_cap, ...)
        5. UPDATE posts SET analyzed_at = now
        6. ws broadcast "post:analyzed" with post_id + opportunities + token metrics
```

**Verification surface in TradingView** (see UI section): user sees the post, the per-token basic analysis that was fed to LLM, the LLM's opportunity decision + reasoning, and can 👍/👎 the decision.

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

### 2. LLM auto-pipeline — two-stage: post-token + token-fundamentals

Per the user direction, the LLM does NOT receive a raw post in isolation. It receives **post + the mentioned token's basic analysis** (market cap, MACD, RSI, 24h volume) and decides if the combination is an Opportunity. This matches the existing `ShortSellingEngine` pattern: gather dimensions → LLM synthesizes.

**Pipeline (per new post):**

```
posts row inserted (with tradingPairs from API interception)
    ↓
asyncio.create_task(_analyze_one(post_id))
    │
    ▼
1. extract tokens from post (Binance tradingPairs field, or regex fallback)
    │
    ▼
2. for each token, in parallel:
    - get_coin_details(symbol)  → market_cap, market_cap_rank, price_change_24h
    - get_klines(symbol)        → close[]
    - calculate_rsi(close)      → rsi_14
    - calculate_macd(close)     → macd_line, signal_line, histogram
    │
    ▼
3. SignalAnalyzer.analyze(post_content, token_contexts)
    prompt: "Post + per-token snapshot (market_cap, RSI, MACD, 24h vol) → Opportunity"
    │
    ▼
4. persist: insert into `opportunities` (1 per token); snapshot into `token_metric_snapshots`
    │
    ▼
5. ws broadcast "post:analyzed" with post_id + opportunities + token metrics
```

**`SignalAnalyzer.analyze(content, token_contexts)`** — signature extended:

```python
SYSTEM = """You are a senior crypto trading analyst. You know every major token
and can read basic technicals. You distinguish real signal from hype, sarcasm,
paid shill, or airdrop spam. When a post mentions a token, the technical and
market context for that token is provided alongside — use it to judge whether
the post's claim lines up with the actual market state."""

PROMPT = """A Binance Square post mentioned these tokens. For each token we have
basic market context. Decide, per token, whether the post+context combination
is a real trade opportunity.

POST:
\"\"\"
{content}
\"\"\"

TOKEN CONTEXT (per token, fetched in parallel):
{token_contexts_json}  # e.g.
                       # [
                       #   {"symbol": "SOL", "market_cap_usd": 65e9, "market_cap_rank": 5,
                       #    "rsi_14": 32.4, "macd_state": "bullish_cross", "macd_hist": 0.12,
                       #    "price_change_24h_pct": 4.2, "volume_24h_usd": 3.2e9},
                       #   ...
                       # ]

Return JSON only, no prose:
{{
  "opportunities": [
    {{
      "token": "SOL",
      "sentiment": "bullish",
      "is_opportunity": true,            // post+context lines up to a trade
      "action": "long",                  // 'long'|'short'|null
      "confidence": 0.82,                // 0-1
      "reasoning": "Post names a specific technical breakout. RSI 32 (oversold), MACD just crossed up. Top-5 market cap = liquid. Not hype."
    }}
  ]
}}
"""
```

**Failure modes:**
- Token data fetch fails (timeout / 404): `token_contexts_json` shows `"error": "no data"` for that token; LLM still analyzes based on post + its own knowledge
- LLM provider not configured: `analyze()` returns `{"opportunities": []}`; the post is marked "not analyzed" in UI
- LLM call exception: opportunity row not inserted; post stays at `is_opportunity=0`; user can manually re-analyze

**Persistence per post:**

```sql
-- One row per (post, token) — multi-token posts get multiple opportunity rows
INSERT INTO opportunities
    (post_id, token, sentiment, action, confidence, reasoning,
     is_opportunity, llm_model, created_at)
VALUES (...);

-- Technical snapshot is persisted separately so the user can later
-- verify "LLM said long SOL, but RSI was 75 at the time"
INSERT INTO token_metric_snapshots
    (post_id, symbol, market_cap_usd, market_cap_rank, rsi_14,
     macd_state, macd_hist, price_change_24h_pct, volume_24h_usd, fetched_at)
VALUES (...);
```

**Decision flow inside `SignalScanScheduler._tick`:**

```python
async def _analyze_one(self, post_id: int) -> None:
    try:
        post = _load_post(post_id)
        tokens = _extract_tokens(post)   # prefer tradingPairs JSON, regex fallback
        token_contexts = await asyncio.gather(
            *(self._fetch_token_context(t) for t in tokens),
            return_exceptions=True,
        )
        result = await SignalAnalyzer().analyze(post["content"], token_contexts)
        for opp in result["opportunities"]:
            opp_id = _persist_opportunity(post_id, opp)
            _persist_token_snapshot(post_id, opp["token"], token_contexts)
        if self._ws_broadcast:
            await self._ws_broadcast("post:analyzed", {
                "post_id": post_id, "opportunities": result["opportunities"],
            })
    except Exception as e:
        logger.warning(f"analyze post {post_id} failed: {e}")
```

`_parse_response` handles the new `{"opportunities": [...]}` shape (handles ```json``` blocks, thinking text). When LLM is not configured, returns `{"opportunities": []}`.

### Token context fetcher

Lives in `backend/services/signal_analyzer.py` (or a new `services/token_context.py` if it grows). One method per data source:

```python
async def _fetch_token_context(self, symbol: str) -> dict:
    """Fetch market_cap + RSI + MACD for one symbol. Returns dict or {'error': ...}."""
    ctx = {"symbol": symbol}
    try:
        details = await get_coin_details(symbol.lower())
        ctx["market_cap_usd"] = details.get("market_cap")
        ctx["market_cap_rank"] = details.get("market_cap_rank")
        ctx["price_change_24h_pct"] = details.get("price_change_24h")
    except Exception as e:
        ctx["error_market"] = str(e)
    try:
        klines = await get_klines(symbol, interval="1h", limit=100)
        closes = [k["close"] for k in klines]
        ctx["rsi_14"] = calculate_rsi(closes, period=14)
        macd = calculate_macd(closes)   # returns (line, signal, hist, state)
        ctx["macd_state"] = macd["state"]    # "bullish_cross" | "bearish_cross" | "above_zero" | ...
        ctx["macd_hist"] = macd["hist"]
    except Exception as e:
        ctx["error_tech"] = str(e)
    return ctx
```

Reuses existing `services/datasources/coingecko.py:get_coin_details` and `services/datasources/technical.py:get_klines / calculate_rsi / calculate_macd` — no new dependencies.

### 3. Schema extensions

`signals` is **renamed** to `posts` (raw source material). New tables `opportunities` and `token_metric_snapshots` capture the LLM-derived and per-token-snapshot data. All changes are migration-safe — see "Schema migration" below.

In `services/database.py` `init_db()`:

```sql
-- Rename signals → posts (idempotent: check first)
ALTER TABLE signals RENAME TO posts;

-- posts: raw Binance Square post. Add columns for API interception output.
ALTER TABLE posts ADD COLUMN shares INTEGER DEFAULT 0;        -- from pgc/feed
ALTER TABLE posts ADD COLUMN posted_at TEXT;                 -- real post time, ISO
ALTER TABLE posts ADD COLUMN trading_pairs TEXT;             -- JSON list of {symbol, ...}
ALTER TABLE posts ADD COLUMN analyzed_at TIMESTAMP;          -- LLM finished (or NULL)

-- opportunities: 1:N from posts. One row per (post, token).
CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    token TEXT NOT NULL,
    sentiment TEXT,                  -- 'bullish' | 'bearish' | 'neutral'
    action TEXT,                     -- 'long' | 'short' | null
    confidence REAL,
    is_opportunity INTEGER DEFAULT 0,  -- 0|1
    reasoning TEXT,
    llm_model TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id)
);
CREATE INDEX IF NOT EXISTS idx_opportunities_post ON opportunities(post_id);
CREATE INDEX IF NOT EXISTS idx_opportunities_token ON opportunities(token);

-- token_metric_snapshots: technical/fundamental context fed to LLM, persisted for verification
CREATE TABLE IF NOT EXISTS token_metric_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    opportunity_id INTEGER,            -- NULL if fetch failed before opp was persisted
    symbol TEXT NOT NULL,
    market_cap_usd REAL,
    market_cap_rank INTEGER,
    price_change_24h_pct REAL,
    volume_24h_usd REAL,
    rsi_14 REAL,
    macd_state TEXT,                  -- 'bullish_cross' | 'bearish_cross' | 'above_zero' | ...
    macd_hist REAL,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id),
    FOREIGN KEY (opportunity_id) REFERENCES opportunities(id)
);
CREATE INDEX IF NOT EXISTS idx_token_snapshots_post ON token_metric_snapshots(post_id);

-- post_feedback: user 👍/👎 on the LLM's opportunity decision
CREATE TABLE IF NOT EXISTS post_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    feedback TEXT NOT NULL,             -- 'good' | 'bad'
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id)
);
CREATE INDEX IF NOT EXISTS idx_post_feedback_post ON post_feedback(post_id);
```

### Schema migration (backwards-compat)

The existing `signals` table has 113 rows. To avoid breaking the running app:

1. **Create new tables** (`opportunities`, `token_metric_snapshots`, `post_feedback`) first.
2. **Rename** `signals` → `posts` via `ALTER TABLE signals RENAME TO posts`.
3. **Update FK references** in legacy tables that point to `signals` (e.g. `trades.signal_id`, `signal_validation`):
   - SQLite doesn't auto-update FK references on rename. Use `PRAGMA foreign_keys = OFF; ...; PRAGMA foreign_keys = ON` and re-create the FK tables, or leave FKs as soft references (current code reads by `signal_id` column without enforcing FK at insert time).
4. **Backfill column renames in queries** — `signal_id` becomes `post_id` in new code; old code paths can use a SQL view `CREATE VIEW signals AS SELECT * FROM posts` for the duration of the transition. View lets `api/trading.py` and the scheduler keep reading from `signals` until they're updated.

This is a one-shot migration. The view is dropped once the call sites are updated.

All migrations idempotent via `PRAGMA table_info` / `PRAGMA table_list` checks.

### 4. API additions

Endpoints renamed/extended for the Post/Opportunity split. Old `/api/trading/signals/*` paths keep working via the `signals` SQL view during the migration window.

| Method | Path | Change |
|---|---|---|
| GET | `/api/posts` | **new** — list recent posts. Response: `{posts: [{id, source, author, content, likes, comments, shares, posted_at, trading_pairs, analyzed_at, opportunities: [{token, action, confidence, is_opportunity, reasoning}], token_metrics: [{symbol, rsi_14, macd_state, market_cap_usd, ...}]}]}` |
| GET | `/api/posts/{id}` | **new** — single post with full opportunity details + token snapshots + feedback |
| POST | `/api/posts/{id}/reanalyze` | **new** — manual re-run of LLM (preserves old `opportunities` rows, inserts new ones) |
| POST | `/api/posts/{id}/skip` | **new** — sets `is_opportunity=0` on all opportunities of this post (user override) |
| POST | `/api/posts/{id}/feedback` | **new** — body `{feedback: "good"|"bad", comment?: str}` → INSERT into `post_feedback` |
| GET | `/api/posts/stats` | **new** — `{total_posts, total_opportunities, is_opportunity_count, feedback: {good, bad, accuracy_pct}, last_24h: {...}}` |
| GET | `/api/trading/signals` | **kept** — view-backed; reads from `posts` via SQL view. Same shape as `/api/posts` for backwards compat. |
| POST | `/api/trading/signals/{id}/validate` | **kept** — now calls `_analyze_one` internally (replaces the inline LLM call) |

### 5. TradingView — Decision Visibility is the centerpiece

The user said: "我说的怎么验证" (how do I verify). UI must make the LLM's reasoning chain, the token-level data that backed it, and the user's feedback loop unmissable.

**Per-post card layout** (replaces the current compact `signal-analysis` block):

```
┌──────────────────────────────────────────────────────────────────┐
│ binance_square · 5m ago                                    [analyzed] │
│                                                                  │
│ 📈 LONG  SOL                                  confidence 82% ▓▓▓▓░ │
│                                                                  │
│ ── Post ──────────────────────────────────────────────────────── │
│ "$SOL is about to break out of the descending wedge.              │
│  Funding just flipped negative and the team shipped a major       │
│  update yesterday. Real momentum here."                           │
│                                                                  │
│ ── Token snapshot (what LLM saw) ──────────────────────────────── │
│ SOL · market_cap $65.2B (#5) · RSI(14) 32.4                       │
│       · MACD bullish_cross (hist +0.12) · 24h vol $3.2B          │
│                                                                  │
│ ── LLM reasoning ─────────────────────────────────────────────── │
│ "Post names a specific technical breakout. RSI 32 (oversold),     │
│  MACD just crossed up. Top-5 market cap = liquid. Not hype."      │
│                                                                  │
│ 👤 AuthorKOL · 18 ❤️ · 4 💬 · 2 ↗                                 │
│                                                                  │
│ [👍 Good call]  [👎 Bad call]  [Skip]  [📈 Execute Long]          │
└──────────────────────────────────────────────────────────────────┘
```

For a post that mentions multiple tokens (e.g. $SOL and $ETH), the card shows **one opportunity badge per token**, each with its own token snapshot + reasoning. The user can 👍/👎 the post as a whole (covers all opportunities on that post).

Rules:
- **Action badge is the largest element on the card.** `📈 LONG` (green) / `📉 SHORT` (red) / `⚪ NO OPPORTUNITY` (gray). One badge per token.
- **Token snapshot block** is rendered above the LLM reasoning — this is the data the LLM saw, so the user can verify "the LLM said long when RSI was 75" or similar reasoning traps.
- **Reasoning block is a quoted block, visually distinct** from the post content. LLM's reasoning is the user's primary verification surface.
- **Confidence as a horizontal bar** (not a number alone).
- **Execute button is only enabled when at least one opportunity has `is_opportunity=1`.** Click → opens a tiny dropdown to pick which token to execute (if multiple).
- **👍/👎 buttons always enabled.** Click → POST to `/api/posts/{id}/feedback`. Selected state is sticky.
- **Skip** sets `is_opportunity=0` on all opportunities of the post via `/api/posts/{id}/skip`. Distinct from "Bad call" — skip is a UI-level hide, bad is a quality rating.

**Stats strip above the feed:**

```
┌────────────────────────────────────────────────────┐
│ 24h: 12 posts · 14 opportunities · 9 actionable   │
│ 👍 7 / 👎 2  ·  accuracy 78%                       │
└────────────────────────────────────────────────────┘
```

Reload every 30s. Read from `/api/posts/stats`.

### 6. TradingView changes — exact Vue deltas

In `frontend/src/views/TradingView.vue`:

- Replace the `signal-analysis` div with a new `signal-decision` div (per-token opportunity badge + token snapshot + reasoning block).
- Add `feedbackButtons` block below the reasoning (post-level 👍/👎, sticky selection).
- Wire `sendFeedback(postId, 'good'|'bad')` and `skipPost(postId)` to the new endpoints.
- Add a `stats` ref fed by `/api/posts/stats`; re-render every 30s.
- Pass the new fields through the existing `Post` interface in `frontend/src/types/index.ts` (renamed from `Signal`).

### 7. Tests

- `test_binance_square_browser.py`: extend with API-interception mock. Inject a `page` whose `page.on("response", cb)` triggers a stubbed `/pgc/feed` response from a fixture; assert `_scan_for_posts` picks the right objects.
- `test_signal_scraper.py`: assert `save_to_db` returns new ids; assert new columns (`shares`, `posted_at`, `trading_pairs`) get populated.
- `test_signal_analyzer.py`: 
  - mock `get_coin_details` and `get_klines` to return canned market data
  - mock `llm.ainvoke` to return canned opportunity list
  - assert the prompt contains both the post content and the token context (RSI, MACD, market_cap)
  - assert `analyze()` correctly persists one `opportunities` row per (post, token) and one `token_metric_snapshots` row per fetch
  - assert failure modes: missing market data → partial context, LLM error → empty opportunities list, post stays `analyzed_at=NULL`
- `test_scheduler.py`: assert `_tick` spawns `_analyze_one` tasks for each new post id; assert a failing LLM does not break the next tick; assert `_analyze_one` does not block the tick (fire-and-forget).
- `test_posts_api.py`: 
  - GET `/api/posts` returns posts with nested `opportunities` and `token_metrics`
  - POST `/api/posts/{id}/skip` sets `is_opportunity=0` on all opportunities of the post
  - POST `/api/posts/{id}/feedback` inserts into `post_feedback`
  - GET `/api/posts/stats` aggregates correctly
  - GET `/api/trading/signals` still works via SQL view (backwards compat)
- `test_post_feedback.py` (new): feedback table CRUD; uniqueness rules (one feedback per user per post — or unlimited? — see open question).
- Headless e2e: `tests/test_posts_pipeline_headless.py` — fake scraper + fake analyzer + real DB + real API; assert end-to-end flow from `_tick` → posts row → opportunities rows → API response.

## Configuration

In `config_store.DEFAULT_CONFIG`:

```python
"binance_user_data_dir": "data/playwright_user_data",   # NEW
"binance_cookies": "",                                   # NEW: optional, written by login_binance.py
"signal_auto_analyze": True,                             # NEW: kill switch for the auto-LLM step (per-post)
"analyze_token_data": True,                              # NEW: kill switch for the token-context fetch step
"kline_interval": "1h",                                  # NEW: kline interval for RSI/MACD (1h recommended)
"kline_limit": 100,                                      # NEW: number of klines to fetch
```

If `binance_cookies` is empty, scraper proceeds without login (public feed). The login is a one-time setup, not a per-tick requirement.

## Risks

- **Binance changes `/pgc/feed` shape.** Mitigated: `_looks_like_post` heuristic only needs `content` + `author` + `engagement` keys. If those three stay, we survive any field rename.
- **LLM latency under burst.** 20 posts / tick × (~0.5s token data fetch + ~3s LLM call) ≈ 70s of background work per tick. Fire-and-forget tasks are fine; the next tick won't queue on them. If LLM provider rate-limits, analyze tasks fail individually; the post stays `analyzed_at=NULL` and the user can manually trigger `/api/posts/{id}/reanalyze`.
- **Token data fetch failures.** CoinGecko or Binance klines can be slow or 429. Mitigated: per-token try/except in `_fetch_token_context`; failed fields marked as `null` with `error_*` key; LLM still reasons with the partial context and its own knowledge.
- **LLM cost.** 20 posts / tick × ~600 token prompt (post + token context) + ~150 token output ≈ 15K tokens per tick. At Sonnet pricing ≈ $0.045/tick = $2.16/day if running 24/7. Acceptable for an observation tool; configurable model via existing `llm_factory`.
- **Login state corruption.** `user_data_dir` could expire (Binance rotates session cookies). Mitigated: `is_connected` check + retry-with-cookie path; if persistent context fails, fall back to public feed (no login) — same as today's behavior.
- **Existing 113 mock/historical posts have no LLM analysis.** Acceptable: not the goal. The user observes new posts going forward. (Backfill is in "Out of scope / Future".)
- **Stats accuracy is self-reported.** Users can lie with 👍/👎. Acceptable: this is for the user themselves, not for evaluation.
- **Schema migration is one-way.** The `signals` → `posts` rename plus view-based backwards compat is correct but a future maintainer reading "SELECT * FROM signals" will be confused. Mitigated: the view comment in the migration, and a top-of-file comment in `api/trading.py` pointing to `api/posts.py`.

## Out of scope / Future

- Hot ranking tab (likes + comments × 2 + recency) — separate spec.
- Backfilling LLM analysis on historical posts — bulk analyzer task.
- Auto-execute on `is_opportunity=1 && confidence>threshold` — would require risk config + trading_engine changes. The user's stated goal is observation first; auto-execution comes after reliability is proven via the feedback loop.
- Multi-LLM consensus (run two models, compare) — only after we've measured single-model accuracy.
- On-chain dimension for token context (whale flows via arkham, exchange netflow) — currently the prompt tells LLM about market cap, RSI, MACD; on-chain could be added later as another context field.

## Open Questions

None — resolved in this conversation:
- Scraper: API interception via `launch_persistent_context` (handles Windows subprocess issue)
- LLM: per-post auto, with token context (market_cap + RSI + MACD) pre-fetched and fed alongside the post
- Decision visibility: per-token opportunity badge + token snapshot + reasoning block + 👍/👎
- Execution: user-driven, no auto
- Schema: rename `signals` → `posts`, new `opportunities` (1:N) and `token_metric_snapshots` tables; back-compat via SQL view
