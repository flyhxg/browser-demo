"""Tests for the workflow API endpoints (multi-task registry dispatch).

Covers GET /tasks, POST /tasks/{id}/{toggle,run,enable,disable}, PUT /config.
The endpoints dispatch by `task_id` against the scheduler registry; both
SignalScanScheduler (id=1) and PolymarketScheduler (id=2) must be served
through the same router.

Tests run against a minimal FastAPI app that includes the workflow router
only — no main.py / DB lifespan side-effects.

Endpoint tests that just exercise the dispatch logic use `TestClient`
(sync) for simplicity. Tests that actually call `start()` / `stop()` on
a real scheduler use `httpx.AsyncClient` with `ASGITransport` so the
endpoints run in the test's own event loop — otherwise the scheduler's
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

from api.workflow import router as workflow_router
from services.database import get_db, init_db
from services.scheduler import (
    PolymarketScheduler,
    SignalScanScheduler,
    _reset_registry,
    get_scheduler,
    register,
)


# --- Fakes ---


class FakeScraper:
    """Records scrape + save calls; no-op results."""

    def __init__(self):
        self.scrape_calls = 0
        self.save_calls: list[list] = []

    async def scrape(self):
        self.scrape_calls += 1
        return []

    def save_to_db(self, posts):
        self.save_calls.append(list(posts))


class FakePoller:
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

    async def start(self):
        self.start_calls += 1

    async def stop(self):
        self.stop_calls += 1


def make_signal_scheduler(enabled: bool = True, interval_minutes: int = 30):
    """Build a SignalScanScheduler wired to a fake scraper + in-memory config."""
    cfg = {"signal_scan_enabled": enabled, "signal_scan_interval_minutes": interval_minutes}
    return SignalScanScheduler(FakeScraper(), config_provider=lambda: cfg), cfg


def make_polymarket_scheduler(enabled: bool = True, poll_interval: int = 60):
    """Build a PolymarketScheduler wired to fake poller/monitor + in-memory config."""
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
    """Build a fresh FastAPI app wrapping the workflow router (no main.py side effects)."""
    app = FastAPI()
    app.include_router(workflow_router)
    return app


def make_client() -> TestClient:
    """Sync client for dispatch-only tests (no real scheduler start/stop)."""
    return TestClient(make_app())


@asynccontextmanager
async def make_async_client():
    """Async client that runs requests in the test's own event loop.

    Use this for tests that call scheduler.start() / stop() through the
    API — those create asyncio.Event/Task objects that must be bound to
    the same loop the API endpoint is awaited on.
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
    # Reset config rows to known defaults so test order doesn't matter.
    conn = get_db()
    conn.execute(
        "UPDATE trading_config SET signal_scan_enabled = 0, "
        "signal_scan_interval_minutes = 30 WHERE id = 1"
    )
    conn.execute(
        "UPDATE polymarket_config SET enabled = 0, poll_interval = 60 WHERE id = 1"
    )
    conn.commit()
    conn.close()
    yield
    _reset_registry()


# --- GET /tasks ---


def test_get_tasks_returns_empty_list_when_registry_empty():
    """No 503 — frontend treats [] as 'loading done, nothing to show'."""
    client = make_client()
    r = client.get("/api/workflow/tasks")
    assert r.status_code == 200
    assert r.json() == {"tasks": []}


def test_get_tasks_returns_both_schedulers():
    """GET /tasks must include status from every registered scheduler."""
    sig, _ = make_signal_scheduler()
    poly, _, _, _ = make_polymarket_scheduler()
    register(sig)
    register(poly)

    client = make_client()
    r = client.get("/api/workflow/tasks")
    assert r.status_code == 200
    body = r.json()
    assert "tasks" in body
    ids = [t["id"] for t in body["tasks"]]
    assert ids == [1, 2]  # insertion order preserved
    names = {t["id"]: t["name"] for t in body["tasks"]}
    assert names[1] == "Signal Scanner"
    assert names[2] == "Polymarket Poller"


# --- POST /tasks/{id}/toggle ---
# These tests call real scheduler.start() / stop() through the API, so
# they use AsyncClient so the loop binding is consistent.


