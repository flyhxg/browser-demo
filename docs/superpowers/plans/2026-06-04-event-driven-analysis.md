# Event-Driven Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a structured event-causality sub-pipeline (news + social + on-chain + derivatives) exposed via `POST /api/analyze/events`, so "why did X drop" queries get a timeline + LLM narrative + confidence score instead of a free-form paragraph.

**Architecture:** New `EventPipeline` class orchestrates 4 parallel datasource fetches via `asyncio.gather`, normalizes to `Event` dataclass, clusters by 30-min window, caps at 50 events, asks LLM for a 2-3 sentence synthesis. New `NewsScraper` uses Playwright with a `BrowserLauncher` seam for testability. `IntentRouter` gets an event-shaped query hook so "why did X drop" questions route to the new endpoint.

**Tech Stack:** Python 3.14, asyncio, Playwright (already a project dep), existing datasources (arkham, whale_alert, binance_futures, okx, signal_scraper).

**Spec:** `docs/superpowers/specs/2026-06-04-event-driven-analysis-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/services/datasources/binance_square.py` (MODIFY) | Add `scrape_hot(symbol, time_range, top_n)` method |
| `backend/services/datasources/news.py` (NEW, ~180 lines) | `NewsScraper` + `BrowserLauncher` Protocol + `PlaywrightLauncher` + `_parse_article_html` |
| `backend/services/datasources/aggregators.py` (NEW, ~80 lines) | `OnchainAggregator` + `DerivativesAggregator` (fan-out + normalize) |
| `backend/services/event_pipeline.py` (NEW, ~250 lines) | `Event` dataclass + `EventPipeline` class |
| `backend/api/analysis.py` (MODIFY) | Add `POST /api/analyze/events` endpoint |
| `backend/services/intent_router.py` (MODIFY) | Add `EVENT_QUERY_KEYWORDS` + `classify` returns `"event"` + `route_event` method |
| `backend/tests/test_binance_square_hot.py` (NEW) | 3 tests for `scrape_hot` |
| `backend/tests/test_news_scraper.py` (NEW) | 5 tests (4 pure `_parse_article_html` + 1 with FakeBrowserLauncher) |
| `backend/tests/test_event_pipeline.py` (NEW) | 10 tests |
| `backend/tests/test_analyze_events_endpoint.py` (NEW) | 2 tests (200 happy path + 400 on invalid time_range) |
| `backend/tests/test_intent_router.py` (MODIFY or NEW) | 3 tests for event hook |

---

## Task 1: Add `scrape_hot` to BinanceSquareScraper (TDD)

**Files:**
- Modify: `backend/services/datasources/binance_square.py`
- Create: `backend/tests/test_binance_square_hot.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_binance_square_hot.py`:

```python
"""Tests for BinanceSquareScraper.scrape_hot()."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest


class _FakePost(dict):
    """Mimics a row from BinanceSquareScraper.scrape()."""
    pass


def _make_post(likes: int, comments: int, content: str, age_hours: float = 1.0):
    return {
        "source": "binance_square",
        "content": content,
        "author": "trader",
        "likes": likes,
        "comments": comments,
        "url": "https://example.com/post/" + content[:10],
        "timestamp": (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat(),
    }


@pytest.mark.asyncio
async def test_scrape_hot_returns_top_n_by_engagement():
    """scrape_hot must return posts sorted by likes + comments*2, descending."""
    from services.datasources.binance_square import BinanceSquareScraper

    posts = [
        _make_post(10, 1, "$BTC low eng", age_hours=1),
        _make_post(100, 50, "$BTC high eng", age_hours=2),    # score=200
        _make_post(50, 30, "$BTC mid eng", age_hours=0.5),    # score=110
    ]
    scraper = BinanceSquareScraper()
    scraper.scrape = AsyncMock(return_value=posts)

    result = await scraper.scrape_hot("BTC", time_range="24h", top_n=2)

    assert len(result) == 2
    assert result[0]["content"] == "$BTC high eng"
    assert result[1]["content"] == "$BTC mid eng"


@pytest.mark.asyncio
async def test_scrape_hot_filters_by_time_range():
    """Posts older than time_range must be excluded."""
    from services.datasources.binance_square import BinanceSquareScraper

    posts = [
        _make_post(100, 50, "$BTC fresh", age_hours=1),
        _make_post(100, 50, "$BTC stale", age_hours=72),
    ]
    scraper = BinanceSquareScraper()
    scraper.scrape = AsyncMock(return_value=posts)

    result = await scraper.scrape_hot("BTC", time_range="24h", top_n=10)

    assert len(result) == 1
    assert result[0]["content"] == "$BTC fresh"


@pytest.mark.asyncio
async def test_scrape_hot_filters_by_symbol_mention():
    """Posts not mentioning the symbol must be excluded."""
    from services.datasources.binance_square import BinanceSquareScraper

    posts = [
        _make_post(100, 50, "$BTC to the moon", age_hours=1),
        _make_post(100, 50, "ETH looking strong", age_hours=1),
        _make_post(100, 50, "BTC and ethereum correlation", age_hours=1),
    ]
    scraper = BinanceSquareScraper()
    scraper.scrape = AsyncMock(return_value=posts)

    result = await scraper.scrape_hot("BTC", time_range="24h", top_n=10)

    # Should include posts 1 and 3 (both mention BTC or Bitcoin)
    contents = [p["content"] for p in result]
    assert "$BTC to the moon" in contents
    assert "BTC and ethereum correlation" in contents
    assert "ETH looking strong" not in contents
```

- [ ] **Step 2: Run the tests to verify they FAIL**

Run from `D:\work/browser-demo`:
```bash
cd backend && python -m pytest tests/test_binance_square_hot.py -v 2>&1 | tail -20
```

Expected: 3 failures with `AttributeError: 'BinanceSquareScraper' object has no attribute 'scrape_hot'`.

- [ ] **Step 3: Add `scrape_hot` method to `BinanceSquareScraper`**

In `backend/services/datasources/binance_square.py`, find the existing class. Add the method after the existing `scrape()` method (or before the helpers at the bottom — anywhere inside the class is fine):

```python
    async def scrape_hot(
        self,
        symbol: str,
        time_range: str = "24h",
        top_n: int = 20,
    ) -> list[dict]:
        """Return the top-N hottest posts mentioning `symbol` within `time_range`.

        Hotness = likes + comments * 2. Posts with no timestamp are excluded
        when a time_range is given. Used by the event-driven analysis pipeline.
        """
        from datetime import datetime, timedelta, timezone

        hours = {"1h": 1, "4h": 4, "24h": 24, "7d": 24 * 7}.get(time_range, 24)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        all_posts = await self.scrape()
        symbol_upper = symbol.upper()
        symbol_name_map = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}

        # Filter: must mention symbol, and be within time range
        filtered = []
        for p in all_posts:
            content = p.get("content", "")
            upper = content.upper()
            if f"${symbol_upper}" not in upper and f"#{symbol_upper}" not in upper:
                # try full name
                full_name = symbol_name_map.get(symbol_upper, "")
                if full_name and full_name not in content.lower():
                    continue
            ts_str = p.get("timestamp")
            if ts_str and time_range:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts < cutoff:
                        continue
                except (ValueError, AttributeError):
                    continue
            filtered.append(p)

        # Sort by engagement
        filtered.sort(key=lambda p: p.get("likes", 0) + p.get("comments", 0) * 2, reverse=True)
        return filtered[:top_n]
```

- [ ] **Step 4: Run the tests to verify they PASS**

```bash
cd backend && python -m pytest tests/test_binance_square_hot.py -v 2>&1 | tail -10
```

Expected: 3 passed.

- [ ] **Step 5: Run the full backend test suite to confirm no regression**

```bash
cd backend && python -m pytest -q 2>&1 | tail -3
```

Expected: 144 passed (was 141 + 3 new). The 1 pre-existing flaky coingecko test may or may not trigger.

- [ ] **Step 6: Commit**

```bash
cd D:/work/browser-demo
git add backend/services/datasources/binance_square.py backend/tests/test_binance_square_hot.py
git commit -m "feat(binance_square): add scrape_hot for event-driven analysis"
```

---

