# Signal Scan Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run `BinanceSquareScraper.scrape()` + `save_to_db()` on a fixed interval in the background, with a kill switch (config flag) and optional WebSocket broadcast for new signals.

**Architecture:** One new file `backend/services/scheduler.py` (a `SignalScanScheduler` class with pure asyncio loop), wired into FastAPI's `lifespan` in `main.py`. Config-driven via two new keys in `trading_config`. No new dependencies.

**Tech Stack:** Python 3.14, asyncio, FastAPI lifespan, pytest-asyncio (already in use), unittest.mock.

**Spec:** `docs/superpowers/specs/2026-06-04-signal-scan-scheduler-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/services/scheduler.py` (NEW) | `SignalScanScheduler` class — background tick loop, config-driven, never raises |
| `backend/main.py` (MODIFY) | Replace `@app.on_event("startup")` with modern `lifespan` context manager; wire scheduler start/stop |
| `backend/api/trading.py` (MODIFY) | Add 2 keys to `update_trading_config` whitelist |
| `backend/tests/test_api_trading_actions.py` (MODIFY) | Add 2 tests for new whitelist keys |
| `backend/tests/test_scheduler.py` (NEW) | 11 tests covering `_tick`, `start`, `stop`, `_loop` |

---

## Task 1: Add config keys to update_trading_config whitelist

**Files:**
- Modify: `backend/api/trading.py:245-247`
- Modify: `backend/tests/test_api_trading_actions.py` (append 2 tests)

- [ ] **Step 1: Write the failing tests**

Append these to `backend/tests/test_api_trading_actions.py`:

```python
def test_update_config_accepts_signal_scan_enabled(client):
    r = client.put("/api/trading/config", json={"signal_scan_enabled": True})
    assert r.status_code == 200
    assert r.json() == {"status": "updated"}


def test_update_config_accepts_signal_scan_interval(client):
    r = client.put("/api/trading/config", json={"signal_scan_interval_minutes": 5})
    assert r.status_code == 200
    assert r.json() == {"status": "updated"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_api_trading_actions.py::test_update_config_accepts_signal_scan_enabled tests/test_api_trading_actions.py::test_update_config_accepts_signal_scan_interval -v`
Expected: 2 failures — the whitelist rejects unknown keys and the endpoint returns a non-200 (or empty body).

- [ ] **Step 3: Add the keys to the whitelist in `api/trading.py`**

In `backend/api/trading.py`, find the whitelist tuple inside `update_trading_config` (around line 245):

```python
            if key in ("binance_api_key", "binance_secret_key", "max_position_size_usd",
                      "tp_percentage", "sl_percentage", "min_confidence",
                      "max_daily_loss", "scan_interval_minutes"):
```

Replace it with:

```python
            if key in ("binance_api_key", "binance_secret_key", "max_position_size_usd",
                      "tp_percentage", "sl_percentage", "min_confidence",
                      "max_daily_loss", "scan_interval_minutes",
                      "signal_scan_enabled", "signal_scan_interval_minutes"):
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_api_trading_actions.py::test_update_config_accepts_signal_scan_enabled tests/test_api_trading_actions.py::test_update_config_accepts_signal_scan_interval -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd D:/work/browser-demo
git add backend/api/trading.py backend/tests/test_api_trading_actions.py
git commit -m "feat(api): accept signal_scan_* in trading config whitelist"
```

---

## Task 2: Create scheduler.py skeleton

**Files:**
- Create: `backend/services/scheduler.py`

- [ ] **Step 1: Create the file with the class and `__init__`**

Create `backend/services/scheduler.py`:

