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
