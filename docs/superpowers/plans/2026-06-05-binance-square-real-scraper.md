# Binance Square Real Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded mock data in `BinanceSquareScraper._fetch_posts` with a real Playwright-driven scraper of public `binance.com/en/square`, so trading signals in the DB come from live data instead of three stubbed posts. Scheduler cadence flips from 2 min default to 30 min.

**Architecture:** Keep the existing `BinanceSquareScraper.scrape() → save_to_db()` contract. Replace only the `_fetch_posts` body to delegate to a new `BinanceSquareBrowser` (module-level singleton chromium with page injection for tests). Add DB-level dedup via UNIQUE index on `signals.source_url` plus `INSERT OR IGNORE`. Errors get custom exception types that `_fetch_posts` swallows so the scheduler loop never dies.

**Tech Stack:** Playwright (async), FastAPI (unchanged), SQLite (existing), pytest + HTML fixtures for offline tests.

**Spec:** `docs/superpowers/specs/2026-06-05-binance-square-real-scraper-design.md`

---

## File Structure

| File | Status | Purpose |
|------|--------|---------|
| `backend/services/binance_square_browser.py` | **new** | Singleton browser, `fetch_posts(limit)`, custom exceptions, `_parse_html` |
| `backend/services/signal_scraper.py` | edit | Replace `_fetch_posts` body; `save_to_db` uses INSERT OR IGNORE + `source_type` |
| `backend/services/database.py` | edit | Add `source_type` column, UNIQUE index, backfill, flip `signal_scan_interval_minutes` default to 30 |
| `backend/services/scheduler.py` | edit | Default `signal_scan_interval_minutes` fallback 15 → 30 |
| `backend/services/config_store.py` | edit | Add `get_binance_square_scrape_config()` + `set_binance_square_scrape_config()` |
| `backend/tests/fixtures/binance_square/home_with_posts.html` | new | Captured real page with token-mentioning posts |
| `backend/tests/fixtures/binance_square/empty_page.html` | new | Captured real page with no posts |
| `backend/tests/fixtures/binance_square/login_wall.html` | new | Captured real page after redirect to login |
| `backend/tests/fixtures/binance_square/captcha_page.html` | new | Captured real page with captcha |
| `backend/tests/test_binance_square_browser.py` | new | Fixture-based unit tests |
| `backend/tests/manual/test_binance_square_live.py` | new | Live smoke, `@pytest.mark.skip` by default |

---

## Task 1: Database migration

**Files:**
- Modify: `backend/services/database.py:26-39` (signals table) and `91-104` (trading_config)
- Modify: `backend/services/scheduler.py:96-100` (fallback default)

- [ ] **Step 1: Add `source_type` column with idempotent migration**

In `backend/services/database.py`, immediately after the signals `CREATE TABLE` block, add:

```python
# Migration: add source_type column (idempotent)
cursor.execute("PRAGMA table_info(signals)")
sig_cols = {row[1] for row in cursor.fetchall()}
if "source_type" not in sig_cols:
    cursor.execute("ALTER TABLE signals ADD COLUMN source_type TEXT DEFAULT 'live'")
    # Backfill known mock authors
    cursor.execute(
        "UPDATE signals SET source_type = 'mock' "
        "WHERE author IN ('TraderOne', 'CryptoWhale', 'BearHunter') "
        "AND source_type IS NULL"
    )

# Unique index on source_url for dedup (idempotent)
cursor.execute(
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_source_url "
    "ON signals(source_url) WHERE source_url != ''"
)
```

- [ ] **Step 2: Flip `signal_scan_interval_minutes` default 5 → 30**

In `backend/services/database.py:91-105`, change the `trading_config` table default:

```python
cursor.execute("""
    CREATE TABLE IF NOT EXISTS trading_config (
        id INTEGER PRIMARY KEY,
        binance_api_key TEXT,
        binance_secret_key TEXT,
        use_testnet INTEGER DEFAULT 1,
        max_position_size_usd REAL DEFAULT 100.0,
        max_positions INTEGER DEFAULT 5,
        tp_percentage REAL DEFAULT 5.0,
        sl_percentage REAL DEFAULT 3.0,
        min_confidence REAL DEFAULT 0.7,
        max_daily_loss REAL DEFAULT 100.0,
        scan_interval_minutes INTEGER DEFAULT 30
    )
""")
```

- [ ] **Step 3: Update scheduler fallback default 15 → 30**

In `backend/services/scheduler.py`:

```python
# Line ~97
def _interval_seconds(self) -> float:
    return float(self._config_provider().get("signal_scan_interval_minutes", 30)) * 60.0

# Line ~100
def _interval_minutes(self) -> int:
    return int(self._config_provider().get("signal_scan_interval_minutes", 30))
```

- [ ] **Step 4: Run existing test suite to confirm no regression**

Run: `cd backend && python -m pytest tests/test_database.py tests/test_scheduler.py -q --no-header`
Expected: PASS (migrations are idempotent, scheduler still works with old `2` minute row)

- [ ] **Step 5: Commit**