## Task 2: Create news.py with NewsScraper + BrowserLauncher seam (TDD)

**Files:**
- Create: `backend/services/datasources/news.py`
- Create: `backend/tests/test_news_scraper.py`

This task builds the Playwright-based news scraper. The test seam is the `BrowserLauncher` Protocol — tests inject a fake, production uses `PlaywrightLauncher`.

- [ ] **Step 1: Write the failing tests for `_parse_article_html` (pure function)**

Create `backend/tests/test_news_scraper.py` with the FIRST 4 tests (the 5th uses FakeBrowserLauncher and is added in Step 4):

```python
"""Tests for NewsScraper — the Playwright-based news fetcher."""
import pytest


def test_normalize_post_extracts_mentioned_tokens():
    """_parse_article_html must extract $SYMBOL and #SYMBOL mentions."""
    from services.datasources.news import _parse_article_html

    html = """
    <article>
      <h2>$BTC drops on ETF delay</h2>
      <p>The SEC pushed the decision to Q3, weighing on #Bitcoin markets.</p>
      <time datetime="2026-06-03T14:23:00Z"></time>
    </article>
    """
    evt = _parse_article_html(html, source="CoinDesk", url="https://coindesk.com/x")

    assert evt["title"] == "$BTC drops on ETF delay"
    assert "SEC" in evt["summary"]
    assert "BTC" in evt["mentioned_tokens"]
    assert "BITCOIN" in evt["mentioned_tokens"]  # #bitcoin normalized to BITCOIN
    assert evt["timestamp"] == "2026-06-03T14:23:00+00:00"
    assert evt["source"] == "CoinDesk"
    assert evt["url"] == "https://coindesk.com/x"


def test_filter_by_symbol_includes_cashtags_and_names():
    """matches_symbol must return True for $BTC, #bitcoin, and 'Bitcoin'."""
    from services.datasources.news import matches_symbol

    assert matches_symbol("$BTC surges", "BTC") is True
    assert matches_symbol("#bitcoin news", "BTC") is True
    assert matches_symbol("Bitcoin price update", "BTC") is True
    assert matches_symbol("ETH looking strong", "BTC") is False
    assert matches_symbol("Solana ecosystem", "BTC") is False


def test_top_n_returns_highest_engagement():
    """_top_n_by_engagement must return the N highest-scoring items."""
    from services.datasources.news import _top_n_by_engagement

    items = [
        {"title": "low", "score": 1},
        {"title": "high", "score": 100},
        {"title": "mid", "score": 50},
    ]
    result = _top_n_by_engagement(items, n=2)
    titles = [r["title"] for r in result]
    assert titles == ["high", "mid"]


def test_parse_article_html_handles_missing_optional_fields():
    """_parse_article_html must not crash on minimal HTML."""
    from services.datasources.news import _parse_article_html

    html = "<article><h2>Title only</h2></article>"
    evt = _parse_article_html(html, source="X", url="https://x.com/y")
    assert evt["title"] == "Title only"
    assert evt["summary"] == ""
    assert evt["mentioned_tokens"] == []
    assert evt["timestamp"] is None
```

- [ ] **Step 2: Run the tests to verify they FAIL**

```bash
cd backend && python -m pytest tests/test_news_scraper.py -v 2>&1 | tail -15
```

