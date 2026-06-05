"""Unit tests for BinanceSquareBrowser. All offline via HTML fixtures."""
import pytest

from services.binance_square_browser import (
    BinanceSquareBrowser,
    CaptchaError,
    LoginWallError,
    ParseError,
    RateLimitError,
)


def _load_fixture(name: str) -> str:
    from pathlib import Path
    return (Path(__file__).parent / "fixtures" / "binance_square" / name).read_text(encoding="utf-8")


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
    html = _load_fixture("synthetic_empty_page.html")
    browser = BinanceSquareBrowser()
    assert browser._parse_html(html, limit=30) == []


def test_parse_login_wall_raises_login_wall_error():
    html = _load_fixture("synthetic_login_wall.html")
    browser = BinanceSquareBrowser()
    with pytest.raises(LoginWallError):
        browser._parse_html(html, limit=30)


def test_parse_captcha_raises_captcha_error():
    html = _load_fixture("synthetic_captcha.html")
    browser = BinanceSquareBrowser()
    with pytest.raises(CaptchaError):
        browser._parse_html(html, limit=30)


def test_parse_respects_limit():
    """Must not return more than `limit` posts even if the page has more."""
    html = _load_fixture("home_with_posts.html")
    browser = BinanceSquareBrowser()
    posts = browser._parse_html(html, limit=2)
    assert len(posts) <= 2


from services.binance_square_browser import (
    _extract_tokens,
    _parse_int,
)


def test_parse_int_handles_k_suffix():
    assert _parse_int("1.2K") == 1200
    assert _parse_int("1k") == 1000


def test_parse_int_handles_m_suffix():
    assert _parse_int("1.5M") == 1_500_000
    assert _parse_int("1m") == 1_000_000


def test_parse_int_handles_plain_and_comma_separated():
    assert _parse_int("234") == 234
    assert _parse_int("1,234") == 1234
    assert _parse_int("1,234,567") == 1234567


def test_parse_int_handles_empty_and_invalid():
    assert _parse_int("") == 0
    assert _parse_int("abc") == 0
    assert _parse_int(None) == 0  # type: ignore[arg-type]


def test_extract_tokens_finds_dollar_and_hash_mentions():
    assert _extract_tokens("$BTC to the moon") == ["BTC"]
    assert _extract_tokens("Bullish on $ETH and #SOL") == ["ETH", "SOL"]


def test_extract_tokens_dedupes_and_filters_by_length():
    # Dedup
    assert _extract_tokens("$BTC $BTC") == ["BTC"]
    # Below 2 chars: excluded
    assert _extract_tokens("$B") == []
    # 10 chars: included
    assert _extract_tokens("$LONGTOKENX") == ["LONGTOKENX"]
    # 11 chars: excluded
    assert _extract_tokens("$TOOLONGTOKEN") == []


def test_extract_tokens_handles_lowercase_as_no_match():
    """Lowercase symbols are NOT token mentions per the spec regex."""
    assert _extract_tokens("btc to the moon") == []
    assert _extract_tokens("$btc") == []


# --- fetch_posts with injected page (Task 6) ---


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
    assert page.content_calls >= 1
    assert browser._browser is None
    assert browser._playwright is None
    assert browser._last_fetch_at is not None


@pytest.mark.asyncio
async def test_fetch_posts_propagates_login_wall_from_injected_page():
    html = _load_fixture("synthetic_login_wall.html")
    browser = BinanceSquareBrowser(page=FakePage(html))
    with pytest.raises(LoginWallError):
        await browser.fetch_posts(limit=5)