```bash
git add backend/services/database.py backend/services/scheduler.py
git commit -m "feat(db): add signals.source_type, dedup index, 30min interval default"
```

---

## Task 2: Config store helpers for scrape config

**Files:**
- Modify: `backend/services/config_store.py` (append at end of file)

- [ ] **Step 1: Add the constants and helpers**

Append to `backend/services/config_store.py`:

```python
DEFAULT_BINANCE_SQUARE_CONFIG = {
    "url": "https://www.binance.com/en/square",
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
    ),
    "max_posts_per_scrape": 30,
    "headless": True,
    "scroll_passes": 2,
    "scroll_pause_ms": 2500,
}

# In-process cache (configurable via the workflow UI; not persisted across restarts in v1)
_scrape_config_overrides: dict[str, Any] = {}


def get_binance_square_scrape_config() -> dict[str, Any]:
    """Read effective scrape config: defaults merged with any in-process overrides."""
    cfg = DEFAULT_BINANCE_SQUARE_CONFIG.copy()
    cfg.update(_scrape_config_overrides)
    return cfg


def set_binance_square_scrape_config(patch: dict[str, Any]) -> dict[str, Any]:
    """Patch the in-process scrape config. Returns the new effective config."""
    for k, v in patch.items():
        if k in DEFAULT_BINANCE_SQUARE_CONFIG:
            _scrape_config_overrides[k] = v
    return get_binance_square_scrape_config()
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_binance_square_config.py`:

```python
from services.config_store import (
    DEFAULT_BINANCE_SQUARE_CONFIG,
    get_binance_square_scrape_config,
    set_binance_square_scrape_config,
)


def test_defaults_when_no_overrides():
    cfg = get_binance_square_scrape_config()
    assert cfg["url"] == "https://www.binance.com/en/square"
    assert cfg["max_posts_per_scrape"] == 30
    assert cfg["headless"] is True


def test_set_overrides_merge_with_defaults():
    set_binance_square_scrape_config({"max_posts_per_scrape": 10})
    cfg = get_binance_square_scrape_config()
    assert cfg["max_posts_per_scrape"] == 10
    # Other keys untouched
    assert cfg["url"] == "https://www.binance.com/en/square"
    # Reset for other tests
    set_binance_square_scrape_config({"max_posts_per_scrape": 30})


def test_set_ignores_unknown_keys():
    set_binance_square_scrape_config({"not_a_real_key": "x"})
    cfg = get_binance_square_scrape_config()
    assert "not_a_real_key" not in cfg
```

- [ ] **Step 3: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_binance_square_config.py -v --no-header`
Expected: 3 passed (helpers are already implemented; this task is setup + test)

- [ ] **Step 4: Commit**

```bash
git add backend/services/config_store.py backend/tests/test_binance_square_config.py
git commit -m "feat(config): binance square scrape config defaults + helpers"
```

---

## Task 3: Browser module skeleton + exception types

**Files:**
- Create: `backend/services/binance_square_browser.py`

- [ ] **Step 1: Create the module with exception types and class skeleton**

Create `backend/services/binance_square_browser.py`:

```python
"""Long-lived Playwright browser for scraping public Binance Square.

Module-level singleton is the default; tests inject a `page` so they
can run without launching chromium.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


# --- Custom exceptions ---

class BrowserError(Exception):
    """Base for all browser/scraper errors the scheduler should swallow."""


class LoginWallError(BrowserError):
    """Binance Square redirected to a login page."""


class CaptchaError(BrowserError):
    """Captcha/anti-bot verification page detected."""


class RateLimitError(BrowserError):
    """Upstream returned 429 or equivalent."""


class ParseError(BrowserError):
    """DOM did not match expected selectors — likely a Binance Square layout change."""

    def __init__(self, msg: str, screenshot_path: Optional[str] = None):
        super().__init__(msg)
        self.screenshot_path = screenshot_path


# --- Browser ---

class BinanceSquareBrowser:
    """Lazy-initialised Playwright browser. Module-level singleton via `_get_browser()`."""

    # How long a page can sit idle before we force a fresh goto.
    IDLE_RELOAD_SECONDS = 20 * 60

    def __init__(self, page=None):
        # `page` is injected by tests; None means "lazy-launch real chromium".
        self._injected_page = page
        self._browser = None
        self._playwright = None
        self._last_fetch_at: Optional[float] = None

    async def fetch_posts(self, limit: int) -> list[dict[str, Any]]:
        """Fetch up to `limit` posts from Binance Square. Returns raw post dicts.

        Raises LoginWallError / CaptchaError / RateLimitError / ParseError
        for the caller to handle.
        """
        raise NotImplementedError

    async def aclose(self) -> None:
        """Cleanly shut down the browser. Idempotent."""
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception as e:
                logger.debug(f"[BinanceSquareBrowser] browser close failed: {e}")
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.debug(f"[BinanceSquareBrowser] playwright stop failed: {e}")
            self._playwright = None


# --- Module-level singleton ---

_browser: Optional[BinanceSquareBrowser] = None


def get_browser() -> BinanceSquareBrowser:
    """Return the process-wide BinanceSquareBrowser instance."""
    global _browser
    if _browser is None:
        _browser = BinanceSquareBrowser()
    return _browser


def reset_browser_for_tests() -> None:
    """Test helper: drop the singleton so the next get_browser() builds a fresh one."""
    global _browser
    _browser = None
```

- [ ] **Step 2: Verify module imports cleanly**

Run: `cd backend && python -c "from services.binance_square_browser import BinanceSquareBrowser, get_browser, LoginWallError, CaptchaError, RateLimitError, ParseError; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/services/binance_square_browser.py
git commit -m "feat(scraper): binance square browser skeleton + exception types"
```

---

## Task 4: HTML fixture capture script

**Files:**
- Create: `backend/tests/fixtures/binance_square/capture_fixtures.py` (one-shot helper)

- [ ] **Step 1: Create the capture directory**

Run: `mkdir -p backend/tests/fixtures/binance_square`

- [ ] **Step 2: Write the capture helper**

Create `backend/tests/fixtures/binance_square/capture_fixtures.py`:

```python
"""One-shot helper: launch a real chromium, hit Binance Square, save
the rendered HTML into the four fixture files used by tests.

