# Binance Square Real Scraper — Design Spec

**Date:** 2026-06-05
**Status:** Approved (pending user review of this doc)
**Scope:** Replace mock data in `BinanceSquareScraper._fetch_posts` with a real Playwright-driven scraper of `binance.com/en/square` (public, no login)

## Problem

`backend/services/signal_scraper.py:49-82` (`_fetch_posts`) returns three hardcoded posts. The `SignalScanScheduler` runs every `signal_scan_interval_minutes` (default 30 min after this change), inserts these into the `signals` table, and the `TradingView` shows them. The author wrote a TODO comment about it ("Real implementation requires browser automation"). Positions endpoint is empty because no Binance trading API key is configured — that's a separate problem and out of scope.

The trading demo can't be evaluated against real flow until the signal source is real.

## Goals

- `SignalScanScheduler` ticks produce real Binance Square posts instead of three hardcoded ones
- Stable enough to survive Binance Square's minor DOM changes; clear failure modes when DOM shifts
- No login / no API keys / no proxy required for first cut
- Scheduler error path (already in place) still swallows failures so the loop never dies
- DB doesn't accumulate duplicates when the same post is scraped twice

## Non-Goals

- Positions / order execution (needs Binance trading API keys; not this change)
- Login-gated content (personalized feed, DMs, replies-only)
- Historical scrape (time-window backfill) — only current feed
- Auto-solving captchas / advanced anti-bot evasion
- Multi-language filtering

## Architecture

**Replace the stub inside `BinanceSquareScraper._fetch_posts`** rather than introducing a parallel scraper class. The scheduler already drives `scrape()` → `save_to_db()`; keeping that contract means zero changes to `SignalScanScheduler` and the WS broadcast layer.

```
SignalScanScheduler._tick (every 30 min)
    │
    ▼
BinanceSquareScraper.scrape(limit=30)   ← unchanged
    │
    ▼
_fetch_posts(30)                       ← replace internals
    │
    ▼
BinanceSquareBrowser.fetch_posts(30)   ← new module
    │       │  module-level singleton chromium
    │       │  injects page for tests
    │       └─ goto + scroll + collect N cards → return list[dict]
    │
    ▼
filter (len(tokens) > 0)
    │
    ▼
save_to_db → INSERT OR IGNORE   ← new dedup path
    │
    ▼
ws broadcast "signal:new" (existing)
```

### Module layout

| File | Status | Responsibility |
|------|--------|----------------|
| `backend/services/binance_square_browser.py` | **new** | Long-lived Playwright browser, `fetch_posts(limit)` API, custom exception types |
| `backend/services/signal_scraper.py` | edit | Replace `_fetch_posts` body; add dedup + `source_type` to `save_to_db` |
| `backend/services/database.py` | edit | Migration: UNIQUE index on `signals.source_url` (partial, where != ''); add `source_type` column; default `signal_scan_interval_minutes = 30` |
| `backend/services/config_store.py` | edit | Default `signal_scan_interval_minutes` flips 15 → 30 (helper already exists); add `get_binance_square_scrape_config()` + `set_binance_square_scrape_config()` |
| `backend/tests/fixtures/binance_square/*.html` | new | Saved real pages for offline tests |
| `backend/tests/test_binance_square_browser.py` | new | Fixture-based unit tests (no network) |
| `backend/tests/manual/test_binance_square_live.py` | new | Manual-only live smoke (skipped in CI) |

### Why module-level singleton browser

Scheduler cadence is 30 min. Re-launching chromium per tick wastes 5-8s of cold start. Singleton with lazy-init + reconnect-on-failure is the simplest path. Not a separate service because there's no second consumer and no need for IPC.

## Components

### `BinanceSquareBrowser`

```python
class BinanceSquareBrowser:
    def __init__(self, page: Page | None = None):
        # Inject page fixture for tests; None → lazy launch real chromium
        self._injected_page = page
        self._browser: Browser | None = None
        self._last_fetch_at: float | None = None

    async def fetch_posts(self, limit: int) -> list[dict]: ...
    async def aclose(self) -> None: ...
    def _parse_html(self, html: str, limit: int) -> list[dict]: ...
```

Behaviour:
- First `fetch_posts` call: launch chromium (headless), `page.goto(SQUARE_URL)`, wait for first card render
- Subsequent calls: reuse the page; if `browser.is_connected() == False` or `last_fetch_at` is > 20 min ago, re-`goto` and continue
- `atexit` registers a sync wrapper that calls `aclose()` (handles `asyncio.run` if no loop)
- Selectors concentrated in module-level `SELECTORS` dict so DOM-breakages are localized

### Custom exceptions

```python
class BrowserError(Exception): pass
class LoginWallError(BrowserError): pass       # page redirected to login
class CaptchaError(BrowserError): pass         # "verify you are human" detected
class RateLimitError(BrowserError): pass       # HTTP 429
class ParseError(BrowserError):
    def __init__(self, msg, screenshot_path=None): ...
```