```python
"""Background scheduler for Binance Square signal scraping.

Reads interval + enabled flag from config_store. Re-reads on every
tick so config changes take effect without restart. Never raises
out of `_tick` — exceptions are logged and swallowed.
"""
import asyncio
import logging
from typing import Awaitable, Callable

from services.config_store import get_config

logger = logging.getLogger(__name__)


class SignalScanScheduler:
    """Background loop that calls scraper.scrape() + save_to_db() on an interval."""

    def __init__(
        self,
        scraper,
        config_provider: Callable[[], dict] | None = None,
        ws_broadcast: Callable[[str, dict], Awaitable[None]] | None = None,
    ):
        self.scraper = scraper
        self._config_provider = config_provider or get_config
        self._ws_broadcast = ws_broadcast
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    def _is_enabled(self) -> bool:
        return bool(self._config_provider().get("signal_scan_enabled", False))

    def _interval_seconds(self) -> float:
        return float(self._config_provider().get("signal_scan_interval_minutes", 15)) * 60.0
```

- [ ] **Step 2: Commit**

```bash
cd D:/work/browser-demo
git add backend/services/scheduler.py
git commit -m "feat(scheduler): add SignalScanScheduler skeleton"
```

---

## Task 3: `_tick` calls scraper + save (TDD)

**Files:**
- Modify: `backend/tests/test_scheduler.py` (create with first test)
- Modify: `backend/services/scheduler.py`

- [ ] **Step 1: Create the test file with the first failing test**

Create `backend/tests/test_scheduler.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_scheduler.py::test_tick_calls_scraper_and_save -v`
Expected: FAIL with `AttributeError: 'SignalScanScheduler' object has no attribute '_tick'`.

- [ ] **Step 3: Add the minimal `_tick` method to `services/scheduler.py`**

In `backend/services/scheduler.py`, add this method to `SignalScanScheduler` (above `_is_enabled`):

```python
    async def _tick(self) -> None:
        """One scrape cycle. Always called from `_loop`."""
        posts = await self.scraper.scrape()
        if not posts:
            return
        self.scraper.save_to_db(posts)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_scheduler.py::test_tick_calls_scraper_and_save -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd D:/work/browser-demo
git add backend/services/scheduler.py backend/tests/test_scheduler.py
git commit -m "feat(scheduler): _tick calls scraper and save"
```

---

## Task 4: `_tick` broadcasts when ws provided (TDD)

**Files:**
- Modify: `backend/tests/test_scheduler.py`
- Modify: `backend/services/scheduler.py`

- [ ] **Step 1: Append the failing test**