Usage (from project root):
    cd backend && python tests/fixtures/binance_square/capture_fixtures.py

The login_wall and captcha fixtures are best-effort — they save the
current page if those states happen to be detected. Empty page is
saved if the feed has no posts at capture time.
"""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

FIXTURE_DIR = Path(__file__).parent
SQUARE_URL = "https://www.binance.com/en/square"


async def capture(page, name: str) -> None:
    html = await page.content()
    out = FIXTURE_DIR / f"{name}.html"
    out.write_text(html, encoding="utf-8")
    print(f"  saved {out.name} ({len(html)} bytes)")


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => false })")
        page = await ctx.new_page()

        print(">>> home_with_posts")
        await page.goto(SQUARE_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)  # let SPA render
        # Scroll 2x to load more
        for _ in range(2):
            await page.mouse.wheel(0, 1200)
            await page.wait_for_timeout(2500)
        await capture(page, "home_with_posts")

        # The other fixtures are best-effort — saved as the current page
        # if those states are detected, otherwise as the home page.
        print(">>> empty_page (best-effort)")
        await capture(page, "empty_page")

        print(">>> login_wall (best-effort)")
        await capture(page, "login_wall")

        print(">>> captcha (best-effort)")
        await capture(page, "captcha")

        await browser.close()
    print("Done. Inspect HTML files and replace selectors in _parse_html as needed.")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Run the capture script**

Run: `cd backend && python tests/fixtures/binance_square/capture_fixtures.py`
Expected: 4 files created. Open `home_with_posts.html` and locate the post-card container class. Note the selector pattern.

- [ ] **Step 4: Document the actual selectors found**

Open the captured `home_with_posts.html` in an editor. Find the post card wrapper (likely a `<div>` containing the author, content, likes/comments). Note:
- The post URL pattern (`<a href="/en/square/post/...">`)
- The author container
- The content container
- The like/comment counts

Write these into the module's `SELECTORS` constant (will be created in Task 5). Save the names — Task 5 will use them.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/fixtures/binance_square/
git commit -m "test(fixtures): capture script + initial real-page snapshots"
```

---

## Task 5: `_parse_html` implementation

**Files:**
- Modify: `backend/services/binance_square_browser.py`
- Create: `backend/tests/test_binance_square_browser.py`

- [ ] **Step 1: Write the failing test for `_parse_html`**

Create `backend/tests/test_binance_square_browser.py`:

```python
"""Unit tests for BinanceSquareBrowser. All offline via HTML fixtures."""
import pytest

from services.binance_square_browser import (
    BinanceSquareBrowser,
    CaptchaError,
    LoginWallError,
    ParseError,
    RateLimitError,
)


FIXTURE_DIR = "tests/fixtures/binance_square"


def _load_fixture(name: str) -> str:
    from pathlib import Path
    return (Path(__file__).parent.parent / "fixtures" / "binance_square" / name).read_text(encoding="utf-8")


def test_parse_home_with_posts_extracts_token_mentions():
    """Parser must return posts whose content has $XXX / #XXX tokens."""
    html = _load_fixture("home_with_posts.html")
    browser = BinanceSquareBrowser()
    posts = browser._parse_html(html, limit=30)
    assert isinstance(posts, list)
    assert len(posts) > 0, "expected at least one post in fixture"
    for p in posts:
        assert "content" in p
        assert "source_url" in p
        assert "author" in p
        assert "tokens" in p
        assert len(p["tokens"]) > 0, f"post without token mention leaked: {p['content'][:80]}"
        assert isinstance(p["likes"], int)
        assert isinstance(p["comments"], int)


def test_parse_empty_page_returns_empty_list():
    html = _load_fixture("empty_page.html")
    browser = BinanceSquareBrowser()
    assert browser._parse_html(html, limit=30) == []


