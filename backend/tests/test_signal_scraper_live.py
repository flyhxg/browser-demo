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
    """Return a setter that installs a stubbed browser singleton for the test."""
    def _set(posts=None, exc=None):
        b = _StubBrowser(posts=posts, exc=exc)
        monkeypatch.setattr(browser_module, "_browser", b)
        return b

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