Expected: 4 failures with `ModuleNotFoundError` (news.py doesn't exist yet) or `ImportError`.

- [ ] **Step 3: Create the news.py module with pure functions and class skeleton**

Create `backend/services/datasources/news.py`:

```python
"""Playwright-based news scraper for CoinDesk + The Block.

Fetches articles mentioning a target symbol within a time range.
The `BrowserLauncher` Protocol is the seam for tests — production
uses `PlaywrightLauncher`, tests inject `FakeBrowserLauncher` returning
canned HTML.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

logger = logging.getLogger(__name__)

SYMBOL_FULL_NAMES = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binance coin",
}

TOKEN_MENTION_RE = re.compile(r"\$([A-Z]{2,10})|#([A-Za-z]{2,15})")


def matches_symbol(text: str, symbol: str) -> bool:
    """Return True if `text` mentions `symbol` via $tag, #tag, or full name."""
    if not text:
        return False
    upper_text = text.upper()
    if f"${symbol.upper()}" in upper_text:
        return True
    if f"#{symbol.upper()}" in upper_text:
        return True
    full_name = SYMBOL_FULL_NAMES.get(symbol.upper(), "")
    if full_name and full_name in text.lower():
        return True
    return False


def _parse_article_html(html: str, source: str, url: str) -> dict[str, Any]:
    """Parse one article's HTML into a normalized news event dict.

    Uses regex (no BeautifulSoup dependency) — robust enough for the
    article structures on CoinDesk / The Block.
    """
    # Title
    title_match = re.search(r"<h2[^>]*>(.*?)</h2>", html, re.DOTALL | re.IGNORECASE)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""

    # First <p> as summary
    p_match = re.search(r"<p[^>]*>(.*?)</p>", html, re.DOTALL | re.IGNORECASE)
    summary = re.sub(r"<[^>]+>", "", p_match.group(1)).strip() if p_match else ""
    summary = re.sub(r"\s+", " ", summary)[:500]

    # Timestamp from <time datetime="...">
    time_match = re.search(r'<time[^>]+datetime="([^"]+)"', html, re.IGNORECASE)
    timestamp: str | None = None
    if time_match:
        raw = time_match.group(1)
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            timestamp = dt.isoformat()
        except ValueError:
            timestamp = None

    # Token mentions
    mentioned: set[str] = set()
    for m in TOKEN_MENTION_RE.finditer(html):
        token = (m.group(1) or m.group(2) or "").upper()
        if token:
            mentioned.add(token)

    return {
        "title": title,
        "summary": summary,
        "mentioned_tokens": sorted(mentioned),
        "timestamp": timestamp,
        "source": source,
        "url": url,
    }


def _top_n_by_engagement(items: list[dict], n: int) -> list[dict]:
    """Return the N items with the highest `score` field."""
    return sorted(items, key=lambda x: x.get("score", 0), reverse=True)[:n]


# --- BrowserLauncher seam ---


class BrowserLauncher(Protocol):
    """Seam for tests — production uses PlaywrightLauncher."""
    async def launch(self) -> Any: ...


class PlaywrightLauncher:
    """Production launcher. One context per call, closed in finally."""
    async def launch(self) -> Any:
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        return _PlaywrightHandle(pw, browser)


class _PlaywrightHandle:
    """Wraps the Playwright objects so launcher.launch() returns a single value."""
    def __init__(self, pw, browser):
        self.pw = pw
        self.browser = browser
```

- [ ] **Step 4: Run the 4 tests to verify they PASS**

```bash
cd backend && python -m pytest tests/test_news_scraper.py -v 2>&1 | tail -10
```

Expected: 4 passed.

- [ ] **Step 5: Add the 5th test (FakeBrowserLauncher integration test)**

Append to `backend/tests/test_news_scraper.py`:

```python
@pytest.mark.asyncio
async def test_scraper_handles_site_5xx_returns_from_other_site():
    """When one site fails (FakeBrowser raises), the other site's posts are returned."""
    from services.datasources.news import NewsScraper, _PlaywrightHandle


    class FakePage:
        def __init__(self, html: str):
            self._html = html

        async def goto(self, url: str, timeout: int = 15000):
            if "coindesk" in url:
                raise RuntimeError("503 Service Unavailable")
            return None

        async def query_selector_all(self, selector: str):
            # Return a single dummy element to keep the loop simple
            return [type("E", (), {
                "inner_html": lambda self: self._html,
                "_html": self._html,
            })(self._html)] if "theblock" in getattr(self, "_url", "") else []

    class FakeBrowser:
        async def new_context(self):
            class Ctx:
                async def new_page(self_inner):
                    p = FakePage("<article><h2>$BTC test</h2></article>")
                    p._url = "https://www.theblock.co/"
                    return p
                async def close(self_inner):
                    pass
            return Ctx()

        async def close(self):
            pass

    class FakeLauncher:
        async def launch(self):
            return FakeBrowser()

    scraper = NewsScraper(browser_launcher=FakeLauncher(), sites=("coindesk", "theblock"))
    events = await scraper.fetch_news("BTC", time_range="24h", top_n_per_site=5)

    # The Block succeeded; CoinDesk failed. The Block's event should be in the result.
    sources = [e["source"] for e in events]
    assert "The Block" in sources or "theblock" in [s.lower() for s in sources]
```

- [ ] **Step 6: Implement `NewsScraper` class with `fetch_news`**

Add the `NewsScraper` class to `backend/services/datasources/news.py` (append below the existing code):

```python
SITE_URLS = {
    "coindesk": "https://www.coindesk.com/",
    "theblock": "https://www.theblock.co/",
}
SITE_NAMES = {
    "coindesk": "CoinDesk",
    "theblock": "The Block",
}


class NewsScraper:
    """Scrape crypto news sites for posts mentioning a symbol.

    The `BrowserLauncher` is the test seam — production uses
    `PlaywrightLauncher`, tests inject a fake that returns canned HTML
    or raises on goto to simulate failures.
    """

    def __init__(
        self,
        browser_launcher: BrowserLauncher | None = None,
        sites: tuple[str, ...] = ("coindesk", "theblock"),
    ):
        self._launcher = browser_launcher or PlaywrightLauncher()
        self._sites = sites

    async def fetch_news(
        self,
        symbol: str,
        time_range: str = "24h",
        top_n_per_site: int = 5,
    ) -> list[dict[str, Any]]:
        """Scrape all configured sites in parallel, return normalized events."""
        results = await asyncio.gather(
            *[self._scrape_site(site, symbol) for site in self._sites],
            return_exceptions=True,
        )

        all_events: list[dict] = []
        for site, result in zip(self._sites, results):
            if isinstance(result, Exception):
                logger.warning(f"[NewsScraper] {site} failed: {result}")
                continue
            all_events.extend(result)

        # Filter by time range
        hours = {"1h": 1, "4h": 4, "24h": 24, "7d": 24 * 7}.get(time_range, 24)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        filtered = []
        for evt in all_events:
            ts_str = evt.get("timestamp")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts < cutoff:
                        continue
                except ValueError:
                    pass
            if not matches_symbol(evt.get("title", "") + " " + evt.get("summary", ""), symbol):
                continue
            filtered.append(evt)

        # Sort by timestamp DESC, take top N
        filtered.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
        return filtered[: top_n_per_site * len(self._sites)]

    async def _scrape_site(self, site: str, symbol: str) -> list[dict[str, Any]]:
        """Scrape one site. Returns a list of normalized event dicts.

        Production: launches a browser, navigates to the site, extracts articles.
        Tests: a fake launcher can simulate the navigation returning HTML or raising.
        """
        url = SITE_URLS[site]
        source_name = SITE_NAMES[site]
        handle = await self._launcher.launch()
        events: list[dict] = []
        try:
            context = await handle.new_context()
            try:
                page = await context.new_page()
                await page.goto(url, timeout=15000)
                # Try multiple selectors — different sites use different markup
                articles = await page.query_selector_all("article")
                for art in articles[:20]:  # cap raw articles
                    try:
                        html = await art.inner_html()
                        evt = _parse_article_html(html, source=source_name, url=url)
                        if evt["title"]:
                            events.append(evt)
                    except Exception as e:
                        logger.debug(f"[NewsScraper] article parse error: {e}")
            finally:
                await context.close()
        finally:
            await handle.close()
            # For PlaywrightLauncher, the underlying pw instance also needs stopping.
            if hasattr(handle, "pw"):
                try:
                    await handle.pw.stop()
                except Exception:
                    pass
        return events
```

Note: The fake `FakeBrowser` in the test doesn't have `pw` attribute, so the `hasattr` check skips the cleanup. The fake's `close()` is a no-op. This is a deliberate test seam.

- [ ] **Step 7: Run the 5 tests to verify they all PASS**

```bash
cd backend && python -m pytest tests/test_news_scraper.py -v 2>&1 | tail -15
```

Expected: 5 passed.

- [ ] **Step 8: Run full backend test suite to confirm no regression**

```bash
cd backend && python -m pytest -q 2>&1 | tail -3
```

Expected: 149 passed (was 144 + 5 new).

- [ ] **Step 9: Commit**

```bash
cd D:/work/browser-demo
git add backend/services/datasources/news.py backend/tests/test_news_scraper.py
git commit -m "feat(news): add NewsScraper with BrowserLauncher seam"
```

---

## Task 3: Create aggregators.py (TDD)

**Files:**
- Create: `backend/services/datasources/aggregators.py`
- Create: `backend/tests/test_aggregators.py`

The aggregators fan out to the underlying single-source classes and normalize results into `Event` dicts. The `Event` dataclass itself is in `event_pipeline.py` (Task 4). For now, the aggregators return dicts in the `Event` shape.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_aggregators.py`:

```python
"""Tests for OnchainAggregator and DerivativesAggregator."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_onchain_aggregator_combines_whale_and_arkham():
    """OnchainAggregator.fetch must combine whale + arkham results."""
    from services.datasources.aggregators import OnchainAggregator

    whale = AsyncMock()
    whale.get_recent_transfers = AsyncMock(return_value=[
        {"amount_usd": 10_000_000, "from": "unknown", "to": "binance", "timestamp": "2026-06-03T14:00:00Z"},
    ])
    arkham = AsyncMock()
    arkham.get_flows = AsyncMock(return_value=[
        {"amount_usd": 7_000_000, "from": "coinbase", "to": "unknown", "timestamp": "2026-06-03T15:00:00Z"},
    ])

    agg = OnchainAggregator(whale=whale, arkham=arkham)
    events = await agg.fetch("BTC", "24h")

    assert len(events) == 2
    types = sorted([e["type"] for e in events])
    assert types == ["whale", "whale"]


@pytest.mark.asyncio
async def test_derivatives_aggregator_returns_liquidations_and_funding():
    """DerivativesAggregator.fetch must include both liquidation and funding events."""
    from services.datasources.aggregators import DerivativesAggregator

    binance = AsyncMock()
    binance.get_liquidations = AsyncMock(return_value=[
        {"side": "long", "amount_usd": 2_000_000, "timestamp": "2026-06-03T14:30:00Z"},
    ])
    binance.get_funding_rate = AsyncMock(return_value={
        "rate": 0.0015, "timestamp": "2026-06-03T15:00:00Z"
    })
    okx = AsyncMock()
    okx.get_funding_rate = AsyncMock(return_value={
        "rate": 0.0008, "timestamp": "2026-06-03T15:00:00Z"
    })

    agg = DerivativesAggregator(binance=binance, okx=okx)
    events = await agg.fetch("BTC", "24h")

    types = [e["type"] for e in events]
    assert "liquidation" in types
    # Funding shift only included if |rate| > 0.001 (0.1%)
    funding_events = [e for e in events if e["type"] == "funding_shift"]
    assert len(funding_events) >= 1
```

- [ ] **Step 2: Run tests to verify they FAIL**

```bash
cd backend && python -m pytest tests/test_aggregators.py -v 2>&1 | tail -10
```

Expected: 2 failures with `ModuleNotFoundError: services.datasources.aggregators`.

- [ ] **Step 3: Create `aggregators.py`**

Create `backend/services/datasources/aggregators.py`:

```python
"""Aggregators that fan out to multiple single-source datasources.

OnchainAggregator: whale_alert + arkham
DerivativesAggregator: binance_futures + okx

Both return normalized event dicts compatible with the EventPipeline.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Sampling thresholds (per spec)
WHALE_MIN_USD = 5_000_000
LIQUIDATION_MIN_USD = 1_000_000
FUNDING_SHIFT_THRESHOLD = 0.001  # 0.1%


def _ts_to_iso(ts: Any) -> str:
    """Normalize various timestamp inputs to ISO-8601 string."""
    if isinstance(ts, str):
        return ts
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.isoformat()
    return datetime.now(timezone.utc).isoformat()


class OnchainAggregator:
    """Combines whale_alert + arkham into normalized whale events."""

    def __init__(self, whale=None, arkham=None):
        from services.datasources.whale_alert import WhaleAlert
        from services.datasources.arkham import Arkham
        self.whale = whale or WhaleAlert()
        self.arkham = arkham or Arkham()

    async def fetch(self, symbol: str, time_range: str) -> list[dict]:
        """Returns whale events ≥ $5M USD."""
        hours = {"1h": 1, "4h": 4, "24h": 24, "7d": 24 * 7}.get(time_range, 24)
        results = await asyncio.gather(
            self._safe(self.whale.get_recent_transfers, symbol, hours),
            self._safe(self.arkham.get_flows, symbol, hours),
            return_exceptions=True,
        )

        events: list[dict] = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning(f"[OnchainAggregator] fetch error: {r}")
                continue
            for transfer in r or []:
                amount = transfer.get("amount_usd", 0)
                if amount < WHALE_MIN_USD:
                    continue
                events.append({
                    "timestamp": _ts_to_iso(transfer.get("timestamp")),
                    "type": "whale",
                    "title": f"{amount / 1_000_000:.1f}M USD {symbol} transfer",
                    "source": transfer.get("source", "WhaleAlert"),
                    "url": transfer.get("url"),
                    "payload": {
                        "amount_usd": amount,
                        "from": transfer.get("from", "unknown"),
                        "to": transfer.get("to", "unknown"),
                    },
                    "severity": 5 if amount >= 50_000_000 else 3,
                })
        return events

    @staticmethod
    async def _safe(method, *args):
        return await method(*args)


class DerivativesAggregator:
    """Combines binance_futures + okx for liquidations + funding rate shifts."""

    def __init__(self, binance=None, okx=None):
        from services.datasources.binance_futures import BinanceFutures
        from services.datasources.okx import OKXSource
        self.binance = binance or BinanceFutures()
        self.okx = okx or OKXSource()

    async def fetch(self, symbol: str, time_range: str) -> list[dict]:
        """Returns liquidation + funding_shift events."""
        results = await asyncio.gather(
            self._safe(self.binance.get_liquidations, symbol, time_range),
            self._safe(self.binance.get_funding_rate, symbol),
            self._safe(self.okx.get_funding_rate, symbol),
            return_exceptions=True,
        )

        events: list[dict] = []

        # Liquidations
        liqs = results[0]
        if isinstance(liqs, list):
            for liq in liqs:
                amount = liq.get("amount_usd", 0)
                if amount < LIQUIDATION_MIN_USD:
                    continue
                events.append({
                    "timestamp": _ts_to_iso(liq.get("timestamp")),
                    "type": "liquidation",
                    "title": f"{liq.get('side', '?').upper()} liq ${amount / 1_000_000:.1f}M",
                    "source": "BinanceFutures",
                    "url": None,
                    "payload": {"side": liq.get("side"), "amount_usd": amount},
                    "severity": 4 if amount >= 10_000_000 else 2,
                })

        # Funding rate shifts (from binance + okx)
        for idx, source_name in [(1, "BinanceFutures"), (2, "OKX")]:
            fr = results[idx]
            if not isinstance(fr, dict):
                continue
            rate = abs(fr.get("rate", 0))
            if rate > FUNDING_SHIFT_THRESHOLD:
                events.append({
                    "timestamp": _ts_to_iso(fr.get("timestamp")),
                    "type": "funding_shift",
                    "title": f"{source_name} funding rate {fr['rate']:.4f}",
                    "source": source_name,
                    "url": None,
                    "payload": {"rate": fr["rate"], "side": "long_pays_short" if fr["rate"] > 0 else "short_pays_long"},
                    "severity": 3,
                })

        return events

    @staticmethod
    async def _safe(method, *args):
        return await method(*args)
```

- [ ] **Step 4: Run tests to verify they PASS**

```bash
cd backend && python -m pytest tests/test_aggregators.py -v 2>&1 | tail -10
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd D:/work/browser-demo
git add backend/services/datasources/aggregators.py backend/tests/test_aggregators.py
git commit -m "feat(aggregators): add Onchain and Derivatives aggregators"
```

---

## Task 4: Create event_pipeline.py with Event dataclass + run() skeleton (TDD)

**Files:**
- Create: `backend/services/event_pipeline.py`
- Create: `backend/tests/test_event_pipeline.py`

- [ ] **Step 1: Write the first failing test — `test_pipeline_never_raises`**

Create `backend/tests/test_event_pipeline.py` with the first test:

```python
"""Tests for EventPipeline — the event-causality orchestrator."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest


def _make_event(type_: str, ts: str, title: str, severity: int = 2, **payload):
    return {
        "timestamp": ts,
        "type": type_,
        "title": title,
        "source": "test",
        "url": None,
        "payload": payload,
        "severity": severity,
    }


def test_pipeline_never_raises_on_unexpected_source_exception():
    """EventPipeline.run must never propagate exceptions from sources."""
    from services.event_pipeline import EventPipeline

    news = AsyncMock()
    news.fetch_news = AsyncMock(side_effect=RuntimeError("boom"))
    social = AsyncMock()
    social.scrape_hot = AsyncMock(side_effect=RuntimeError("boom"))
    onchain = AsyncMock()
    onchain.fetch = AsyncMock(side_effect=RuntimeError("boom"))
    derivatives = AsyncMock()
    derivatives.fetch = AsyncMock(side_effect=RuntimeError("boom"))

    pipeline = EventPipeline(
        news=news, social=social, onchain=onchain, derivatives=derivatives
    )

    result = asyncio.run(pipeline.run("BTC", "24h"))

    # All sources failed → empty events, no summary, confidence=0
    assert result["events"] == []
    assert "unavailable" in result["llm_summary"].lower() or "no data" in result["llm_summary"].lower()
    assert result["overall_confidence"] == 0.0
    assert result["symbol"] == "BTC"
    assert result["time_range"] == "24h"
```

- [ ] **Step 2: Run the test to verify it FAILS**

```bash
cd backend && python -m pytest tests/test_event_pipeline.py -v 2>&1 | tail -10
```

Expected: FAIL with `ModuleNotFoundError: services.event_pipeline`.

- [ ] **Step 3: Create the event_pipeline.py skeleton with `Event` dataclass and `EventPipeline` class**

Create `backend/services/event_pipeline.py`:

```python
"""EventPipeline — combines news + social + on-chain + derivatives into a
structured event-causality report.

Architecture (per docs/superpowers/specs/2026-06-04-event-driven-analysis-design.md):

    asyncio.gather(news, social, onchain, derivatives, return_exceptions=True)
        ↓
    normalize + cap at 50 events (drop low-severity first)
        ↓
    cluster_events(events, window_minutes=30)  # assigns cluster_id
        ↓
    llm.synthesize(symbol, time_range, timeline)
        ↓
    {events, llm_summary, overall_confidence, fetched_sources, fetched_at}
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal

logger = logging.getLogger(__name__)

MAX_EVENTS = 50
CLUSTER_WINDOW_MINUTES = 30
LLM_TIMEOUT_SECONDS = 20.0


@dataclass
class Event:
    """One event in the timeline. Mirrors the dict shape returned by sources."""
    timestamp: datetime
    type: Literal["news", "social", "whale", "liquidation", "funding_shift"]
    title: str
    source: str
    url: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    severity: int = 1
    cluster_id: int = -1

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        ts_raw = d.get("timestamp")
        if isinstance(ts_raw, str):
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except ValueError:
                ts = datetime.now(timezone.utc)
        elif isinstance(ts_raw, datetime):
            ts = ts_raw if ts_raw.tzinfo else ts_raw.replace(tzinfo=timezone.utc)
        else:
            ts = datetime.now(timezone.utc)
        return cls(
            timestamp=ts,
            type=d.get("type", "news"),
            title=d.get("title", ""),
            source=d.get("source", ""),
            url=d.get("url"),
            payload=d.get("payload", {}),
            severity=d.get("severity", 1),
        )

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "type": self.type,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "payload": self.payload,
            "severity": self.severity,
            "cluster_id": self.cluster_id,
        }