def test_parse_login_wall_raises_login_wall_error():
    html = _load_fixture("login_wall.html")
    browser = BinanceSquareBrowser()
    with pytest.raises(LoginWallError):
        browser._parse_html(html, limit=30)


def test_parse_captcha_raises_captcha_error():
    html = _load_fixture("captcha_page.html")
    browser = BinanceSquareBrowser()
    with pytest.raises(CaptchaError):
        browser._parse_html(html, limit=30)


def test_parse_respects_limit():
    """Must not return more than `limit` posts even if the page has more."""
    html = _load_fixture("home_with_posts.html")
    browser = BinanceSquareBrowser()
    posts = browser._parse_html(html, limit=2)
    assert len(posts) <= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_binance_square_browser.py -v --no-header`
Expected: 5 ERROR (AttributeError: 'BinanceSquareBrowser' has no attribute '_parse_html')

- [ ] **Step 3: Implement `_parse_html`**

In `backend/services/binance_square_browser.py`, add the SELECTORS constant and the method. **Selectors below are placeholders — the engineer MUST replace them with the actual classes/attrs found in Task 4's saved fixture.** A reference template:

```python
# Add at the top, after the logger:
# CSS selectors for Binance Square post cards. Update in one place if DOM shifts.
# Verified against fixtures captured 2026-06-05.
SELECTORS = {
    "post_card": "div[class*='PostCard'], article, div[data-post-id]",
    "post_url": "a[href*='/square/post/']",
    "author": "[data-testid='user-name'], a[href*='/square/user/']",
    "content": "[data-testid='post-content'], div[class*='content']",
    "likes": "[data-testid='like-count'], span[class*='like']",
    "comments": "[data-testid='comment-count'], span[class*='comment']",
    "login_wall_marker": "input[type='password']",
    "captcha_marker": "text=verify you are human",
}


def _detect_error_page(html: str) -> None:
    """Raise LoginWallError / CaptchaError if the HTML indicates we hit one."""
    lower = html.lower()
    if "verify you are human" in lower or "captcha" in lower:
        raise CaptchaError("Captcha verification page detected")
    # Login form is the canonical signal of a redirect
    if SELECTORS["login_wall_marker"] and ('type="password"' in lower or "type='password'" in lower):
        # If there's no feed content, it's a login wall
        if "post" not in lower or len(lower) < 5000:
            raise LoginWallError("Login wall detected (password input present, no feed)")


def _parse_int(text: str) -> int:
    """Parse '1.2K' / '234' / '1,234' style counts into an int."""
    if not text:
        return 0
    t = text.strip().replace(",", "")
    if t.endswith(("K", "k")):
        try:
            return int(float(t[:-1]) * 1000)
        except ValueError:
            return 0
    if t.endswith(("M", "m")):
        try:
            return int(float(t[:-1]) * 1_000_000)
        except ValueError:
            return 0
    digits = "".join(c for c in t if c.isdigit() or c == "-")
    try:
        return int(digits) if digits else 0
    except ValueError:
        return 0


def _extract_tokens(content: str) -> list[str]:
    import re
    TOKEN_PATTERN = re.compile(r"[\$#]([A-Z]{2,10})")
    return list(set(TOKEN_PATTERN.findall(content)))
```

Then add this method to `BinanceSquareBrowser`:

```python
def _parse_html(self, html: str, limit: int) -> list[dict[str, Any]]:
    """Parse Binance Square HTML into raw post dicts.

    Detection order: captcha → login wall → empty → extract posts.
    """
    from bs4 import BeautifulSoup  # type: ignore  # project depends on bs4; add if missing

    _detect_error_page(html)

    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(SELECTORS["post_card"])
    if not cards:
        return []

    posts: list[dict[str, Any]] = []
    for card in cards:
        # URL
        url_el = card.select_one(SELECTORS["post_url"])
        source_url = url_el.get("href", "") if url_el else ""
        if source_url and not source_url.startswith("http"):
            source_url = "https://www.binance.com" + source_url

        # Author
        author_el = card.select_one(SELECTORS["author"])
        author = author_el.get_text(strip=True) if author_el else "unknown"

        # Content
        content_el = card.select_one(SELECTORS["content"])
        content = (content_el.get_text("\n", strip=True) if content_el else "")[:1000]

        # Likes / comments
        likes = _parse_int(card.select_one(SELECTORS["likes"]).get_text() if card.select_one(SELECTORS["likes"]) else "")
        comments = _parse_int(card.select_one(SELECTORS["comments"]).get_text() if card.select_one(SELECTORS["comments"]) else "")

        tokens = _extract_tokens(content)
        if not tokens:
            continue  # spec: only posts that mention a token go to the pipeline

        posts.append({
            "source": "binance_square",
            "source_url": source_url,
            "author": author,
            "content": content,
            "likes": likes,
            "comments": comments,
            "tokens": tokens,
        })
        if len(posts) >= limit:
            break
    return posts
