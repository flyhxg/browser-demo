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


@pytest.mark.asyncio
async def test_tick_broadcasts_when_ws_provided():
    """_tick must call ws_broadcast('signal:new', post) for each post."""
    from services.scheduler import SignalScanScheduler

    posts = [{"content": "a"}, {"content": "b"}]
    scraper = FakeScraper(posts=posts)
    recorded, broadcast = make_ws()
    scheduler = SignalScanScheduler(scraper, config_provider=make_config(), ws_broadcast=broadcast)

    await scheduler._tick()

    assert recorded == [("signal:new", {"content": "a"}), ("signal:new", {"content": "b"})]


@pytest.mark.asyncio
async def test_tick_no_broadcast_when_ws_is_none():
    """_tick must not crash when ws_broadcast is None (default)."""
    from services.scheduler import SignalScanScheduler

    scraper = FakeScraper(posts=[{"content": "a"}])
    scheduler = SignalScanScheduler(scraper, config_provider=make_config())

    await scheduler._tick()  # no exception
    assert scraper.save_calls == [[{"content": "a"}]]


@pytest.mark.asyncio
async def test_tick_noop_on_empty_posts():
    """_tick must not call save_to_db or broadcast when scraper returns []."""
    from services.scheduler import SignalScanScheduler

    scraper = FakeScraper(posts=[])
    recorded, broadcast = make_ws()
    scheduler = SignalScanScheduler(scraper, config_provider=make_config(), ws_broadcast=broadcast)

    await scheduler._tick()

    assert scraper.scrape_calls == 1
    assert scraper.save_calls == []
    assert recorded == []


@pytest.mark.asyncio
async def test_tick_survives_scraper_exception():
    """_tick must swallow scraper exceptions and not propagate them."""
    from services.scheduler import SignalScanScheduler

    scraper = FakeScraper(scrape_raises=RuntimeError("upstream down"))
    scheduler = SignalScanScheduler(scraper, config_provider=make_config())

    # Should NOT raise
    await scheduler._tick()

    assert scraper.scrape_calls == 1
    assert scraper.save_calls == []


@pytest.mark.asyncio
async def test_tick_survives_save_exception():
    """_tick must swallow save_to_db exceptions and not propagate them."""
    from services.scheduler import SignalScanScheduler

    scraper = FakeScraper(posts=[{"content": "x"}], save_raises=RuntimeError("db down"))
    scheduler = SignalScanScheduler(scraper, config_provider=make_config())

    # Should NOT raise
    await scheduler._tick()

    assert scraper.save_calls == [[{"content": "x"}]]


@pytest.mark.asyncio
async def test_tick_survives_ws_broadcast_exception_per_post():
    """A failing broadcast for one post must not stop the next post from broadcasting."""
    from services.scheduler import SignalScanScheduler

    posts = [{"content": "a"}, {"content": "b"}, {"content": "c"}]
    scraper = FakeScraper(posts=posts)
    recorded: list[tuple[str, dict]] = []

    async def flaky_broadcast(event: str, payload: dict) -> None:
        if payload["content"] == "b":
            raise RuntimeError("ws hiccup")
        recorded.append((event, payload))

    scheduler = SignalScanScheduler(scraper, config_provider=make_config(), ws_broadcast=flaky_broadcast)

    await scheduler._tick()

    assert recorded == [("signal:new", {"content": "a"}), ("signal:new", {"content": "c"})]
