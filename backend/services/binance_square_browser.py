"""Long-lived Playwright browser for scraping public Binance Square.

Module-level singleton is the default; tests inject a `page` so they
can run without launching chromium.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

from bs4 import BeautifulSoup

from services.config_store import get_binance_square_scrape_config

logger = logging.getLogger(__name__)


# CSS selectors for Binance Square post cards. Update in one place if DOM shifts.
# Verified against fixtures captured 2026-06-05.
SELECTORS = {
    "post_card": '[class*="FeedBuzzBaseViewRoot"][data-id]',
    "post_url": 'a[href^="/en/square/post/"]',
    "author": 'div.nick-username a.nick',
    "content": 'div.card__description.rich-text',
    "likes": 'div.thumb-up-button.card-function-item span.current',
    "comments": 'div.comments-icon.card-function-item span.current',
    "login_wall_marker": "input[type='password']",
    "captcha_marker": "verify you are human",  # matched case-insensitive
}


# Match $BTC / #ETH style token mentions inside a post body.
# Catches 2-10 uppercase chars after $ or # (so single-letter tokens like $B
# are excluded; long ones like $BITCOINUSD still pass). The negative lookahead
# `(?![A-Z])` ensures we don't take a 10-char prefix out of a longer run
# (e.g. $TOOLONGTOKEN should not match as $TOOLONGTOK).
_TOKEN_PATTERN = re.compile(r"[\$#]([A-Z]{2,10})(?![A-Z])")


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
        """Fetch up to `limit` posts from Binance Square.

        Uses the injected page if `__init__` received one (tests), otherwise
        lazy-launches a real chromium, navigates to the Square URL, scrolls,
        and reads the rendered HTML.
        """
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

    def _parse_html(self, html: str, limit: int) -> list[dict[str, Any]]:
        """Parse Binance Square HTML into raw post dicts.

        Detection order: captcha → login wall → empty → extract posts.
        Posts without a $XXX / #XXX token mention are dropped — the downstream
        pipeline only cares about tokenised signal.
        """
        _detect_error_page(html)

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(SELECTORS["post_card"])
        if not cards:
            return []

        posts: list[dict[str, Any]] = []
        for card in cards:
            # URL — prefer the visible title link
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
            likes_el = card.select_one(SELECTORS["likes"])
            comments_el = card.select_one(SELECTORS["comments"])
            likes = _parse_int(likes_el.get_text() if likes_el else "")
            comments = _parse_int(comments_el.get_text() if comments_el else "")

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


# --- Pure helpers (no instance state) ---


def _detect_error_page(html: str) -> None:
    """Raise CaptchaError / LoginWallError if the HTML indicates we hit one."""
    lower = html.lower()
    if "verify you are human" in lower or "captcha" in lower:
        raise CaptchaError("Captcha verification page detected")
    # Login form is the canonical signal of a redirect
    if "type=\"password\"" in lower or "type='password'" in lower:
        raise LoginWallError("Login wall detected (password input present)")


def _parse_int(text: str) -> int:
    """Parse '1.2K' / '234' / '1,234' / '1.5M' style counts into an int."""
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
    # Sort for deterministic ordering — `set` alone has arbitrary iteration order.
    return sorted(set(_TOKEN_PATTERN.findall(content)))


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
