"""Idempotency test for BinanceSquareScraper.save_to_db."""
from hashlib import sha256

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