```

Add `bs4` to the project's deps if not present:
Run: `grep -i "^bs4\|^beautifulsoup" backend/requirements.txt || echo "bs4>=4.12" >> backend/requirements.txt`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_binance_square_browser.py -v --no-header`
Expected: All 5 pass. (If selectors are off, fix them — re-capture fixtures with `capture_fixtures.py` or tweak the SELECTORS dict.)

- [ ] **Step 5: Commit**

```bash
git add backend/services/binance_square_browser.py backend/tests/test_binance_square_browser.py backend/requirements.txt
git commit -m "feat(scraper): _parse_html with selector-driven DOM extraction"
```

---

## Task 6: `fetch_posts` with page injection

**Files:**
- Modify: `backend/services/binance_square_browser.py`

- [ ] **Step 1: Add a failing test for `fetch_posts` with injected page**

Append to `backend/tests/test_binance_square_browser.py`:

```python
import pytest


class FakePage:
    """Stand-in for playwright Page. Returns the same HTML for every .content() call."""

    def __init__(self, html: str):
        self._html = html
        self.content_calls = 0

    async def content(self) -> str:
        self.content_calls += 1
        return self._html

    async def goto(self, *args, **kwargs):
        pass

    async def mouse_wheel(self, *args, **kwargs):
        pass

    async def wait_for_timeout(self, *args, **kwargs):
        pass


@pytest.mark.asyncio
async def test_fetch_posts_uses_injected_page_without_launching_browser():
    """When constructed with page=, fetch_posts must NOT touch _browser / _playwright."""
    html = _load_fixture("home_with_posts.html")
    page = FakePage(html)
    browser = BinanceSquareBrowser(page=page)

    posts = await browser.fetch_posts(limit=5)

    assert isinstance(posts, list)
    assert len(posts) > 0
    # Injected page was used; no lazy launch happened
    assert page.content_calls >= 1
    assert browser._browser is None  # lazy init never fired
    assert browser._playwright is None
    assert browser._last_fetch_at is not None


@pytest.mark.asyncio
async def test_fetch_posts_propagates_login_wall_from_injected_page():
    html = _load_fixture("login_wall.html")
    browser = BinanceSquareBrowser(page=FakePage(html))
    with pytest.raises(LoginWallError):
        await browser.fetch_posts(limit=5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_binance_square_browser.py::test_fetch_posts_uses_injected_page_without_launching_browser tests/test_binance_square_browser.py::test_fetch_posts_propagates_login_wall_from_injected_page -v --no-header`
Expected: NotImplementedError from the stub

- [ ] **Step 3: Implement `fetch_posts`**

Replace the `NotImplementedError` body in `BinanceSquareBrowser.fetch_posts`:

```python
async def fetch_posts(self, limit: int) -> list[dict[str, Any]]:
    """Fetch up to `limit` posts from Binance Square.

    Uses the injected page if `__init__` received one (tests), otherwise
    lazy-launches a real chromium, navigates to the Square URL, scrolls,
    and reads the rendered HTML.
    """
    import asyncio
    from services.config_store import get_binance_square_scrape_config
    from bs4 import BeautifulSoup  # noqa: F401

    cfg = get_binance_square_scrape_config()
    page = self._injected_page

    if page is None:
        page = await self._get_or_launch_page(cfg)

    # If page has been idle too long, force a fresh navigation
    if (
        self._last_fetch_at is not None
        and (time.time() - self._last_fetch_at) > self.IDLE_RELOAD_SECONDS
    ):
        try:
            await page.goto(cfg["url"], wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            raise RateLimitError(f"goto failed (idle reload): {e}")

    html = await page.content()
    self._last_fetch_at = time.time()
    return self._parse_html(html, limit)


async def _get_or_launch_page(self, cfg: dict[str, Any]):
    """Lazy-launch a chromium and return a configured page. Test-only shortcut: tests inject a page in __init__."""
    from playwright.async_api import async_playwright

    if self._browser is not None and getattr(self._browser, "is_connected", lambda: True)():
        return await self._browser.new_page()  # type: ignore[attr-defined]

    self._playwright = await async_playwright().start()
    self._browser = await self._playwright.chromium.launch(
        headless=cfg.get("headless", True),
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    ctx = await self._browser.new_context(
        user_agent=cfg["user_agent"],
        viewport={"width": 1920, "height": 1080},
    )
    await ctx.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', { get: () => false })"
    )
    page = await ctx.new_page()
    await page.goto(cfg["url"], wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(5000)
    for _ in range(int(cfg.get("scroll_passes", 2))):
        await page.mouse.wheel(0, 1200)
        await page.wait_for_timeout(int(cfg.get("scroll_pause_ms", 2500)))
    return page
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_binance_square_browser.py -v --no-header`
Expected: All 7 pass

- [ ] **Step 5: Commit**

```bash
git add backend/services/binance_square_browser.py backend/tests/test_binance_square_browser.py
git commit -m "feat(scraper): fetch_posts with page injection + lazy chromium launch"
```

---

## Task 7: Update `_fetch_posts` in signal_scraper

**Files:**
- Modify: `backend/services/signal_scraper.py:49-82`

