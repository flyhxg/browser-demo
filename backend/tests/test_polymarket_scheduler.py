"""Tests for PolymarketScheduler (workflow integration) + scheduler registry."""
import asyncio
import time

import pytest

from services.database import init_db
from services.scheduler import (
    PolymarketScheduler,
    register,
    get_schedulers,
    get_scheduler,
    _reset_registry,
)


# --- Fakes ---


class FakePoller:
    """Records lifecycle calls; configurable tick behaviour."""

    def __init__(self, refresh_raises=None, poll_raises=None):
        self.refresh_calls = 0
        self.poll_calls = 0
        self.refresh_raises = refresh_raises
        self.poll_raises = poll_raises

    async def _refresh_leaderboard(self):
        self.refresh_calls += 1
        if self.refresh_raises:
            raise self.refresh_raises

    async def _poll_all_trades(self):
        self.poll_calls += 1
        if self.poll_raises:
            raise self.poll_raises

    async def aclose(self):
        pass


class FakeMonitor:
    def __init__(self):
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self):
        self.start_calls += 1

    async def stop(self):
        self.stop_calls += 1


def make_poller_factory(poller=None, monitor=None):
    """Returns (factory_dict, poller, monitor) — call factory_dict["poller"](cfg) etc."""
    poller = poller or FakePoller()
    monitor = monitor or FakeMonitor()
    factory = {
        "poller": lambda cfg: poller,
        "monitor": lambda cfg: monitor,
    }
    return factory, poller, monitor


def make_config(enabled: bool = True, poll_interval: int = 60) -> callable:
    cfg = {"enabled": 1 if enabled else 0, "poll_interval": poll_interval}
    return lambda: cfg


# --- PolymarketScheduler lifecycle ---


@pytest.mark.asyncio
async def test_start_constructs_poller_and_monitor_via_factories():
    """start() must call poller_factory and monitor_factory with the config."""
    factory, poller, monitor = make_poller_factory()
    scheduler = PolymarketScheduler(
        poller_factory=factory["poller"],
        monitor_factory=factory["monitor"],
        config_provider=make_config(),
    )

    await scheduler.start()

    assert monitor.start_calls == 1
    # Poller is constructed but not yet ticked
    assert poller.refresh_calls == 0
    assert poller.poll_calls == 0

    await scheduler.stop()


@pytest.mark.asyncio
async def test_start_runs_scheduler_loop_and_ticks_poller():
    """Background loop must call poller._refresh_leaderboard + _poll_all_trades per tick."""
    factory, poller, _ = make_poller_factory()
    scheduler = PolymarketScheduler(
        poller_factory=factory["poller"],
        monitor_factory=factory["monitor"],
        config_provider=make_config(poll_interval=60),  # seconds; loop uses 60s as min
    )

    # Override interval to 0.05s for a fast test
    scheduler._set_interval_seconds(0.05)
    await scheduler.start()
    await asyncio.sleep(0.18)  # ~3 ticks
    await scheduler.stop()

    # allow slack: between 1-5 ticks
    assert poller.refresh_calls >= 1
    assert poller.poll_calls >= 1
    # refresh and poll counts should match (called together per tick)
    assert poller.refresh_calls == poller.poll_calls


@pytest.mark.asyncio
async def test_start_noop_when_disabled_in_config():
    """start() must not construct poller/monitor when config.enabled is False."""
    factory, poller, monitor = make_poller_factory()
    scheduler = PolymarketScheduler(
        poller_factory=factory["poller"],
        monitor_factory=factory["monitor"],
        config_provider=make_config(enabled=False),
    )

    await scheduler.start()

    assert monitor.start_calls == 0
    assert scheduler._task is None
    assert scheduler._poller is None
    assert scheduler._monitor is None


@pytest.mark.asyncio
async def test_start_is_idempotent():
    """Calling start() twice must not create a second loop task."""
    factory, _, _ = make_poller_factory()
    scheduler = PolymarketScheduler(
        poller_factory=factory["poller"],
        monitor_factory=factory["monitor"],
        config_provider=make_config(poll_interval=60),
    )
    scheduler._set_interval_seconds(0.05)

    await scheduler.start()
    first_task = scheduler._task
    await scheduler.start()  # second call
    assert scheduler._task is first_task

    await scheduler.stop()