Append to `backend/tests/test_scheduler.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_scheduler.py::test_tick_broadcasts_when_ws_provided tests/test_scheduler.py::test_tick_no_broadcast_when_ws_is_none -v`
Expected: 1 fail (`test_tick_broadcasts_when_ws_provided` — `'NoneType' object is not iterable` or `_tick` doesn't broadcast). The "no ws" test should pass since `_tick` doesn't touch ws yet.

- [ ] **Step 3: Add the broadcast block to `_tick`**

In `backend/services/scheduler.py`, update `_tick`:

```python
    async def _tick(self) -> None:
        """One scrape cycle. Always called from `_loop`."""
        posts = await self.scraper.scrape()
        if not posts:
            return
        self.scraper.save_to_db(posts)
        if self._ws_broadcast:
            for post in posts:
                await self._ws_broadcast("signal:new", post)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_scheduler.py::test_tick_broadcasts_when_ws_provided tests/test_scheduler.py::test_tick_no_broadcast_when_ws_is_none -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd D:/work/browser-demo
git add backend/services/scheduler.py backend/tests/test_scheduler.py
git commit -m "feat(scheduler): _tick broadcasts signal:new per post"
```

---

## Task 5: `_tick` no-op on empty posts (TDD)

**Files:**
- Modify: `backend/tests/test_scheduler.py`

- [ ] **Step 1: Append the failing test**

```python
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
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_scheduler.py::test_tick_noop_on_empty_posts -v`
Expected: PASS (the `if not posts: return` already handles this from Task 3).

- [ ] **Step 3: No implementation change needed — just commit**

```bash
cd D:/work/browser-demo
git add backend/tests/test_scheduler.py
git commit -m "test(scheduler): cover _tick no-op on empty posts"
```

---

## Task 6: `_tick` survives scraper exception (TDD)

**Files:**
- Modify: `backend/services/scheduler.py`
- Modify: `backend/tests/test_scheduler.py`

- [ ] **Step 1: Append the failing test**

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_scheduler.py::test_tick_survives_scraper_exception -v`
Expected: FAIL with `RuntimeError: upstream down` (uncaught from `scraper.scrape()`).

- [ ] **Step 3: Wrap `_tick` body in try/except**

In `backend/services/scheduler.py`, replace `_tick` with:

```python
    async def _tick(self) -> None:
        """One scrape cycle. Always called from `_loop`. Per-step errors are logged and swallowed."""
        try:
            posts = await self.scraper.scrape()
        except Exception as e:
            logger.warning(f"[SignalScanScheduler] scrape failed: {e}")
            return
        if not posts:
            return
        try:
            self.scraper.save_to_db(posts)
        except Exception as e:
            logger.error(f"[SignalScanScheduler] save_to_db failed: {e}", exc_info=True)
            return
        if self._ws_broadcast:
            for post in posts:
                try:
                    await self._ws_broadcast("signal:new", post)
                except Exception as e:
                    logger.warning(f"[SignalScanScheduler] broadcast failed for post: {e}")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_scheduler.py -v`
Expected: all 5 tests passed (3 from prior tasks + 2 new from this task? — actually: 1 from Task 3, 2 from Task 4, 1 from Task 5, 1 from Task 6 = 5).

- [ ] **Step 5: Commit**

```bash
cd D:/work/browser-demo
git add backend/services/scheduler.py backend/tests/test_scheduler.py
git commit -m "feat(scheduler): _tick per-step error handling"
```

---

## Task 7: `_tick` survives save_to_db exception (TDD)

**Files:**
- Modify: `backend/tests/test_scheduler.py`

- [ ] **Step 1: Append the test**

```python
@pytest.mark.asyncio
async def test_tick_survives_save_exception():
    """_tick must swallow save_to_db exceptions and not propagate them."""
    from services.scheduler import SignalScanScheduler

    scraper = FakeScraper(posts=[{"content": "x"}], save_raises=RuntimeError("db down"))
    scheduler = SignalScanScheduler(scraper, config_provider=make_config())

    # Should NOT raise
    await scheduler._tick()

    assert scraper.save_calls == [[{"content": "x"}]]
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_scheduler.py::test_tick_survives_save_exception -v`
Expected: PASS (the try/except around `save_to_db` was added in Task 6).

- [ ] **Step 3: Commit**

```bash
cd D:/work/browser-demo
git add backend/tests/test_scheduler.py
git commit -m "test(scheduler): cover _tick save_to_db exception"
```

---

## Task 8: `_tick` survives ws broadcast exception per-post (TDD)

**Files:**
- Modify: `backend/tests/test_scheduler.py`

- [ ] **Step 1: Append the test**

```python
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
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_scheduler.py::test_tick_survives_ws_broadcast_exception_per_post -v`
Expected: PASS (the per-post try/except was added in Task 6).

- [ ] **Step 3: Commit**

```bash
cd D:/work/browser-demo
git add backend/tests/test_scheduler.py
git commit -m "test(scheduler): cover _tick per-post ws broadcast exception"
```

---

## Task 9: `start` method — no-op when disabled, idempotent (TDD)

**Files:**
- Modify: `backend/services/scheduler.py`
- Modify: `backend/tests/test_scheduler.py`

- [ ] **Step 1: Append the failing tests**

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_scheduler.py::test_start_noop_when_disabled_in_config tests/test_scheduler.py::test_start_creates_task_when_enabled tests/test_scheduler.py::test_start_is_idempotent -v`
Expected: 3 failures — `'SignalScanScheduler' object has no attribute 'start'`.

- [ ] **Step 3: Add the `start` method to `SignalScanScheduler`**

In `backend/services/scheduler.py`, add `start` above `_tick`:

```python
    async def start(self) -> None:
        """Start the background scan loop. No-op if disabled in config. Idempotent."""
        if not self._is_enabled():
            logger.info("[SignalScanScheduler] disabled in config — not starting")
            return
        if self._task and not self._task.done():
            return  # already running
        self._stopped.clear()
        self._task = asyncio.create_task(self._loop(), name="signal-scan-scheduler")
        logger.info(
            f"[SignalScanScheduler] started, interval={self._interval_seconds() / 60:.1f}m"
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_scheduler.py -v`
Expected: all 9 tests pass (3 from earlier + 3 from this task + the 3 needing `stop` will fail because `stop` doesn't exist yet — see next task).

If `test_start_creates_task_when_enabled` fails with "no attribute 'stop'", that's expected — implement `stop` in Task 10 and those tests will pass.

- [ ] **Step 5: Commit**

```bash
cd D:/work/browser-demo
git add backend/services/scheduler.py backend/tests/test_scheduler.py
git commit -m "feat(scheduler): start() with no-op when disabled and idempotent"
```

---

## Task 10: `stop` method — cancels running task (TDD)

**Files:**
- Modify: `backend/services/scheduler.py`
- Modify: `backend/tests/test_scheduler.py`

- [ ] **Step 1: Append the failing test**

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_scheduler.py::test_stop_cancels_running_task tests/test_scheduler.py::test_stop_noop_when_not_running -v`
Expected: 2 failures — `'SignalScanScheduler' object has no attribute 'stop'`.

- [ ] **Step 3: Add the `stop` method to `SignalScanScheduler`**

In `backend/services/scheduler.py`, add `stop` immediately after `start`:

```python
    async def stop(self) -> None:
        """Cancel the loop and wait for the current tick to finish."""
        if not self._task:
            return
        self._stopped.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("[SignalScanScheduler] stopped")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_scheduler.py -v`
Expected: all 11 tests pass.

- [ ] **Step 5: Commit**

```bash
cd D:/work/browser-demo
git add backend/services/scheduler.py backend/tests/test_scheduler.py
git commit -m "feat(scheduler): stop() cancels running task"
```

---

## Task 11: `_loop` method — interval reading + enabled toggle (TDD)

**Files:**
- Modify: `backend/services/scheduler.py`
- Modify: `backend/tests/test_scheduler.py`

- [ ] **Step 1: Append the failing tests**

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_scheduler.py::test_loop_runs_multiple_ticks_at_configured_interval tests/test_scheduler.py::test_loop_picks_up_enabled_toggle -v`
Expected: 2 failures — `'SignalScanScheduler' object has no attribute '_loop'`.

- [ ] **Step 3: Add the `_loop` method to `SignalScanScheduler`**

In `backend/services/scheduler.py`, add `_loop` immediately before `_tick`:

```python
    async def _loop(self) -> None:
        """Main loop. Sleeps `_interval_seconds` between ticks. Cancellable via stop()."""
        while not self._stopped.is_set():
            await self._tick()
            try:
                await asyncio.wait_for(
                    self._stopped.wait(),
                    timeout=self._interval_seconds(),
                )
                break  # stopped event fired
            except asyncio.TimeoutError:
                pass  # normal — sleep elapsed, next tick
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_scheduler.py -v`
Expected: all 13 tests pass (11 from prior + 2 new).

- [ ] **Step 5: Run the full backend test suite to check for regressions**

Run: `cd backend && python -m pytest -q`
Expected: 133 passed (was 120 + 13 new).

- [ ] **Step 6: Commit**

```bash
cd D:/work/browser-demo
git add backend/services/scheduler.py backend/tests/test_scheduler.py
git commit -m "feat(scheduler): _loop reads interval each tick and respects stop"
```

---

## Task 12: Wire scheduler into main.py lifespan

**Files:**
- Modify: `backend/main.py`

This is an integration change with no automated test (verified manually after deploy). The scheduler is already tested in isolation.

- [ ] **Step 1: Replace the existing `@app.on_event("startup")` with a `lifespan` context manager**

In `backend/main.py`, find the existing startup block (around line 36):

```python
@app.on_event("startup")
async def _warm_sector_classifier() -> None:
    import asyncio as _asyncio
    async def _run() -> None:
        try:
            await get_classifier().ensure_loaded()
        except Exception as _e:
            print(f"[main] sector classifier warmup failed: {_e}", flush=True)
    _asyncio.create_task(_run())
```

Replace the whole block (including the `@app.on_event("startup")` decorator) with:

```python
from contextlib import asynccontextmanager

from services.signal_scraper import BinanceSquareScraper
from services.scheduler import SignalScanScheduler

_scraper = BinanceSquareScraper()
_scheduler = SignalScanScheduler(_scraper)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    asyncio.create_task(_warm_sector_classifier())
    await _scheduler.start()
    yield
    # shutdown
    await _scheduler.stop()


async def _warm_sector_classifier() -> None:
    try:
        await get_classifier().ensure_loaded()
    except Exception as _e:
        print(f"[main] sector classifier warmup failed: {_e}", flush=True)
```

Then change the `app = FastAPI(...)` line (around line 33) to pass `lifespan=lifespan`:

```python
app = FastAPI(title="Browser Use Web Demo", lifespan=lifespan)
```

- [ ] **Step 2: Add the `import asyncio` near the top of `main.py` if not already present**

Check the imports at the top of `backend/main.py`. If `asyncio` is not imported, add `import asyncio` to the import block. (It's already imported in some files via `import asyncio as _asyncio` in the on_event block — we're moving to top-level.)

- [ ] **Step 3: Run the full backend test suite to confirm no regressions**

Run: `cd backend && python -m pytest -q`
Expected: 133 passed.

- [ ] **Step 4: Commit**

```bash
cd D:/work/browser-demo
git add backend/main.py
git commit -m "feat(main): wire SignalScanScheduler into FastAPI lifespan"
```

- [ ] **Step 5: Manual smoke test (documented, not automated)**

After deploy, flip `signal_scan_enabled=true` via `PUT /api/trading/config`:

```bash
curl -X PUT http://localhost:8000/api/trading/config \
  -H "Content-Type: application/json" \
  -d '{"signal_scan_enabled": true, "signal_scan_interval_minutes": 1}'
```

Then tail backend logs. Expected: one `[SignalScanScheduler] started, interval=1.0m` log on startup, then a tick log every minute. Frontend WS panel should see `signal:new` events.

---

## Self-Review

**Spec coverage** — checked against `docs/superpowers/specs/2026-06-04-signal-scan-scheduler-design.md`:

- ✅ `SignalScanScheduler.__init__` signature (scraper, config_provider, ws_broadcast) — Task 2
- ✅ `_tick` happy path (calls scraper + save + broadcast) — Tasks 3, 4
- ✅ `_tick` no-op on empty posts — Task 5
- ✅ `_tick` survives scraper / save / ws exceptions — Tasks 6, 7, 8
- ✅ `start` no-op when disabled, idempotent — Task 9
- ✅ `stop` cancels running task — Task 10
- ✅ `_loop` reads interval each tick, picks up enabled toggle — Task 11
- ✅ Config keys whitelisted in `update_trading_config` — Task 1
- ✅ FastAPI `lifespan` integration — Task 12
- ⏸ WebSocket hub wiring — explicitly out of scope per spec ("Wiring it to the existing api/ws.py hub is a follow-up commit")

**Placeholder scan** — no TBD / TODO / "implement later" / "fill in details". All steps have full code or commands with expected output.

**Type consistency** — `scraper` parameter is positional; `config_provider` and `ws_broadcast` are keyword-or-positional in all tests. `Callable[[], dict]` and `Callable[[str, dict], Awaitable[None]]` match the spec. The `FakeScraper` test helper has `scrape` and `save_to_db` methods matching the real `BinanceSquareScraper`.

**Scope** — 12 tasks, all TDD (except Task 2 skeleton and Task 12 wiring). Estimated total ~2h implementation + ~30min test review.