### `_fetch_posts` integration

```python
async def _fetch_posts(self, limit: int) -> list[dict]:
    browser = _get_browser()  # module singleton
    try:
        raw = await browser.fetch_posts(limit)
    except (LoginWallError, CaptchaError, RateLimitError) as e:
        logger.warning(f"[BinanceSquareScraper] {type(e).__name__}: {e}")
        return []
    except ParseError as e:
        logger.error(f"[BinanceSquareScraper] parse failed: {e} (screenshot: {e.screenshot_path})")
        return []
    return [_to_schema(p) for p in raw]
```

### Dedup

- Migration in `init_db()`:
  ```sql
  CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_source_url
      ON signals(source_url) WHERE source_url != '';
  ALTER TABLE signals ADD COLUMN source_type TEXT DEFAULT 'live';
  UPDATE signals SET source_type = 'mock' WHERE author IN ('TraderOne', 'CryptoWhale', 'BearHunter');
  ```
- `save_to_db` switches to `INSERT OR IGNORE INTO signals (...)`
- Returns the number of inserted rows; log it for observability

### Schema change

Add column:
- `signals.source_type TEXT DEFAULT 'live'` — `'live'` for new posts, `'mock'` for the historical hardcoded ones (backfilled in the same migration)

No removal of any existing column. Frontend can later badge by `source_type` if desired; out of scope for this change.

## Configuration

`config_store.py` adds:

```python
DEFAULT_BINANCE_SQUARE_CONFIG = {
    "url": "https://www.binance.com/en/square",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "max_posts_per_scrape": 30,
    "headless": True,
    "scroll_passes": 2,
    "scroll_pause_ms": 2500,
}

def get_binance_square_scrape_config() -> dict: ...
def set_binance_square_scrape_config(patch: dict) -> None: ...
```

`trading_config.signal_scan_interval_minutes` default flips from 15 → 30 (existing rows not touched).

`SignalScanScheduler._interval_seconds()` and `_interval_minutes()` continue to read live from the config row — no scheduler change.

## Anti-bot baseline

- Realistic Chrome user-agent string
- Viewport 1920x1080
- `navigator.webdriver` masked via `add_init_script`
- 3s+ pause between scrolls
- No proxy for v1; if 429s/Captchas start showing in logs, layer proxy via existing `proxy_url` config

## Testing

### Unit tests (`test_binance_square_browser.py`, no network)

- Parse fixture `home_with_posts.html` → assert exact list of post dicts
- Parse fixture `empty_page.html` → assert `[]`
- Parse fixture `login_wall.html` → assert `LoginWallError` raised
- Parse fixture `captcha_page.html` → assert `CaptchaError` raised
- `_fetch_posts` swallows `LoginWallError` / `CaptchaError` / `RateLimitError` / `ParseError` and returns `[]`
- `_fetch_posts` lets other exceptions propagate (scheduler will catch)
- `save_to_db` is idempotent: insert same fixture posts twice → DB row count = 1

### Manual live test (`tests/manual/test_binance_square_live.py`, skipped in CI)

- Launch real chromium, fetch 30 posts, print them
- On error: `page.screenshot()` to `tests/output/`
- Marked `@pytest.mark.skip(reason="manual live smoke")` so it never runs in CI

### Acceptance checklist

- [ ] `pytest tests/test_binance_square_browser.py -v` — all pass
- [ ] `pytest tests/test_signal_scraper.py -v` (existing) — no regression
- [ ] `pytest tests/test_scheduler.py -v` — no regression
- [ ] Manual live test prints ≥10 token-mentioning posts
- [ ] Live tick inserts ≥1 `source_type='live'` row into `signals`
- [ ] Re-running tick 3× consecutively → no row-count explosion (dedup works)
- [ ] Replace fixture with `login_wall.html` and call `_fetch_posts` → returns `[]`, warning logged, no exception propagates
- [ ] `signal_scan_interval_minutes` defaults to 30 in fresh DB; scheduler reads it live (changing via `PUT /api/workflow/config` with `task_id=1` still works)
- [ ] `/trading` frontend shows real author names (not TraderOne / CryptoWhale / BearHunter) once a real tick has fired

## Risks

- **Binance Square DOM changes** — primary risk. Mitigated by: (1) selectors concentrated in one dict, (2) `ParseError` carries a screenshot path for fast diagnosis, (3) failure path returns `[]` so loop survives.
- **Anti-bot escalation** — public feed is currently permissive; if rate-limited, add proxy or increase `scroll_pause_ms` via config. Out of scope to auto-solve.
- **Browser leak on crash** — `atexit` only covers clean shutdown. Long-running uvicorn that crashes ungracefully may leak a chromium process. Acceptable for v1; if observed, switch to `try/finally` in scheduler `stop()`.

## Open Questions

None. User confirmed: (1) no login needed for scraping, (2) Playwright + CSS selectors, (3) 30-min cadence.
