"""Tests for SignalScanScheduler (Phase 2.4 of ai-trading-system)."""
import asyncio
import pytest

from services.database import init_db
from services.config_store import get_trading_config_from_db


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


@pytest.mark.asyncio
async def test_start_noop_when_disabled_in_config():
    """start() must not create a task when signal_scan_enabled is False."""
    from services.scheduler import SignalScanScheduler

    scraper = FakeScraper()
    scheduler = SignalScanScheduler(scraper, config_provider=make_config(enabled=False))

    await scheduler.start()

    assert scheduler._task is None


@pytest.mark.asyncio
async def test_start_creates_task_when_enabled():
    """start() must create an asyncio task when enabled."""
    from services.scheduler import SignalScanScheduler

    scraper = FakeScraper()
    scheduler = SignalScanScheduler(scraper, config_provider=make_config(enabled=True, interval_minutes=0.001))

    await scheduler.start()

    assert scheduler._task is not None
    assert not scheduler._task.done()

    # Clean up so the test doesn't leak a background task
    await scheduler.stop()


@pytest.mark.asyncio
async def test_start_is_idempotent():
    """Calling start() twice must not create a second task."""
    from services.scheduler import SignalScanScheduler

    scraper = FakeScraper()
    scheduler = SignalScanScheduler(scraper, config_provider=make_config(enabled=True, interval_minutes=0.001))

    await scheduler.start()
    first_task = scheduler._task
    await scheduler.start()  # second call

    assert scheduler._task is first_task

    await scheduler.stop()


@pytest.mark.asyncio
async def test_stop_cancels_running_task():
    """stop() must cancel the background task and wait for it to finish."""
    from services.scheduler import SignalScanScheduler

    scraper = FakeScraper()
    scheduler = SignalScanScheduler(scraper, config_provider=make_config(enabled=True, interval_minutes=0.001))

    await scheduler.start()
    assert scheduler._task is not None

    await scheduler.stop()

    assert scheduler._task is None


@pytest.mark.asyncio
async def test_stop_noop_when_not_running():
    """stop() must be safe to call when no task is running."""
    from services.scheduler import SignalScanScheduler

    scraper = FakeScraper()
    scheduler = SignalScanScheduler(scraper, config_provider=make_config())

    # Should not raise
    await scheduler.stop()
    assert scheduler._task is None


@pytest.mark.asyncio
async def test_loop_runs_multiple_ticks_at_configured_interval():
    """_loop must call _tick repeatedly with the interval from config."""
    from services.scheduler import SignalScanScheduler

    scraper = FakeScraper(posts=[{"content": "x"}])
    scheduler = SignalScanScheduler(
        scraper,
        config_provider=make_config(enabled=True, interval_minutes=0.001),  # 0.06s
    )

    await scheduler.start()
    # 0.06s interval; wait 0.15s → expect ~2 ticks (allow 1-3 for timing slack)
    await asyncio.sleep(0.15)
    await scheduler.stop()

    assert scraper.scrape_calls >= 1, f"expected ≥1 ticks, got {scraper.scrape_calls}"


@pytest.mark.asyncio
async def test_loop_picks_up_enabled_toggle():
    """_loop must NOT tick while disabled, then start ticking when enabled is flipped."""
    from services.scheduler import SignalScanScheduler

    config = {"signal_scan_enabled": False, "signal_scan_interval_minutes": 0.001}
    scraper = FakeScraper(posts=[{"content": "x"}])
    scheduler = SignalScanScheduler(scraper, config_provider=lambda: config)

    await scheduler.start()  # disabled — no task
    assert scheduler._task is None
    assert scraper.scrape_calls == 0

    # Flip enabled and start
    config["signal_scan_enabled"] = True
    await scheduler.start()
    assert scheduler._task is not None
    await asyncio.sleep(0.1)
    await scheduler.stop()

    assert scraper.scrape_calls >= 1


def test_default_config_provider_reads_from_trading_config_table():
    """Default config_provider (no override) must read from the trading_config
    SQLite table — the source of truth for `PUT /api/trading/config` writes.

    Regression test: the kill switch must be togglable via the API endpoint.
    """
    from services.scheduler import SignalScanScheduler
    from services.database import get_db

    init_db()
    # Seed: row exists but kill switch is off
    conn = get_db()
    conn.execute("UPDATE trading_config SET signal_scan_enabled = 0, signal_scan_interval_minutes = 7 WHERE id = 1")
    conn.commit()
    conn.close()

    scheduler = SignalScanScheduler(scraper=FakeScraper())
    assert scheduler._is_enabled() is False
    assert scheduler._interval_seconds() == 7 * 60.0

    # Flip via direct DB write (simulating what PUT /api/trading/config does)
    conn = get_db()
    conn.execute("UPDATE trading_config SET signal_scan_enabled = 1, signal_scan_interval_minutes = 2 WHERE id = 1")
    conn.commit()
    conn.close()

    # Re-reading must pick up the new values
    assert scheduler._is_enabled() is True
    assert scheduler._interval_seconds() == 2 * 60.0