@pytest.mark.asyncio
async def test_stop_cancels_task_and_stops_monitor():
    """stop() must cancel the loop and call monitor.stop()."""
    factory, _, monitor = make_poller_factory()
    scheduler = PolymarketScheduler(
        poller_factory=factory["poller"],
        monitor_factory=factory["monitor"],
        config_provider=make_config(poll_interval=60),
    )
    scheduler._set_interval_seconds(0.05)

    await scheduler.start()
    assert scheduler._task is not None

    await scheduler.stop()

    assert scheduler._task is None
    assert monitor.stop_calls == 1
    assert scheduler._poller is None
    assert scheduler._monitor is None


@pytest.mark.asyncio
async def test_stop_noop_when_not_running():
    """stop() must be safe to call when nothing is running."""
    factory, _, monitor = make_poller_factory()
    scheduler = PolymarketScheduler(
        poller_factory=factory["poller"],
        monitor_factory=factory["monitor"],
        config_provider=make_config(enabled=False),
    )

    await scheduler.stop()  # no-op

    assert scheduler._task is None
    assert monitor.stop_calls == 0


@pytest.mark.asyncio
async def test_tick_swallows_poller_exceptions():
    """A failing poller tick must not propagate; loop continues."""
    poller = FakePoller(refresh_raises=RuntimeError("upstream down"))
    factory, _, _ = make_poller_factory(poller=poller)
    scheduler = PolymarketScheduler(
        poller_factory=factory["poller"],
        monitor_factory=factory["monitor"],
        config_provider=make_config(poll_interval=60),
    )
    scheduler._set_interval_seconds(0.05)

    await scheduler.start()
    await asyncio.sleep(0.15)
    await scheduler.stop()

    # Survived multiple ticks despite the error
    assert poller.refresh_calls >= 1


@pytest.mark.asyncio
async def test_tick_updates_last_run_even_on_failure():
    """_tick must update last_run even if poller raises (use try/finally)."""
    poller = FakePoller(poll_raises=RuntimeError("boom"))
    factory, _, _ = make_poller_factory(poller=poller)
    scheduler = PolymarketScheduler(
        poller_factory=factory["poller"],
        monitor_factory=factory["monitor"],
        config_provider=make_config(poll_interval=60),
    )
    scheduler._set_interval_seconds(0.05)

    await scheduler.start()
    await asyncio.sleep(0.1)
    last_run = scheduler._last_run
    assert last_run is not None
    await scheduler.stop()

    # last_run was set despite the failure
    assert last_run is not None


# --- get_status ---


@pytest.mark.asyncio
async def test_get_status_reports_disabled_when_config_off():
    factory, _, _ = make_poller_factory()
    scheduler = PolymarketScheduler(
        poller_factory=factory["poller"],
        monitor_factory=factory["monitor"],
        config_provider=make_config(enabled=False),
    )
    status = scheduler.get_status()
    assert status["id"] == 2
    assert status["name"] == "Polymarket Poller"
    assert status["enabled"] is False
    assert status["running"] is False
    assert status["status"] == "paused"
    assert status["next_run"] is None


@pytest.mark.asyncio
async def test_get_status_reports_running_when_started():
    factory, _, _ = make_poller_factory()
    scheduler = PolymarketScheduler(
        poller_factory=factory["poller"],
        monitor_factory=factory["monitor"],
        config_provider=make_config(enabled=True, poll_interval=60),
    )
    scheduler._set_interval_seconds(0.5)

    await scheduler.start()
    try:
        status = scheduler.get_status()
        assert status["enabled"] is True
        assert status["running"] is True
        assert status["status"] == "running"
        # poll_interval=60s → 1 min in display units
        assert status["interval_minutes"] == 1
        assert status["next_run"] is not None
    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_get_status_interval_minutes_reflects_config():
    """interval_minutes must be poll_interval_seconds // 60."""
    factory, _, _ = make_poller_factory()
    scheduler = PolymarketScheduler(
        poller_factory=factory["poller"],
        monitor_factory=factory["monitor"],
        config_provider=make_config(enabled=True, poll_interval=300),  # 5 min
    )
    status = scheduler.get_status()
    assert status["interval_minutes"] == 5