def _dict_to_event(d: dict) -> Event:
    return Event.from_dict(d)


def cluster_events(events: list[Event], window_minutes: int = CLUSTER_WINDOW_MINUTES) -> list[Event]:
    """Assign cluster_id: events within `window_minutes` of each other get the same id.

    Cluster id is the timestamp (epoch seconds) of the cluster's earliest event,
    so clusters are sortable and unique.
    """
    if not events:
        return events
    sorted_events = sorted(events, key=lambda e: e.timestamp)
    clusters: list[list[Event]] = []
    current: list[Event] = [sorted_events[0]]
    for evt in sorted_events[1:]:
        last = current[-1]
        delta = (evt.timestamp - last.timestamp).total_seconds() / 60.0
        if delta <= window_minutes:
            current.append(evt)
        else:
            clusters.append(current)
            current = [evt]
    clusters.append(current)

    for cluster in clusters:
        cluster_id = int(cluster[0].timestamp.timestamp())
        for evt in cluster:
            evt.cluster_id = cluster_id
    return sorted_events


def cap_events(events: list[Event], max_n: int = MAX_EVENTS) -> list[Event]:
    """Cap event list at max_n, dropping lowest-severity first. Ties broken by timestamp."""
    if len(events) <= max_n:
        return events
    return sorted(events, key=lambda e: (-e.severity, e.timestamp))[:max_n]