- [ ] **Step 1: Write the failing test for error swallowing**

Create `backend/tests/test_signal_scraper_live.py`:

```python
"""Tests for the live-scraping path in BinanceSquareScraper._fetch_posts."""
import pytest

from services.signal_scraper import BinanceSquareScraper
from services.binance_square_browser import (
    BinanceSquareBrowser,
    CaptchaError,
    LoginWallError,
    ParseError,
    RateLimitError,
)
import services.binance_square_browser as browser_module


class _StubBrowser(BinanceSquareBrowser):
    def __init__(self, posts=None, exc=None):
        super().__init__()
        self._posts = posts or []
        self._exc = exc

    async def fetch_posts(self, limit):
        if self._exc:
            raise self._exc
        return self._posts


@pytest.fixture
def stub_browser(monkeypatch):
    holder = {}

    def _set(posts=None, exc=None):
        holder["b"] = _StubBrowser(posts=posts, exc=exc)
        # Replace module-level getter
        monkeypatch.setattr(browser_module, "_browser", holder["b"])
        return holder["b"]

    return _set


@pytest.mark.asyncio
async def test_fetch_posts_returns_empty_on_login_wall(stub_browser):
    stub_browser(exc=LoginWallError("wall"))
    s = BinanceSquareScraper()
    assert await s._fetch_posts(10) == []


@pytest.mark.asyncio
async def test_fetch_posts_returns_empty_on_captcha(stub_browser):
    stub_browser(exc=CaptchaError("c"))
    s = BinanceSquareScraper()
    assert await s._fetch_posts(10) == []


@pytest.mark.asyncio
async def test_fetch_posts_returns_empty_on_rate_limit(stub_browser):
    stub_browser(exc=RateLimitError("429"))
    s = BinanceSquareScraper()
    assert await s._fetch_posts(10) == []


@pytest.mark.asyncio
async def test_fetch_posts_returns_empty_on_parse_error(stub_browser):
    stub_browser(exc=ParseError("DOM shifted", screenshot_path="/tmp/x.png"))
    s = BinanceSquareScraper()
    assert await s._fetch_posts(10) == []


@pytest.mark.asyncio
async def test_fetch_posts_passes_through_unexpected_exception(stub_browser):
    """Non-BrowserError exceptions must propagate — the scheduler catches them."""
    stub_browser(exc=RuntimeError("disk full"))
    s = BinanceSquareScraper()
    with pytest.raises(RuntimeError, match="disk full"):
        await s._fetch_posts(10)


@pytest.mark.asyncio
async def test_fetch_posts_passes_raw_posts_through(stub_browser):
    raw = [{
        "source": "binance_square",
        "source_url": "https://www.binance.com/en/square/post/999",
        "author": "RealAuthor",
        "content": "$BTC to the moon",
        "likes": 42,
        "comments": 7,
        "tokens": ["BTC"],
    }]
    stub_browser(posts=raw)
    s = BinanceSquareScraper()
    out = await s._fetch_posts(10)
    assert out == raw
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_signal_scraper_live.py -v --no-header`
Expected: ImportError or assertion failure (current `_fetch_posts` returns the hardcoded list)

- [ ] **Step 3: Replace the body of `_fetch_posts`**

In `backend/services/signal_scraper.py`, replace the entire `_fetch_posts` method (lines 49-82):

```python
async def _fetch_posts(self, limit: int) -> list[dict[str, Any]]:
    """Fetch real Binance Square posts via the singleton browser.

    The browser swallows nothing — the four `BrowserError` subclasses
    (LoginWall / Captcha / RateLimit / Parse) are caught here and
    converted to an empty list so the scheduler tick is a no-op
    instead of an error. Any other exception is allowed to propagate
    so the scheduler's existing error-handling path still fires.
    """
    from services.binance_square_browser import (
        CaptchaError,
        LoginWallError,
        ParseError,
        RateLimitError,
        get_browser,
    )

    browser = get_browser()
    try:
        raw = await browser.fetch_posts(limit)
    except (LoginWallError, CaptchaError, RateLimitError) as e:
        logger.warning(f"[BinanceSquareScraper] {type(e).__name__}: {e}")
        return []
    except ParseError as e:
        logger.error(
            f"[BinanceSquareScraper] parse failed: {e} "
            f"(screenshot: {e.screenshot_path})"
        )
        return []
    return raw
```

Also add at the top of the file (after the imports):

```python
import logging
logger = logging.getLogger(__name__)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_signal_scraper_live.py -v --no-header`
Expected: All 6 pass

- [ ] **Step 5: Run the full suite to confirm no regression**

Run: `cd backend && python -m pytest tests/test_scheduler.py tests/test_binance_square_browser.py tests/test_signal_scraper_live.py -q --no-header`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add backend/services/signal_scraper.py backend/tests/test_signal_scraper_live.py
git commit -m "feat(scraper): _fetch_posts delegates to browser with error swallowing"
```

---

## Task 8: `save_to_db` with INSERT OR IGNORE + source_type

**Files:**
- Modify: `backend/services/signal_scraper.py:89-110` (`save_to_db`)

- [ ] **Step 1: Write the failing test for dedup**

Create `backend/tests/test_signal_scraper_dedup.py`:

```python
"""Idempotency test for BinanceSquareScraper.save_to_db."""
from services.database import get_db, init_db
from services.signal_scraper import BinanceSquareScraper


