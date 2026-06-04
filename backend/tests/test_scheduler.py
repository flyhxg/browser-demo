"""Tests for SignalScanScheduler (Phase 2.4 of ai-trading-system)."""
import asyncio
import pytest


class FakeScraper:
    """Records scrape + save calls; configurable results."""
    def __init__(self, posts=None, scrape_raises=None, save_raises=None):
        self.posts = posts or []
        self.scrape_raises = scrape_raises
        self.save_raises = save_raises
        self.scrape_calls = 0
        self.save_calls: list[list] = []

    async def scrape(self):
        self.scrape_calls += 1
        if self.scrape_raises:
            raise self.scrape_raises
        return self.posts

    def save_to_db(self, posts):
        self.save_calls.append(list(posts))
        if self.save_raises:
            raise self.save_raises


def make_ws():
    """Returns (recorder, broadcaster). recorder is a list of (event, payload) tuples."""
    recorded: list[tuple[str, dict]] = []

    async def broadcast(event: str, payload: dict) -> None:
        recorded.append((event, payload))

    return recorded, broadcast


def make_config(enabled: bool = True, interval_minutes: float = 15) -> callable:
    cfg = {"signal_scan_enabled": enabled, "signal_scan_interval_minutes": interval_minutes}
    return lambda: cfg


@pytest.mark.asyncio
async def test_tick_calls_scraper_and_save():
    """_tick must call scraper.scrape() then scraper.save_to_db() with the posts."""
    from services.scheduler import SignalScanScheduler

    scraper = FakeScraper(posts=[{"source": "x", "content": "$BTC"}])
    scheduler = SignalScanScheduler(scraper, config_provider=make_config())

    await scheduler._tick()

    assert scraper.scrape_calls == 1
    assert scraper.save_calls == [[{"source": "x", "content": "$BTC"}]]