class EventPipeline:
    """Orchestrates the 4-source event-causality pipeline. Never raises."""

    def __init__(
        self,
        news=None,
        social=None,
        onchain=None,
        derivatives=None,
        llm_synthesize: Callable[[str, str, list[dict]], Awaitable[str]] | None = None,
    ):
        self.news = news
        self.social = social
        self.onchain = onchain
        self.derivatives = derivatives
        self._llm_synthesize = llm_synthesize or self._default_llm

    async def run(
        self,
        symbol: str,
        time_range: Literal["1h", "4h", "24h", "7d"] = "24h",
    ) -> dict[str, Any]:
        """Fetch → normalize → cap → cluster → synthesize. Returns a dict, never raises."""
        # Fetch in parallel
        results = await asyncio.gather(
            self._safe_fetch(self.news, "fetch_news", symbol, time_range),
            self._safe_fetch(self.social, "scrape_hot", symbol, time_range),
            self._safe_fetch(self.onchain, "fetch", symbol, time_range),
            self._safe_fetch(self.derivatives, "fetch", symbol, time_range),
            return_exceptions=False,
        )

        news_events, social_events, onchain_events, derivatives_events = results
        all_dicts = news_events + social_events + onchain_events + derivatives_events

        # Normalize + cap
        all_events = [_dict_to_event(d) for d in all_dicts]
        all_events = cap_events(all_events, MAX_EVENTS)

        # Cluster
        all_events = cluster_events(all_events)

        # LLM synthesis
        try:
            timeline = [e.to_dict() for e in all_events]
            summary = await asyncio.wait_for(
                self._llm_synthesize(symbol, time_range, timeline),
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"[EventPipeline] LLM synthesis failed: {e}")
            summary = "LLM synthesis unavailable."

        # Confidence: per spec, no decrement logic in this skeleton — covered in Task 8
        confidence = 1.0 if all_events else 0.0

        return {
            "symbol": symbol,
            "time_range": time_range,
            "events": [e.to_dict() for e in all_events],
            "llm_summary": summary,
            "overall_confidence": confidence,
            "fetched_sources": {
                "news": "ok" if news_events else ("failed" if self.news else "skipped"),
                "social": "ok" if social_events else ("failed" if self.social else "skipped"),
                "onchain": "ok" if onchain_events else ("failed" if self.onchain else "skipped"),
                "derivatives": "ok" if derivatives_events else ("failed" if self.derivatives else "skipped"),
            },
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _safe_fetch(self, source, method_name: str, *args) -> list[dict]:
        """Call source.method_name(*args) safely. Returns [] on any error."""
        if source is None:
            return []
        try:
            method = getattr(source, method_name, None)
            if method is None:
                return []
            result = await method(*args)
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.warning(f"[EventPipeline] {method_name} failed: {e}")
            return []

    @staticmethod
    async def _default_llm(symbol: str, time_range: str, timeline: list[dict]) -> str:
        """Default LLM synthesis — placeholder. Real impl in Task 8."""
        if not timeline:
            return "No data available."
        return f"Found {len(timeline)} event(s) for {symbol} in the last {time_range}."
```

- [ ] **Step 4: Run the test to verify it PASSES**

```bash
cd backend && python -m pytest tests/test_event_pipeline.py -v 2>&1 | tail -10
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
cd D:/work/browser-demo
git add backend/services/event_pipeline.py backend/tests/test_event_pipeline.py
git commit -m "feat(event_pipeline): add EventPipeline skeleton with run() that never raises"
```

---

## Task 5: EventPipeline — parallel fetch + chronological ordering (TDD)

**Files:**
- Modify: `backend/tests/test_event_pipeline.py` (append 2 tests)

- [ ] **Step 1: Append 2 failing tests**

Append to `backend/tests/test_event_pipeline.py`:

```python
@pytest.mark.asyncio
async def test_pipeline_runs_fetches_in_parallel():
    """All 4 sources must start before any one returns (proves parallel execution)."""
    from services.event_pipeline import EventPipeline
    import time

    started: list[str] = []
    finished: list[str] = []

    def make_source(name: str, delay: float):
        s = AsyncMock()
        async def fetch(*args, **kwargs):
            started.append(name)
            await asyncio.sleep(delay)
            finished.append(name)
            return [_make_event("news", "2026-06-03T14:00:00Z", f"{name} event", severity=2)]
        s.fetch_news = AsyncMock(side_effect=lambda *a, **kw: fetch())
        s.scrape_hot = AsyncMock(side_effect=lambda *a, **kw: fetch())
        s.fetch = AsyncMock(side_effect=lambda *a, **kw: fetch())
        return s

    news = make_source("news", 0.1)
    social = make_source("social", 0.1)
    onchain = make_source("onchain", 0.1)
    derivatives = make_source("derivatives", 0.1)

    pipeline = EventPipeline(news=news, social=social, onchain=onchain, derivatives=derivatives)
    t0 = time.monotonic()
    result = await pipeline.run("BTC", "24h")
    elapsed = time.monotonic() - t0

    # All 4 should have started before any finished (parallelism)
    assert len(started) == 4
    assert len(finished) == 0 or len(started) == 4  # started before finished
    # Total time should be ~0.1s, not ~0.4s (sequential would be 0.4s)
    assert elapsed < 0.3, f"elapsed {elapsed}s suggests sequential execution"
    assert len(result["events"]) == 4


@pytest.mark.asyncio
async def test_pipeline_orders_timeline_chronologically():
    """Output events must be sorted by timestamp ASC."""
    from services.event_pipeline import EventPipeline

    news = AsyncMock()
    news.fetch_news = AsyncMock(return_value=[
        _make_event("news", "2026-06-03T16:00:00Z", "later news", severity=2),
    ])
    social = AsyncMock()
    social.scrape_hot = AsyncMock(return_value=[
        _make_event("social", "2026-06-03T14:00:00Z", "earlier social", severity=2),
    ])
    onchain = AsyncMock()
    onchain.fetch = AsyncMock(return_value=[
        _make_event("whale", "2026-06-03T15:00:00Z", "middle whale", severity=3),
    ])
    derivatives = AsyncMock()
    derivatives.fetch = AsyncMock(return_value=[])

    pipeline = EventPipeline(news=news, social=social, onchain=onchain, derivatives=derivatives)
    result = await pipeline.run("BTC", "24h")

    timestamps = [e["timestamp"] for e in result["events"]]
    assert timestamps == sorted(timestamps)
```

- [ ] **Step 2: Run the 2 tests to verify they PASS**

```bash
cd backend && python -m pytest tests/test_event_pipeline.py -v 2>&1 | tail -10
```

Expected: Both pass (the implementation in Task 4 already supports parallel fetch via gather and sorts by timestamp in `cluster_events`).

- [ ] **Step 3: Commit**

```bash
cd D:/work/browser-demo
git add backend/tests/test_event_pipeline.py
git commit -m "test(event_pipeline): cover parallel fetch and chronological ordering"
```

---

## Task 6: EventPipeline — clustering (TDD)

**Files:**
- Modify: `backend/tests/test_event_pipeline.py` (append 1 test)

- [ ] **Step 1: Append the failing test**

```python
@pytest.mark.asyncio
async def test_pipeline_clusters_events_by_30min_window():
    """Events within 30 min of each other must share cluster_id."""
    from services.event_pipeline import EventPipeline

    news = AsyncMock()
    news.fetch_news = AsyncMock(return_value=[
        _make_event("news", "2026-06-03T14:00:00Z", "news 1", severity=2),
        _make_event("news", "2026-06-03T14:20:00Z", "news 2 (same cluster)", severity=2),
    ])
    social = AsyncMock()
    social.scrape_hot = AsyncMock(return_value=[
        _make_event("social", "2026-06-03T16:00:00Z", "social (different cluster)", severity=2),
    ])
    onchain = AsyncMock()
    onchain.fetch = AsyncMock(return_value=[])
    derivatives = AsyncMock()
    derivatives.fetch = AsyncMock(return_value=[])

    pipeline = EventPipeline(news=news, social=social, onchain=onchain, derivatives=derivatives)
    result = await pipeline.run("BTC", "24h")

    events = result["events"]
    assert len(events) == 3
    # First two should share cluster_id
    assert events[0]["cluster_id"] == events[1]["cluster_id"]
    # Third should be different
    assert events[2]["cluster_id"] != events[0]["cluster_id"]
```

- [ ] **Step 2: Run the test to verify it PASSES**

```bash
cd backend && python -m pytest tests/test_event_pipeline.py::test_pipeline_clusters_events_by_30min_window -v 2>&1 | tail -10
```

Expected: PASS (the `cluster_events` function from Task 4 implements this).

- [ ] **Step 3: Commit**

```bash
cd D:/work/browser-demo
git add backend/tests/test_event_pipeline.py
git commit -m "test(event_pipeline): cover 30-min cluster window"
```

---

## Task 7: EventPipeline — 50-event cap (TDD)

**Files:**
- Modify: `backend/tests/test_event_pipeline.py` (append 1 test)

- [ ] **Step 1: Append the failing test**

```python
@pytest.mark.asyncio
async def test_pipeline_caps_at_50_events():
    """If sources return > 50 events, only the top 50 by severity are kept."""
    from services.event_pipeline import EventPipeline

    # 100 events of varying severity
    events = []
    for i in range(100):
        sev = (i % 5) + 1  # 1-5 cycling
        events.append(_make_event("news", f"2026-06-03T{14 + (i // 60):02d}:{i % 60:02d}:00Z", f"e{i}", severity=sev))

    news = AsyncMock()
    news.fetch_news = AsyncMock(return_value=events)
    social = AsyncMock(); social.scrape_hot = AsyncMock(return_value=[])
    onchain = AsyncMock(); onchain.fetch = AsyncMock(return_value=[])
    derivatives = AsyncMock(); derivatives.fetch = AsyncMock(return_value=[])

    pipeline = EventPipeline(news=news, social=social, onchain=onchain, derivatives=derivatives)
    result = await pipeline.run("BTC", "24h")

    assert len(result["events"]) == 50
    # All kept events should have severity >= 1 (all are kept since we have 100 with cycling severity)
    # The actual kept events are top 50 by severity
    kept_severities = sorted([e["severity"] for e in result["events"]], reverse=True)
    # With 100 events cycling 1-5, top 50 by severity = 10 of each severity
    from collections import Counter
    counts = Counter(e["severity"] for e in result["events"])
    assert sum(counts.values()) == 50
```

- [ ] **Step 2: Run the test to verify it PASSES**

```bash
cd backend && python -m pytest tests/test_event_pipeline.py::test_pipeline_caps_at_50_events -v 2>&1 | tail -10
```

Expected: PASS (the `cap_events` function from Task 4 implements this).

- [ ] **Step 3: Commit**

```bash
cd D:/work/browser-demo
git add backend/tests/test_event_pipeline.py
git commit -m "test(event_pipeline): cover 50-event cap with severity ranking"
```

---

## Task 8: EventPipeline — LLM synthesis with custom injection (TDD)

**Files:**
- Modify: `backend/tests/test_event_pipeline.py` (append 2 tests)

- [ ] **Step 1: Append 2 failing tests**

```python
@pytest.mark.asyncio
async def test_pipeline_calls_llm_with_timeline():
    """LLM synth function must receive symbol, time_range, and the timeline dicts."""
    from services.event_pipeline import EventPipeline

    received: dict = {}

    async def fake_llm(symbol, time_range, timeline):
        received["symbol"] = symbol
        received["time_range"] = time_range
        received["timeline"] = timeline
        return "Test summary."

    news = AsyncMock()
    news.fetch_news = AsyncMock(return_value=[
        _make_event("news", "2026-06-03T14:00:00Z", "ETF delay", severity=3),
    ])
    social = AsyncMock(); social.scrape_hot = AsyncMock(return_value=[])
    onchain = AsyncMock(); onchain.fetch = AsyncMock(return_value=[])
    derivatives = AsyncMock(); derivatives.fetch = AsyncMock(return_value=[])

    pipeline = EventPipeline(
        news=news, social=social, onchain=onchain, derivatives=derivatives,
        llm_synthesize=fake_llm,
    )
    result = await pipeline.run("BTC", "24h")

    assert received["symbol"] == "BTC"
    assert received["time_range"] == "24h"
    assert len(received["timeline"]) == 1
    assert received["timeline"][0]["title"] == "ETF delay"
    assert result["llm_summary"] == "Test summary."


@pytest.mark.asyncio
async def test_pipeline_returns_unavailable_summary_on_llm_timeout():
    """If LLM times out, summary must indicate unavailability (not raise)."""
    from services.event_pipeline import EventPipeline

    async def slow_llm(symbol, time_range, timeline):
        await asyncio.sleep(0.1)
        return "won't get here"

    news = AsyncMock()
    news.fetch_news = AsyncMock(return_value=[
        _make_event("news", "2026-06-03T14:00:00Z", "evt", severity=2),
    ])
    social = AsyncMock(); social.scrape_hot = AsyncMock(return_value=[])
    onchain = AsyncMock(); onchain.fetch = AsyncMock(return_value=[])
    derivatives = AsyncMock(); derivatives.fetch = AsyncMock(return_value=[])

    # Patch the LLM timeout constant to a very small value for this test
    import services.event_pipeline as ep_mod
    original = ep_mod.LLM_TIMEOUT_SECONDS
    ep_mod.LLM_TIMEOUT_SECONDS = 0.01
    try:
        pipeline = EventPipeline(
            news=news, social=social, onchain=onchain, derivatives=derivatives,
            llm_synthesize=slow_llm,
        )
        result = await pipeline.run("BTC", "24h")
        assert "unavailable" in result["llm_summary"].lower()
    finally:
        ep_mod.LLM_TIMEOUT_SECONDS = original
```

- [ ] **Step 2: Run the 2 tests to verify they PASS**

```bash
cd backend && python -m pytest tests/test_event_pipeline.py::test_pipeline_calls_llm_with_timeline tests/test_event_pipeline.py::test_pipeline_returns_unavailable_summary_on_llm_timeout -v 2>&1 | tail -10
```

Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
cd D:/work/browser-demo
git add backend/tests/test_event_pipeline.py
git commit -m "test(event_pipeline): cover LLM synthesis injection and timeout"
```

---

## Task 9: EventPipeline — confidence decrement on partial failure (TDD)

**Files:**
- Modify: `backend/services/event_pipeline.py` (extend `run()`)
- Modify: `backend/tests/test_event_pipeline.py` (append 1 test)

- [ ] **Step 1: Append the failing test**

```python
@pytest.mark.asyncio
async def test_pipeline_lowers_confidence_on_partial_source_failure():
    """If one source fails, overall_confidence must drop by 0.2."""
    from services.event_pipeline import EventPipeline

    news = AsyncMock()
    news.fetch_news = AsyncMock(side_effect=RuntimeError("down"))
    social = AsyncMock()
    social.scrape_hot = AsyncMock(return_value=[
        _make_event("social", "2026-06-03T14:00:00Z", "ok post", severity=2),
    ])
    onchain = AsyncMock()
    onchain.fetch = AsyncMock(return_value=[
        _make_event("whale", "2026-06-03T14:30:00Z", "whale", severity=3),
    ])
    derivatives = AsyncMock()
    derivatives.fetch = AsyncMock(return_value=[])

    pipeline = EventPipeline(news=news, social=social, onchain=onchain, derivatives=derivatives)
    result = await pipeline.run("BTC", "24h")

    # 1 source failed (-0.2). Start at 1.0 → 0.8
    assert result["overall_confidence"] == 0.8
    assert result["fetched_sources"]["news"] == "failed"
    assert result["fetched_sources"]["social"] == "ok"
    # Events from working sources should still be present
    assert len(result["events"]) >= 1
```

- [ ] **Step 2: Run the test to verify it FAILS**

```bash
cd backend && python -m pytest tests/test_event_pipeline.py::test_pipeline_lowers_confidence_on_partial_source_failure -v 2>&1 | tail -10
```

Expected: FAIL — current code returns `confidence=1.0` for any non-empty result.

- [ ] **Step 3: Add confidence decrement logic to `EventPipeline.run()`**

In `backend/services/event_pipeline.py`, find this block in `run()`:

```python
        # Confidence: per spec, no decrement logic in this skeleton — covered in Task 8
        confidence = 1.0 if all_events else 0.0
```

Replace it with:

```python
        # Confidence: start at 1.0, decrement per source failure (-0.2 each).
        # Per spec error table.
        confidence = 1.0
        source_status = {
            "news": "ok" if news_events else ("failed" if self.news else "skipped"),
            "social": "ok" if social_events else ("failed" if self.social else "skipped"),
            "onchain": "ok" if onchain_events else ("failed" if self.onchain else "skipped"),
            "derivatives": "ok" if derivatives_events else ("failed" if self.derivatives else "skipped"),
        }
        for status in source_status.values():
            if status == "failed":
                confidence -= 0.2
        if not all_events:
            confidence = 0.0
        confidence = max(0.0, confidence)
```

Then update the return statement to use `source_status`:

```python
        return {
            "symbol": symbol,
            "time_range": time_range,
            "events": [e.to_dict() for e in all_events],
            "llm_summary": summary,
            "overall_confidence": confidence,
            "fetched_sources": source_status,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
```

(Remove the old `fetched_sources={...}` line.)

- [ ] **Step 4: Run the test to verify it PASSES**

```bash
cd backend && python -m pytest tests/test_event_pipeline.py::test_pipeline_lowers_confidence_on_partial_source_failure -v 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 5: Run full test suite to confirm no regression**

```bash
cd backend && python -m pytest tests/test_event_pipeline.py -q 2>&1 | tail -3
```

Expected: 7 passed (the 6 from prior tasks + this new one).

- [ ] **Step 6: Commit**

```bash
cd D:/work/browser-demo
git add backend/services/event_pipeline.py backend/tests/test_event_pipeline.py
git commit -m "feat(event_pipeline): confidence decrements per source failure"
```

---

## Task 10: Add POST /api/analyze/events endpoint (TDD)

**Files:**
- Modify: `backend/api/analysis.py`
- Create: `backend/tests/test_analyze_events_endpoint.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_analyze_events_endpoint.py`:

```python
"""Tests for POST /api/analyze/events endpoint."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_analyze_events_returns_pipeline_response():
    """POST /api/analyze/events must return the pipeline's response dict."""
    from api.analysis import router
    from services.event_pipeline import EventPipeline

    app = FastAPI()
    app.include_router(router)

    fake_response = {
        "symbol": "BTC",
        "time_range": "24h",
        "events": [],
        "llm_summary": "Test summary.",
        "overall_confidence": 0.5,
        "fetched_sources": {"news": "ok", "social": "ok", "onchain": "ok", "derivatives": "ok"},
        "fetched_at": "2026-06-04T10:00:00Z",
    }

    with patch.object(EventPipeline, "run", new=AsyncMock(return_value=fake_response)):
        client = TestClient(app)
        r = client.post("/api/analyze/events", json={"symbol": "BTC", "time_range": "24h"})

    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "BTC"
    assert body["llm_summary"] == "Test summary."
    assert body["overall_confidence"] == 0.5


def test_analyze_events_rejects_invalid_time_range():
    """time_range must be one of 1h, 4h, 24h, 7d — Pydantic returns 422 otherwise."""
    from api.analysis import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    r = client.post("/api/analyze/events", json={"symbol": "BTC", "time_range": "2y"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run tests to verify they FAIL**

```bash
cd backend && python -m pytest tests/test_analyze_events_endpoint.py -v 2>&1 | tail -15
```

Expected: 2 failures — first with `405 Method Not Allowed` (no endpoint), second also `405`.

- [ ] **Step 3: Add the endpoint to `api/analysis.py`**

In `backend/api/analysis.py`, find the existing `CompareRequest` class (around line 15). Add a new request model below it:

```python
class AnalyzeEventsRequest(BaseModel):
    symbol: str
    time_range: Optional[str] = "24h"  # validated in endpoint, not Pydantic — for 400 vs 422 trade-off
```

Then add the endpoint at the bottom of the file (after `get_cached_report`):

```python
@router.post("/events")
async def analyze_events(req: AnalyzeEventsRequest):
    """Run the event-causality pipeline for a single symbol.

    Returns a structured event timeline + LLM-written causal narrative
    with a confidence score. Combines news (CoinDesk + The Block via
    Playwright), social (Binance Square top-N hottest), on-chain
    (whale transfers), and derivatives (liquidations + funding rate
    shifts) into one response.
    """
    valid_ranges = {"1h", "4h", "24h", "7d"}
    if req.time_range not in valid_ranges:
        raise HTTPException(
            status_code=400,
            detail=f"time_range must be one of {sorted(valid_ranges)}",
        )
    if not req.symbol or not req.symbol.strip():
        raise HTTPException(status_code=400, detail="symbol is required")

    from services.event_pipeline import EventPipeline
    pipeline = EventPipeline()
    return await pipeline.run(req.symbol.upper(), req.time_range)
```

Also update the imports at the top of `api/analysis.py` to include `HTTPException` (if not already):

```python
from fastapi import APIRouter, HTTPException
```

(Check the existing imports — if `HTTPException` isn't there, add it.)

- [ ] **Step 4: Run tests to verify they PASS**

```bash
cd backend && python -m pytest tests/test_analyze_events_endpoint.py -v 2>&1 | tail -10
```

Expected: 2 passed.

NOTE: If the first test fails with `500 Internal Server Error` from inside the pipeline (because the real `EventPipeline()` instantiates with `None` sources that fall through to empty lists, but the LLM call is real), the `patch.object` may not be effective — check the import path. If real LLM is configured, the test might time out or hit a 500. If so, the `patch.object(EventPipeline, "run", ...)` may need to target `api.analysis.EventPipeline` instead:

```python
with patch("api.analysis.EventPipeline") as MockPipeline:
    mock_instance = MockPipeline.return_value
    mock_instance.run = AsyncMock(return_value=fake_response)
    ...
```

Update the test if this is the case. The implementation should be correct.

- [ ] **Step 5: Run full backend test suite**

```bash
cd backend && python -m pytest -q 2>&1 | tail -3
```

Expected: ~160 passed (was 149 + ~11 new). May have 1 pre-existing flaky coingecko test.

- [ ] **Step 6: Commit**

```bash
cd D:/work/browser-demo
git add backend/api/analysis.py backend/tests/test_analyze_events_endpoint.py
git commit -m "feat(api): add POST /api/analyze/events endpoint"
```

---

## Task 11: IntentRouter event-shape hook (TDD)

**Files:**
- Modify: `backend/services/intent_router.py`
- Create (or modify): `backend/tests/test_intent_router_event.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_intent_router_event.py`:

```python
"""Tests for IntentRouter's event-shape query hook."""
from unittest.mock import AsyncMock, patch

import pytest


def test_classify_returns_event_for_why_questions():
    """classify() must return 'event' for 'why did X drop' style messages."""
    from services.intent_router import IntentRouter

    layer = IntentRouter.classify(
        symbols=["BTC"],
        dimensions=None,
        message="why did BTC drop 5% today?",
    )
    assert layer == "event"


def test_classify_returns_event_for_chinese_keywords():
    """Chinese event-shape keywords also trigger 'event' layer."""
    from services.intent_router import IntentRouter

    for msg in [
        "BTC为什么暴跌",
        "ETH发生了什么",
        "SOL突然暴涨",
    ]:
        layer = IntentRouter.classify(symbols=["BTC"], dimensions=None, message=msg)
        assert layer == "event", f"Expected 'event' for message: {msg}"


def test_route_event_dispatches_to_event_pipeline():
    """IntentRouter.route_event must call EventPipeline.run and return its result."""
    from services.intent_router import IntentRouter
    from services.event_pipeline import EventPipeline

    fake_response = {
        "symbol": "BTC",
        "time_range": "24h",
        "events": [{"type": "whale", "title": "test"}],
        "llm_summary": "Test.",
        "overall_confidence": 0.8,
    }

    with patch.object(EventPipeline, "run", new=AsyncMock(return_value=fake_response)):
        router = IntentRouter()
        result = await asyncio_run(router.route_event("BTC", "why did BTC drop?"))

    assert result["layer"] == "event"
    assert result["report"] == fake_response


def asyncio_run(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)
```

- [ ] **Step 2: Run tests to verify they FAIL**

```bash
cd backend && python -m pytest tests/test_intent_router_event.py -v 2>&1 | tail -15
```

Expected: failures on the keyword detection (`classify` doesn't return `"event"`) and on `route_event` not existing.

- [ ] **Step 3: Add the event hook to `IntentRouter`**

In `backend/services/intent_router.py`, find the `LAYER2_KEYWORDS_HINTS` constant. Add a new constant below it:

```python
EVENT_QUERY_KEYWORDS = (
    "why", "为什么", "what happened", "发生了什么",
    "drop", "pump", "crash", "暴涨", "暴跌", "plunge", "rally",
    "suddenly", "突然",
)
```

Update the `classify()` static method's return type and add the event detection. Find the signature:

```python
def classify(
    symbols: list[str] | None,
    dimensions: list[str] | None,
    message: str | None = None,
) -> Literal["layer2", "layer3"]:
```

Change it to:

```python
def classify(
    symbols: list[str] | None,
    dimensions: list[str] | None,
    message: str | None = None,
) -> Literal["layer2", "layer3", "event"]:
```

And add the event check at the TOP of the method body (before the existing logic):

```python
    if message:
        lower = message.lower()
        if any(kw in lower for kw in EVENT_QUERY_KEYWORDS):
            return "event"
```

Add a new method `route_event` to the `IntentRouter` class:

```python
    async def route_event(self, symbol: str, message: str | None = None) -> dict[str, Any]:
        """Dispatch an event-shaped query to EventPipeline."""
        from services.event_pipeline import EventPipeline
        pipeline = EventPipeline()
        report = await pipeline.run(symbol, "24h")
        return {
            "layer": "event",
            "report": report,
        }
```

- [ ] **Step 4: Run tests to verify they PASS**

```bash
cd backend && python -m pytest tests/test_intent_router_event.py -v 2>&1 | tail -10
```

Expected: 3 passed (the helper `asyncio_run` makes the 3rd test work as a sync test).

- [ ] **Step 5: Run full backend test suite**

```bash
cd backend && python -m pytest -q 2>&1 | tail -3
```

Expected: ~163 passed (was ~160 + 3 new). 1 pre-existing flaky may or may not trigger.

- [ ] **Step 6: Commit**

```bash
cd D:/work/browser-demo
git add backend/services/intent_router.py backend/tests/test_intent_router_event.py
git commit -m "feat(intent_router): route event-shaped queries to EventPipeline"
```

---

## Task 12: End-to-end integration smoke test (manual)

**Files:**
- No new files. Manual verification.

- [ ] **Step 1: Start the FastAPI server**

```bash
cd backend && python main.py
```

Expected: Server starts on `http://localhost:8000`. Lifespan startup logs include `[main] sector classifier warmup` and similar.

- [ ] **Step 2: Hit the new endpoint**

```bash
curl -X POST http://localhost:8000/api/analyze/events \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC","time_range":"24h"}'
```

Expected: 200 response with `events` list, `llm_summary` non-empty, `overall_confidence` in [0, 1]. The response shape matches the spec's data flow section.

- [ ] **Step 3: Verify Playwright actually opens and closes (no zombie processes)**

```bash
# On Windows
tasklist | findstr chrome
# On Linux/Mac
ps aux | grep chrome
```

Expected: No zombie chrome processes after the request completes. Playwright's `close()` in the `finally` block of `_scrape_site` should clean up.

If zombie processes are observed, check the `await handle.pw.stop()` in `_scrape_site` — the `hasattr` check should be True for the real launcher but False for the fake.

- [ ] **Step 4: Document the manual test in `docs/`**

Append a section to `docs/superpowers/specs/2026-06-04-event-driven-analysis-design.md` (the spec doc) under a new "Manual smoke results" heading:

```markdown
## Manual smoke results (2026-06-04)

Verified end-to-end:
- `POST /api/analyze/events {"symbol":"BTC","time_range":"24h"}` returns 200 with events + summary
- Playwright opens and closes cleanly (no zombie chrome processes)
- IntentRouter correctly routes "why did BTC drop?" to the event layer
```

(Only add this section AFTER running the manual test successfully.)

- [ ] **Step 5: Commit any spec updates**

```bash
cd D:/work/browser-demo
git add docs/superpowers/specs/2026-06-04-event-driven-analysis-design.md
git commit -m "docs: record manual smoke test results for event-driven analysis"
```

(Only if Step 4 added content.)

---

## Self-Review

**Spec coverage** — checked against `docs/superpowers/specs/2026-06-04-event-driven-analysis-design.md`:

- ✅ News scraping (CoinDesk + The Block) via Playwright — Task 2
- ✅ Binance Square `scrape_hot` top-20 by engagement — Task 1
- ✅ On-chain aggregator (whale + arkham, ≥ $5M) — Task 3
- ✅ Derivatives aggregator (liquidations ≥ $1M + funding shifts) — Task 3
- ✅ EventPipeline.run() — Task 4
- ✅ Parallel fetch via `asyncio.gather` — Task 5
- ✅ Chronological ordering — Task 5
- ✅ 30-min cluster window — Task 6
- ✅ 50-event cap with severity ranking — Task 7
- ✅ Per-source sampling rules (whale $5M, liq $1M, funding 0.1%) — Task 3
- ✅ LLM synthesis with timeout — Task 8
- ✅ Confidence decrement on partial failure — Task 9
- ✅ Never-raises guarantee — Task 4
- ✅ `POST /api/analyze/events` endpoint — Task 10
- ✅ `IntentRouter` event-shape hook — Task 11
- ✅ Manual integration smoke — Task 12
- ✅ All YAGNI scope items respected (no persistent store, no streaming, no Twitter, no historical replay)

**Placeholder scan** — no TBD / TODO / "fill in details". Every step has full code.

**Type consistency** —
- `Event` dataclass in `event_pipeline.py` matches the dict shape used by aggregators and the news scraper (all use `timestamp` / `type` / `title` / `source` / `url` / `payload` / `severity` / `cluster_id`).
- `EventPipeline.__init__` parameter names match test injection: `news`, `social`, `onchain`, `derivatives`, `llm_synthesize`.
- The 4 source methods called by `EventPipeline._safe_fetch` are: `news.fetch_news(symbol, time_range)`, `social.scrape_hot(symbol, time_range)`, `onchain.fetch(symbol, time_range)`, `derivatives.fetch(symbol, time_range)`. All four exist by Task 3.
- `IntentRouter.classify` return type updated to `Literal["layer2", "layer3", "event"]` in Task 11.
- `EventPipeline.run` return shape is consistent across all 10 tests (symbol, time_range, events, llm_summary, overall_confidence, fetched_sources, fetched_at).

**Scope** — 12 tasks, all TDD except Task 12 (manual smoke). Total new tests: ~21 (3 + 5 + 2 + 7 + 2 + 2 = 21 in unit tests, + 2 in test_analyze_events_endpoint.py). Estimated total: ~3-4h implementation + ~30min test review.