@pytest.mark.asyncio
async def test_toggle_signal_scanner_starts_then_stops():
    sig, _ = make_signal_scheduler(enabled=True)
    register(sig)

    async with make_async_client() as ac:
        # First toggle: starts it
        r = await ac.post("/api/workflow/tasks/1/toggle")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "toggled"
        assert body["task_id"] == 1
        assert body["task"]["id"] == 1
        assert body["task"]["running"] is True

        # Second toggle: stops it
        r = await ac.post("/api/workflow/tasks/1/toggle")
        assert r.status_code == 200
        assert r.json()["task"]["running"] is False


@pytest.mark.asyncio
async def test_toggle_polymarket_starts_then_stops():
    poly, _, _, _ = make_polymarket_scheduler(enabled=True)
    register(poly)

    async with make_async_client() as ac:
        r = await ac.post("/api/workflow/tasks/2/toggle")
        assert r.status_code == 200
        assert r.json()["task"]["running"] is True

        r = await ac.post("/api/workflow/tasks/2/toggle")
        assert r.status_code == 200
        assert r.json()["task"]["running"] is False


def test_toggle_unknown_task_id_returns_404():
    client = make_client()
    r = client.post("/api/workflow/tasks/999/toggle")
    assert r.status_code == 404


# --- POST /tasks/{id}/run ---


def test_run_signal_scanner_calls_run_now(monkeypatch):
    sig, _ = make_signal_scheduler(enabled=True)
    register(sig)
    called = {"count": 0}

    def fake_run_now():
        called["count"] += 1

    monkeypatch.setattr(sig, "run_now", fake_run_now)

    client = make_client()
    r = client.post("/api/workflow/tasks/1/run")
    assert r.status_code == 200
    assert r.json()["status"] == "started"
    assert called["count"] == 1


def test_run_polymarket_calls_run_now(monkeypatch):
    poly, _, _, _ = make_polymarket_scheduler(enabled=True)
    register(poly)
    called = {"count": 0}

    def fake_run_now():
        called["count"] += 1

    monkeypatch.setattr(poly, "run_now", fake_run_now)

    client = make_client()
    r = client.post("/api/workflow/tasks/2/run")
    assert r.status_code == 200
    assert r.json()["status"] == "started"
    assert called["count"] == 1


def test_run_signal_scanner_returns_400_when_kill_switch_off(monkeypatch):
    sig, _ = make_signal_scheduler(enabled=False)
    register(sig)

    def fake_run_now():
        raise RuntimeError("Signal Scanner is disabled in config — cannot run_now")

    monkeypatch.setattr(sig, "run_now", fake_run_now)

    client = make_client()
    r = client.post("/api/workflow/tasks/1/run")
    assert r.status_code == 400
    assert "disabled" in r.json()["detail"].lower()


def test_run_polymarket_returns_400_when_kill_switch_off(monkeypatch):
    poly, _, _, _ = make_polymarket_scheduler(enabled=False)
    register(poly)

    def fake_run_now():
        raise RuntimeError("Polymarket is disabled in config — cannot run_now")

    monkeypatch.setattr(poly, "run_now", fake_run_now)

    client = make_client()
    r = client.post("/api/workflow/tasks/2/run")
    assert r.status_code == 400
    assert "disabled" in r.json()["detail"].lower()


# --- POST /tasks/{id}/enable ---


@pytest.mark.asyncio
async def test_enable_signal_scanner_writes_kill_switch_on():
    """`start()` is called via the API, so we use AsyncClient for loop consistency."""
    sig, _ = make_signal_scheduler(enabled=False)
    register(sig)

    async with make_async_client() as ac:
        r = await ac.post("/api/workflow/tasks/1/enable")
        assert r.status_code == 200
        assert r.json()["status"] == "enabled"

    # Verify DB row reflects the write
    conn = get_db()
    row = conn.execute(
        "SELECT signal_scan_enabled FROM trading_config WHERE id = 1"
    ).fetchone()
    conn.close()
    assert row["signal_scan_enabled"] == 1


@pytest.mark.asyncio
async def test_enable_polymarket_writes_kill_switch_on():
    poly, _, _, _ = make_polymarket_scheduler(enabled=False)
    register(poly)

    async with make_async_client() as ac:
        r = await ac.post("/api/workflow/tasks/2/enable")
        assert r.status_code == 200
        assert r.json()["status"] == "enabled"

    conn = get_db()
    row = conn.execute(
        "SELECT enabled FROM polymarket_config WHERE id = 1"
    ).fetchone()
    conn.close()
    assert row["enabled"] == 1