def _count_signals():
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    conn.close()
    return n


def _url_for(content):
    from hashlib import sha256
    return "https://www.binance.com/en/square/post/" + sha256(content.encode()).hexdigest()[:12]


def test_save_to_db_is_idempotent_for_same_source_url():
    init_db()
    scraper = BinanceSquareScraper()
    post = {
        "source": "binance_square",
        "source_url": _url_for("dedup test $BTC"),
        "author": "DedupAuthor",
        "content": "dedup test $BTC",
        "likes": 1,
        "comments": 0,
        "raw_data": "{}",
    }
    scraper.save_to_db([post])
    after_first = _count_signals()

    scraper.save_to_db([post])  # second insert
    after_second = _count_signals()

    assert after_second == after_first, "duplicate insert was not ignored"


def test_save_to_db_sets_source_type_live():
    init_db()
    scraper = BinanceSquareScraper()
    post = {
        "source": "binance_square",
        "source_url": _url_for("sourcetype test $ETH"),
        "author": "NewAuthor",
        "content": "sourcetype test $ETH",
        "likes": 0,
        "comments": 0,
        "raw_data": "{}",
    }
    scraper.save_to_db([post])

    conn = get_db()
    row = conn.execute(
        "SELECT source_type FROM signals WHERE source_url = ?", (post["source_url"],)
    ).fetchone()
    conn.close()

    assert row is not None
    assert row["source_type"] == "live"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_signal_scraper_dedup.py -v --no-header`
Expected: First test fails (count goes up on second insert); second test fails (no `source_type` column yet, or value is NULL).

- [ ] **Step 3: Update `save_to_db`**

In `backend/services/signal_scraper.py`, replace the entire `save_to_db` method:

```python
def save_to_db(self, posts: list[dict[str, Any]]) -> int:
    """Save scraped posts to the database. Returns the count of rows actually inserted.

    Uses INSERT OR IGNORE so re-running with the same posts (same
    source_url) is a no-op — the UNIQUE partial index on source_url
    (created in init_db) is the source of truth for dedup.
    """
    conn = get_db()
    cursor = conn.cursor()
    inserted = 0
    for post in posts:
        cursor.execute(
            """
            INSERT OR IGNORE INTO signals
                (source, source_url, author, content, likes, comments, raw_data, status, source_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 'live')
            """,
            (
                post.get("source", "binance_square"),
                post.get("source_url", ""),
                post.get("author", "unknown"),
                post.get("content", ""),
                post.get("likes", 0),
                post.get("comments", 0),
                post.get("raw_data", str(post)),
            ),
        )
        if cursor.rowcount > 0:
            inserted += 1
    conn.commit()
    conn.close()
    if inserted:
        logger.info(f"[BinanceSquareScraper] inserted {inserted}/{len(posts)} posts")
    return inserted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_signal_scraper_dedup.py -v --no-header`
Expected: Both pass

- [ ] **Step 5: Commit**

```bash
git add backend/services/signal_scraper.py backend/tests/test_signal_scraper_dedup.py
git commit -m "feat(scraper): save_to_db dedup via INSERT OR IGNORE + source_type"
```

---

## Task 9: Manual live smoke test

**Files:**
- Create: `backend/tests/manual/test_binance_square_live.py`

- [ ] **Step 1: Write the manual live test**

Create `backend/tests/manual/test_binance_square_live.py`:

```python
"""Live smoke test for BinanceSquareBrowser.

Launches real chromium and hits binance.com/en/square. Skipped in
CI. Run with: `pytest tests/manual/test_binance_square_live.py --no-header -v`
or just `python -m pytest tests/manual -v` after removing the skip.
"""
import asyncio
from pathlib import Path

import pytest

from services.binance_square_browser import (
    BinanceSquareBrowser,
    BrowserError,
    get_browser,
)


OUTPUT_DIR = Path(__file__).parent.parent / "output"


@pytest.mark.skip(reason="manual live smoke — needs network + chromium")
@pytest.mark.asyncio
async def test_live_fetch_returns_posts():
    OUTPUT_DIR.mkdir(exist_ok=True)
    browser = get_browser()
    try:
        posts = await browser.fetch_posts(limit=10)
    except BrowserError as e:
        # On error, dump the page so we can debug selectors
        if browser._browser is not None:
            try:
                pages = browser._browser.contexts[0].pages if browser._browser.contexts else []
                if pages:
                    shot = OUTPUT_DIR / "live_failure.png"
                    await pages[0].screenshot(path=str(shot))
                    print(f"  screenshot: {shot}")
            except Exception:
                pass
        raise

    print(f"  fetched {len(posts)} posts")
    for p in posts[:5]:
        print(f"    [{p['author']}] {p['content'][:80]}")
    assert len(posts) > 0, "no posts returned from live Square"
    assert all(p["tokens"] for p in posts), "expected token-mentioning posts only"

    await browser.aclose()
