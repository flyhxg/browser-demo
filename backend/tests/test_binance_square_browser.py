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
