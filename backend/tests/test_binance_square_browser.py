"""Unit tests for BinanceSquareBrowser. All offline via HTML fixtures."""
from datetime import datetime, timedelta

import pytest

from services.binance_square_browser import (
    BinanceSquareBrowser,
    CaptchaError,
    LoginWallError,
    ParseError,
    RateLimitError,
    _parse_relative_time,
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


# --- _parse_relative_time unit tests ---


def test_parse_relative_time_minutes():
    now = datetime(2026, 6, 5, 12, 0, 0)
    assert _parse_relative_time("5m", now) == now - timedelta(minutes=5)
    assert _parse_relative_time("30m", now) == now - timedelta(minutes=30)


def test_parse_relative_time_hours():
    now = datetime(2026, 6, 5, 12, 0, 0)
    assert _parse_relative_time("19h", now) == now - timedelta(hours=19)
    assert _parse_relative_time("1h", now) == now - timedelta(hours=1)


def test_parse_relative_time_days():
    now = datetime(2026, 6, 5, 12, 0, 0)
    assert _parse_relative_time("1d", now) == now - timedelta(days=1)


def test_parse_relative_time_yesterday():
    now = datetime(2026, 6, 5, 12, 0, 0)
    assert _parse_relative_time("Yesterday", now) == now - timedelta(days=1)


def test_parse_relative_time_just_now():
    now = datetime(2026, 6, 5, 12, 0, 0)
    assert _parse_relative_time("Just now", now) == now
    assert _parse_relative_time("now", now) == now


def test_parse_relative_time_month_day_current_year():
    now = datetime(2026, 6, 5, 12, 0, 0)
    # May 3, 2026 is in the past relative to June 5, 2026
    assert _parse_relative_time("May 3", now) == datetime(2026, 5, 3)


def test_parse_relative_time_month_day_rolls_to_previous_year():
    now = datetime(2026, 1, 15, 12, 0, 0)
    # Dec 25 of "this year" would be 2026-12-25 which is in the future
    # relative to Jan 15, 2026, so it should roll to 2025-12-25
    assert _parse_relative_time("Dec 25", now) == datetime(2025, 12, 25)


def test_parse_relative_time_unparseable_returns_min():
    now = datetime(2026, 6, 5, 12, 0, 0)
    assert _parse_relative_time("", now) == datetime.min
    assert _parse_relative_time("garbage", now) == datetime.min


# --- _parse_html sort order test ---


def test_parse_html_returns_posts_newest_first():
    """Posts must be sorted by created_at descending."""
    html = _load_fixture("home_with_posts.html")
    browser = BinanceSquareBrowser()
    # Pin `now` to a known reference. The fixture has times like "19h" and "Jun 3".
    # We use a "now" close to those so the sort produces a meaningful order.
    now = datetime(2026, 6, 5, 12, 0, 0)
    posts = browser._parse_html(html, limit=30, now=now)
    assert len(posts) >= 2, "need at least 2 posts to test sort order"

    # Each post must have created_at
    for p in posts:
        assert "created_at" in p
        # Sanity: parseable ISO 8601
        datetime.fromisoformat(p["created_at"])

    # Sort order: descending (newest first)
    times = [datetime.fromisoformat(p["created_at"]) for p in posts]
    assert times == sorted(times, reverse=True), (
        f"posts not sorted newest first: first={times[0]}, last={times[-1]}"
    )


def test_parse_html_includes_created_at_field():
    """Each post dict must include the created_at ISO string."""
    html = _load_fixture("home_with_posts.html")
    browser = BinanceSquareBrowser()
    posts = browser._parse_html(html, limit=5, now=datetime(2026, 6, 5, 12, 0, 0))
    assert posts
    for p in posts:
        assert "created_at" in p
        # Should be an ISO string
        assert isinstance(p["created_at"], str)
        # Should be parseable
        datetime.fromisoformat(p["created_at"])