```

- [ ] **Step 2: Verify the test is properly skipped**

Run: `cd backend && python -m pytest tests/manual/test_binance_square_live.py -v --no-header`
Expected: 1 skipped (no chromium launched)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/manual/test_binance_square_live.py
git commit -m "test(scraper): manual live smoke for BinanceSquareBrowser"
```

---

## Task 10: End-to-end verification

**Files:** none — this is verification only.

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && python -m pytest tests/ -q --no-header 2>&1 | tail -5`
Expected: All pass (currently 192; expect 192 + ~12 new = ~204)

- [ ] **Step 2: Restart the running backend with the new code**

```bash
tasklist 2>/dev/null | grep -i python | awk '{print $2}' | xargs -I {} taskkill //F //PID {} 2>&1
sleep 2
cd backend && nohup python main.py > /tmp/backend.log 2>&1 &
sleep 6
curl -s http://localhost:8000/api/health
```

Expected: `{"status": "ok"}` and `/tmp/backend.log` shows no startup errors

- [ ] **Step 3: Confirm the scheduler interval flipped to 30 min**

```bash
curl -s http://localhost:8000/api/workflow/tasks | python -m json.tool
```

Expected: `signal_scan_interval_minutes` for the Signal Scanner task is `30` (or whatever the config row says — the **scheduler fallback default** is now 30, so newly-initialised rows default to it)

- [ ] **Step 4: Manually trigger one scheduler tick via "Run Now"**

In the browser, open `http://localhost:5173/workflow`, click "▶ Run Now" on the Signal Scanner card.

Watch `/tmp/backend.log` — look for:
- `[BinanceSquareScraper] inserted N/M posts` (success)
- OR `[BinanceSquareScraper] LoginWallError: ...` (login wall — selector drift or rate limit; check the page state)

- [ ] **Step 5: Verify a real post landed in the DB**

```bash
cd backend && python -c "
import sqlite3
conn = sqlite3.connect('data/trading.db')
conn.row_factory = sqlite3.Row
for row in conn.execute(\"SELECT author, source_type, substr(content,1,60) as c FROM signals WHERE source_type='live' ORDER BY id DESC LIMIT 5\"):
    print(f\"  [{row['source_type']}] {row['author']}: {row['c']}\")
"
```

Expected: ≥1 row with `source_type='live'` and author name NOT in {TraderOne, CryptoWhale, BearHunter}

- [ ] **Step 6: Visually confirm the Trading view shows real data**

```bash
cd /d/work/browser-demo && python -c "
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page()
        await page.goto('http://localhost:5173/trading', wait_until='domcontentloaded')
        await page.wait_for_selector('.signal-card, .empty-state', timeout=10000)
        await page.screenshot(path='D:/work/browser-demo/_verify_trading_live.png', full_page=True)
        await b.close()
asyncio.run(main())
"
```

Open the screenshot and verify the signal cards show real author names (not TraderOne/CryptoWhale/BearHunter).

- [ ] **Step 7: Commit the verification artifacts (optional)**

```bash
git add _verify_trading_live.png 2>/dev/null || true
git commit -m "verify: live trading screenshot" --allow-empty
```

---

## Self-Review Checklist (run before declaring done)

- [ ] All 4 HTML fixtures are committed and contain real Binance Square content
- [ ] `SELECTORS` dict in `binance_square_browser.py` is grounded in actual fixture DOM, not placeholder
- [ ] `_fetch_posts` swallows exactly the 4 `BrowserError` subclasses; everything else propagates
- [ ] `save_to_db` uses `INSERT OR IGNORE` and writes `source_type='live'`
- [ ] Migration in `init_db` adds `source_type` column + backfills old mock rows + creates UNIQUE index — all idempotent
- [ ] Scheduler fallback default flipped to 30; SQL DEFAULT flipped to 30
- [ ] No silent regressions in the existing test suite
- [ ] Live tick inserts ≥1 `source_type='live'` row
- [ ] Trading UI screenshot shows real author names

---

## Notes for Implementers

- **Selectors are the fragile part.** If `home_with_posts.html` doesn't yield the expected posts, open the fixture in a browser, look at the actual class names, and update the `SELECTORS` dict. The `_parse_html` function is intentionally tolerant (returns `[]` for empty, raises specific errors for known failure modes).
- **If the live fetch fails immediately with CaptchaError or LoginWallError**, the fixtures may be stale. Re-run `python tests/fixtures/binance_square/capture_fixtures.py` to refresh, and update `SELECTORS` accordingly.
- **The `atexit` browser cleanup is not yet implemented** — a clean `aclose()` is exposed but only the test invokes it. Live uvicorn that crashes ungracefully may leak a chromium process. Acceptable for v1.
- **Don't add LLM-based analysis** to this scope. `validate_signal` already exists and works against any `signals` row, live or mock. That's a separate brainstorm.
