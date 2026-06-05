"""Tests for api/polymarket.py — start/stop/status endpoints that dispatch
through the scheduler registry.

These endpoints used to hold module-level `_polymarket_poller` /
`_position_monitor` globals. They now look up the `PolymarketScheduler`
(task_id=2) in `services.scheduler` and delegate to it. The endpoint
contract is preserved (same JSON shapes, same 200/503 outcomes), but
the start/stop logic now lives in the scheduler, not in the endpoint.

Tests run against a minimal FastAPI app that includes the polymarket
router only — no main.py / DB lifespan side-effects. Each test starts
with an empty registry (`_reset_registry()`) and either registers a
fake `PolymarketScheduler` (built with no-op factories) or leaves the
registry empty, depending on the case.

Endpoint tests that call real `scheduler.start()` / `stop()` use
`httpx.AsyncClient` + `ASGITransport` so the request runs on the same
event loop the test controls — otherwise the scheduler's
`asyncio.Event` (created in the test's loop) would be bound to a
different loop than the background task started inside the endpoint,
raising `RuntimeError: ... is bound to a different event loop`.
"""
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport

from api.polymarket import router as polymarket_router
from services.database import init_db
from services.scheduler import (
    PolymarketScheduler,
    _reset_registry,
    register,
)


# --- Fakes ---


class FakePoller:
    """Records lifecycle calls; no-op behaviour."""

    def __init__(self):
        self.refresh_calls = 0
        self.poll_calls = 0
        self._closed = False

    async def _refresh_leaderboard(self):
        self.refresh_calls += 1

    async def _poll_all_trades(self):
        self.poll_calls += 1

    async def aclose(self):
        self._closed = True


class FakeMonitor:
    def __init__(self):
        self.start_calls = 0
        self.stop_calls = 0
        self._running = False

    async def start(self):
        self.start_calls += 1
        self._running = True

    async def stop(self):
        self.stop_calls += 1
        self._running = False


def make_polymarket_scheduler(enabled: bool = True, poll_interval: int = 60):
    """Build a PolymarketScheduler wired to fake poller/monitor + in-memory config.

    Returns (scheduler, cfg, poller, monitor) so tests can assert on
    the fake's call counters after a start/stop round-trip.
    """
    cfg = {"enabled": 1 if enabled else 0, "poll_interval": poll_interval}
    poller = FakePoller()
    monitor = FakeMonitor()
    scheduler = PolymarketScheduler(
        poller_factory=lambda c: poller,
        monitor_factory=lambda c: monitor,
        config_provider=lambda: cfg,
    )
    return scheduler, cfg, poller, monitor


def make_app() -> FastAPI:
    """Build a fresh FastAPI app wrapping the polymarket router only."""
    app = FastAPI()
    app.include_router(polymarket_router)
    return app


def make_client() -> TestClient:
    """Sync client for read-only endpoint tests (no scheduler start/stop)."""
    return TestClient(make_app())


