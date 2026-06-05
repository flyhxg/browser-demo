"""Idempotency test for BinanceSquareScraper.save_to_db."""
import asyncio
from hashlib import sha256
from pathlib import Path

import services.binance_square_browser as browser_module
from services.binance_square_browser import BinanceSquareBrowser
from services.database import get_db, init_db
from services.signal_scraper import BinanceSquareScraper


def _count_signals():
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    conn.close()
    return n


def _url_for(content):
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


# --- Integration: scrape() → save_to_db() end-to-end ---


class _FakePage:
    """Stand-in for playwright Page returning a fixed HTML blob."""

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


def _load_fixture(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / "binance_square" / name).read_text(encoding="utf-8")


def test_scrape_to_save_to_db_round_trip_has_non_empty_source_url(tmp_path, monkeypatch):
    """scrape() must propagate source_url from browser → save_to_db.

    Regression test: scrape() previously read the wrong key ("url" vs
    "source_url") and silently inserted empty source_url values, which
    bypassed the UNIQUE INDEX dedup and produced 17 duplicate rows per
    scheduler tick. The unit tests missed this because they hand-built
    the post dicts; this test exercises the real browser → scraper →
    DB chain.

    Uses a tmp DB so the assertions about "first save inserts N rows,
    second save inserts 0" hold regardless of what's in the live DB.
    """
    import services.database as db_module

    db_file = tmp_path / "scrape_integration.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_file)
    init_db()

    html = _load_fixture("home_with_posts.html")
    page = _FakePage(html)
    fixture_browser = BinanceSquareBrowser(page=page)

    # Install the fixture-backed browser as the module-level singleton.
    original = browser_module._browser
    browser_module._browser = fixture_browser
    try:
        scraper = BinanceSquareScraper()
        posts = asyncio.run(scraper.scrape(limit=5))
        assert posts, "scrape() returned no posts"
        for p in posts:
            assert p.get("source_url"), (
                f"source_url is empty for post: author={p.get('author')!r} "
                f"content={p.get('content', '')[:60]!r}"
            )

        # First save: all should insert.
        before = _count_signals()
        inserted_first = scraper.save_to_db(posts)
        after_first = _count_signals()
        assert inserted_first == len(posts), (
            f"first save: expected {len(posts)} inserts, got {inserted_first}"
        )
        assert after_first - before == len(posts)

        # Second save of the same posts: dedup via UNIQUE INDEX must
        # reject every row. The original bug inserted them all again.
        inserted_second = scraper.save_to_db(posts)
        after_second = _count_signals()
        assert inserted_second == 0, (
            f"dedup broken: {inserted_second} duplicate rows inserted on re-save"
        )
        assert after_second == after_first, (
            f"row count grew on re-save: {after_first} -> {after_second}"
        )
    finally:
        browser_module._browser = original
