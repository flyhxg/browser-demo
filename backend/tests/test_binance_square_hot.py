"""Tests for BinanceSquareScraper.scrape_hot()."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest


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
    from services.signal_scraper import BinanceSquareScraper

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
    from services.signal_scraper import BinanceSquareScraper

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
    from services.signal_scraper import BinanceSquareScraper

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