@asynccontextmanager
async def make_async_client():
    """Async client that runs requests in the test's own event loop.

    Use this for tests that call scheduler.start() / stop() through
    the API — those create asyncio.Event/Task objects that must be
    bound to the same loop the API endpoint is awaited on.
    """
    transport = ASGITransport(app=make_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Fixtures ---


@pytest.fixture(autouse=True)
def _clean_registry():
    """Empty registry + fresh DB row defaults before/after every test."""
    _reset_registry()
    init_db()
    conn = __import__("services.database", fromlist=["get_db"]).get_db()
    conn.execute(
        "UPDATE polymarket_config SET enabled = 0, poll_interval = 60 WHERE id = 1"
    )
    conn.commit()
    conn.close()
    yield
    _reset_registry()


# --- Module-level globals are gone ---


def test_module_globals_removed():
    """The old module-level poller / monitor globals must no longer exist.

    Regression guard: if a future refactor reintroduces them (e.g. to
    keep a reference for the signal handler), the registry dispatch
    is being bypassed again.
    """
    import api.polymarket as m
    assert not hasattr(m, "_polymarket_poller"), (
        "_polymarket_poller should have been removed; use scheduler registry"
    )
    assert not hasattr(m, "_position_monitor"), (
        "_position_monitor should have been removed; use scheduler registry"
    )


# --- POST /start ---


@pytest.mark.asyncio
async def test_start_calls_scheduler_and_returns_started():
    """Registered + not running: start() is called, returns 200 + 'started'."""
    scheduler, _, poller, monitor = make_polymarket_scheduler(enabled=True)
    register(scheduler)

    async with make_async_client() as ac:
        r = await ac.post("/api/polymarket/start")
        assert r.status_code == 200
        assert r.json() == {"status": "started"}

    # Scheduler is now running; both factories were invoked
    assert monitor.start_calls == 1

    # Clean up
    await scheduler.stop()


@pytest.mark.asyncio
async def test_start_returns_already_running_when_scheduler_is_running():
    """Registered + running: start() is NOT called a second time."""
    scheduler, _, _, monitor = make_polymarket_scheduler(enabled=True)
    scheduler._set_interval_seconds(0.5)  # long enough not to drift
    register(scheduler)

    async with make_async_client() as ac:
        # First call: starts the scheduler
        r1 = await ac.post("/api/polymarket/start")
        assert r1.status_code == 200
        assert r1.json() == {"status": "started"}
        assert monitor.start_calls == 1

        # Second call while running: must be a no-op
        r2 = await ac.post("/api/polymarket/start")
        assert r2.status_code == 200
        assert r2.json() == {"status": "already_running"}
        assert monitor.start_calls == 1, "monitor.start() must not be called a second time"

    await scheduler.stop()


def test_start_returns_503_when_scheduler_not_registered():
    """Registry empty: 503 with the expected error message."""
    client = make_client()
    r = client.post("/api/polymarket/start")
    assert r.status_code == 503
    body = r.json()
    # FastAPI wraps HTTPException in {"detail": ...}
    assert "Polymarket scheduler not registered" in body["detail"]
    assert "starting up" in body["detail"]


# --- POST /stop ---


@pytest.mark.asyncio
async def test_stop_calls_scheduler_and_returns_stopped_when_running():
    """Registered + running: stop() is called, returns 200 + 'stopped'."""
    scheduler, _, _, monitor = make_polymarket_scheduler(enabled=True)
    scheduler._set_interval_seconds(0.5)
    register(scheduler)

    async with make_async_client() as ac:
        # Start it first
        r_start = await ac.post("/api/polymarket/start")
        assert r_start.status_code == 200
        assert monitor.start_calls == 1

        # Now stop
        r = await ac.post("/api/polymarket/stop")
        assert r.status_code == 200
        assert r.json() == {"status": "stopped"}

    assert monitor.stop_calls == 1


@pytest.mark.asyncio
async def test_stop_returns_stopped_when_not_running():
    """Registered + not running: stop() is still called (idempotent on the
    scheduler), but the response contract stays 'stopped'."""
    scheduler, _, _, monitor = make_polymarket_scheduler(enabled=True)
    register(scheduler)

    async with make_async_client() as ac:
        r = await ac.post("/api/polymarket/stop")
        assert r.status_code == 200
        assert r.json() == {"status": "stopped"}

    # Scheduler.stop() is idempotent; monitor.stop() is reached on a
    # no-stop call only if monitor was started. Without a start(),
    # monitor is None — scheduler.stop() bails out early.
    assert monitor.stop_calls == 0


def test_stop_returns_503_when_scheduler_not_registered():
    """Registry empty: 503 with the expected error message."""
    client = make_client()
    r = client.post("/api/polymarket/stop")
    assert r.status_code == 503
    body = r.json()
    assert "Polymarket scheduler not registered" in body["detail"]


# --- GET /status ---


@pytest.mark.asyncio
async def test_status_reports_running_when_scheduler_is_running():
    """Registered + running: poller_running=True, monitor_running=True, registered=True."""
    scheduler, _, _, _ = make_polymarket_scheduler(enabled=True)
    scheduler._set_interval_seconds(0.5)
    register(scheduler)

    async with make_async_client() as ac:
        # Start it
        r_start = await ac.post("/api/polymarket/start")
        assert r_start.status_code == 200

        r = await ac.get("/api/polymarket/status")
        assert r.status_code == 200
        body = r.json()
        assert body == {
            "poller_running": True,
            "monitor_running": True,
            "registered": True,
        }

    await scheduler.stop()


@pytest.mark.asyncio
async def test_status_reports_not_running_when_scheduler_is_registered_but_not_running():
    """Registered + not running: poller_running=False, monitor_running=False, registered=True."""
    scheduler, _, _, _ = make_polymarket_scheduler(enabled=True)
    register(scheduler)

    async with make_async_client() as ac:
        r = await ac.get("/api/polymarket/status")
        assert r.status_code == 200
        body = r.json()
        assert body == {
            "poller_running": False,
            "monitor_running": False,
            "registered": True,
        }


def test_status_reports_unregistered_when_scheduler_not_in_registry():
    """Registry empty: registered=False, no error (200, not 503)."""
    client = make_client()
    r = client.get("/api/polymarket/status")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "poller_running": False,
        "monitor_running": False,
        "registered": False,
    }


# --- Read-only endpoints (regression: not touched by the refactor) ---


def test_get_config_still_works():
    """GET /config must continue to read the polymarket_config table."""
    client = make_client()
    r = client.get("/api/polymarket/config")
    assert r.status_code == 200
    body = r.json()
    assert "config" in body
    # Default seed values from init_db()
    cfg = body["config"]
    assert cfg["poll_interval"] == 60
    assert cfg["dry_run"] is True
    assert cfg["enabled"] is False
    assert cfg["cluster_min_users"] == 3
    assert cfg["cluster_min_value"] == 1000.0


def test_get_signals_still_works_when_empty():
    """GET /signals must continue to read the polymarket_signals table."""
    client = make_client()
    r = client.get("/api/polymarket/signals")
    assert r.status_code == 200
    body = r.json()
    assert body == {"signals": []}


def test_get_positions_still_works_when_empty():
    """GET /positions must continue to read polymarket_positions."""
    client = make_client()
    r = client.get("/api/polymarket/positions")
    assert r.status_code == 200
    body = r.json()
    assert body == {"positions": []}


def test_get_trades_still_works_when_empty():
    """GET /trades must continue to read polymarket_trades."""
    client = make_client()
    r = client.get("/api/polymarket/trades")
    assert r.status_code == 200
    body = r.json()
    assert body == {"trades": []}