@pytest.mark.asyncio
async def test_get_status_last_run_set_after_tick():
    factory, _, _ = make_poller_factory()
    scheduler = PolymarketScheduler(
        poller_factory=factory["poller"],
        monitor_factory=factory["monitor"],
        config_provider=make_config(),
    )
    before = time.time()
    await scheduler._tick()
    after = time.time()
    status = scheduler.get_status()
    assert status["last_run"] is not None
    assert before <= status["last_run"] <= after


@pytest.mark.asyncio
async def test_run_now_does_not_block():
    """run_now() must return immediately; tick runs as a background task."""
    factory, poller, _ = make_poller_factory()

    class SlowPoller(FakePoller):
        async def _poll_all_trades(self):
            await asyncio.sleep(0.1)
            self.poll_calls += 1

    factory, poller, _ = make_poller_factory(poller=SlowPoller())
    scheduler = PolymarketScheduler(
        poller_factory=factory["poller"],
        monitor_factory=factory["monitor"],
        config_provider=make_config(enabled=True, poll_interval=60),
    )

    t0 = time.monotonic()
    scheduler.run_now()
    elapsed = time.monotonic() - t0
    assert elapsed < 0.05, f"run_now took {elapsed:.3f}s"

    await asyncio.sleep(0.2)
    assert poller.poll_calls >= 1


def test_run_now_raises_when_disabled():
    factory, _, _ = make_poller_factory()
    scheduler = PolymarketScheduler(
        poller_factory=factory["poller"],
        monitor_factory=factory["monitor"],
        config_provider=make_config(enabled=False),
    )
    with pytest.raises(RuntimeError, match="disabled"):
        scheduler.run_now()


# --- Registry ---


@pytest.fixture(autouse=True)
def _clean_registry():
    """Each test starts with an empty registry."""
    _reset_registry()
    yield
    _reset_registry()


def test_register_and_get_schedulers():
    from services.scheduler import SignalScanScheduler

    class FakeScraper:
        async def scrape(self):
            return []

        def save_to_db(self, posts):
            pass

    sig = SignalScanScheduler(FakeScraper())
    factory, _, _ = make_poller_factory()
    poly = PolymarketScheduler(
        poller_factory=factory["poller"],
        monitor_factory=factory["monitor"],
    )

    register(sig)
    register(poly)

    schedulers = get_schedulers()
    assert sig in schedulers
    assert poly in schedulers
    assert len(schedulers) == 2


def test_get_scheduler_by_id_returns_correct_one():
    factory, _, _ = make_poller_factory()
    poly = PolymarketScheduler(
        poller_factory=factory["poller"],
        monitor_factory=factory["monitor"],
    )
    register(poly)

    assert get_scheduler(2) is poly
    assert get_scheduler(999) is None


def test_get_schedulers_returns_empty_list_initially():
    assert get_schedulers() == []


# --- Default config provider reads from polymarket_config table ---


def test_default_config_provider_reads_from_polymarket_config_table():
    """Default config_provider (no override) must read from polymarket_config."""
    from services.scheduler import PolymarketScheduler
    from services.database import get_db

    init_db()
    conn = get_db()
    conn.execute(
        "UPDATE polymarket_config SET enabled = 0, poll_interval = 120 WHERE id = 1"
    )
    conn.commit()
    conn.close()

    scheduler = PolymarketScheduler(
        poller_factory=lambda cfg: FakePoller(),
        monitor_factory=lambda cfg: FakeMonitor(),
    )
    assert scheduler._is_enabled() is False
    assert scheduler._interval_seconds() == 120.0

    conn = get_db()
    conn.execute(
        "UPDATE polymarket_config SET enabled = 1, poll_interval = 30 WHERE id = 1"
    )
    conn.commit()
    conn.close()

    assert scheduler._is_enabled() is True
    assert scheduler._interval_seconds() == 30.0