# --- POST /tasks/{id}/disable ---


@pytest.mark.asyncio
async def test_disable_signal_scanner_clears_kill_switch():
    # Pre-set the flag to ON so we can observe the OFF transition
    conn = get_db()
    conn.execute(
        "UPDATE trading_config SET signal_scan_enabled = 1 WHERE id = 1"
    )
    conn.commit()
    conn.close()

    sig, _ = make_signal_scheduler(enabled=True)
    register(sig)

    async with make_async_client() as ac:
        r = await ac.post("/api/workflow/tasks/1/disable")
        assert r.status_code == 200
        assert r.json()["status"] == "disabled"

    conn = get_db()
    row = conn.execute(
        "SELECT signal_scan_enabled FROM trading_config WHERE id = 1"
    ).fetchone()
    conn.close()
    assert row["signal_scan_enabled"] == 0


@pytest.mark.asyncio
async def test_disable_polymarket_clears_kill_switch():
    conn = get_db()
    conn.execute(
        "UPDATE polymarket_config SET enabled = 1 WHERE id = 1"
    )
    conn.commit()
    conn.close()

    poly, _, _, _ = make_polymarket_scheduler(enabled=True)
    register(poly)

    async with make_async_client() as ac:
        r = await ac.post("/api/workflow/tasks/2/disable")
        assert r.status_code == 200
        assert r.json()["status"] == "disabled"

    conn = get_db()
    row = conn.execute(
        "SELECT enabled FROM polymarket_config WHERE id = 1"
    ).fetchone()
    conn.close()
    assert row["enabled"] == 0


# --- PUT /config ---


def test_put_config_signal_scanner_interval_minutes():
    """task_id=1 writes minutes directly (no unit conversion)."""
    client = make_client()
    r = client.put(
        "/api/workflow/config",
        json={"task_id": 1, "interval_minutes": 7},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "updated"

    conn = get_db()
    row = conn.execute(
        "SELECT signal_scan_interval_minutes FROM trading_config WHERE id = 1"
    ).fetchone()
    conn.close()
    assert row["signal_scan_interval_minutes"] == 7


def test_put_config_polymarket_converts_minutes_to_seconds():
    """task_id=2 multiplies minutes by 60 (helper takes seconds)."""
    client = make_client()
    r = client.put(
        "/api/workflow/config",
        json={"task_id": 2, "interval_minutes": 1},
    )
    assert r.status_code == 200

    conn = get_db()
    row = conn.execute(
        "SELECT poll_interval FROM polymarket_config WHERE id = 1"
    ).fetchone()
    conn.close()
    assert row["poll_interval"] == 60  # 1 min * 60 = 60 s


def test_put_config_signal_scanner_zero_returns_400():
    """interval_minutes < 1 is invalid for task_id=1 (min is 1 min)."""
    client = make_client()
    r = client.put(
        "/api/workflow/config",
        json={"task_id": 1, "interval_minutes": 0},
    )
    assert r.status_code == 400


def test_put_config_polymarket_zero_minutes_returns_400():
    """0 min = 0 s, which violates Polymarket's 10-second minimum."""
    client = make_client()
    r = client.put(
        "/api/workflow/config",
        json={"task_id": 2, "interval_minutes": 0},
    )
    assert r.status_code == 400


def test_put_config_missing_task_id_returns_422():
    """task_id is now a required field (no implicit default of 1)."""
    client = make_client()
    r = client.put(
        "/api/workflow/config",
        json={"interval_minutes": 5},
    )
    assert r.status_code == 422


# --- 404 path on enable/disable/run for unknown task ---


def test_run_unknown_task_id_returns_404():
    client = make_client()
    r = client.post("/api/workflow/tasks/999/run")
    assert r.status_code == 404


def test_enable_unknown_task_id_returns_404():
    client = make_client()
    r = client.post("/api/workflow/tasks/999/enable")
    assert r.status_code == 404


def test_disable_unknown_task_id_returns_404():
    client = make_client()
    r = client.post("/api/workflow/tasks/999/disable")
    assert r.status_code == 404
