"""Background schedulers for workflow tasks.

Each scheduler exposes a uniform surface so the workflow API can
control them by `task_id` without knowing the implementation:

    TASK_ID, TASK_NAME = ...   # class attributes
    get_status() -> dict
    start() / stop() / run_now()

The module owns a **registry** of all schedulers the app has
registered at startup. `workflow.py` reads from the registry to
serve `/api/workflow/tasks` and the per-task action endpoints.

Two schedulers ship out of the box:
- SignalScanScheduler (TASK_ID=1) — Binance Square signal scraper
- PolymarketScheduler  (TASK_ID=2) — top-200 cluster signal poller
"""
import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from services.config_store import get_trading_config_from_db

logger = logging.getLogger(__name__)


# --- Registry -----------------------------------------------------------------

_schedulers: list[Any] = []


def register(scheduler: Any) -> None:
    """Register a scheduler instance for the workflow API to expose.

    Idempotent by `TASK_ID`: re-registering a different instance with
    the same id is a no-op. This guards against double-import bugs
    where `python main.py` loads the module as `__main__` and uvicorn
    then re-imports it as `main`, causing module-level code to run
    twice. Two scheduler instances of the same id would otherwise
    appear in the registry, with the second one never being
    `start()`-ed.
    """
    target_id = getattr(scheduler, "TASK_ID", None)
    for existing in _schedulers:
        if getattr(existing, "TASK_ID", None) == target_id:
            return  # already registered for this id
    _schedulers.append(scheduler)


def get_schedulers() -> list[Any]:
    """Return all registered schedulers (order preserved, insertion order)."""
    return list(_schedulers)


def get_scheduler(task_id: int) -> Any | None:
    """Return the scheduler with the given TASK_ID, or None."""
    for s in _schedulers:
        if getattr(s, "TASK_ID", None) == task_id:
            return s
    return None


def _reset_registry() -> None:
    """Clear the registry. Test-only — do not call from app code."""
    _schedulers.clear()


# --- Backwards-compat shim ----------------------------------------------------
# main.py and older call sites use `set_scheduler_instance(s)` /
# `get_scheduler()` (no args). Kept as thin wrappers so a single
# registration keeps working while the registry grows.

_scheduler_instance: Any = None


def get_scheduler_instance() -> Any | None:
    """Deprecated: use `get_schedulers()` to support multiple tasks."""
    return _scheduler_instance


def set_scheduler_instance(instance: Any) -> None:
    """Register a scheduler. Backwards-compat wrapper around `register`.

    Stores the latest call as the legacy singleton and ensures the
    instance is also in the registry (idempotent — re-registering the
    same id is a no-op, even if the instance is different).
    """
    global _scheduler_instance
    _scheduler_instance = instance
    register(instance)


# --- SignalScanScheduler ------------------------------------------------------

class SignalScanScheduler:
    """Background loop that calls scraper.scrape() + save_to_db() on an interval."""

    TASK_ID = 1
    TASK_NAME = "Signal Scanner"

    def __init__(
        self,
        scraper,
        config_provider: Callable[[], dict] | None = None,
        ws_broadcast: Callable[[str, dict], Awaitable[None]] | None = None,
    ):
        self.scraper = scraper
        self._config_provider = config_provider or get_trading_config_from_db
        self._ws_broadcast = ws_broadcast
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()
        self._last_run: float | None = None
        self._next_run: float | None = None

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
        self._next_run = None
        logger.info("[SignalScanScheduler] stopped")

    async def _tick(self) -> None:
        """One scrape cycle. Always called from `_loop`. Per-step errors are logged and swallowed."""
        try:
            posts = await self.scraper.scrape()
        except Exception as e:
            logger.warning(f"[SignalScanScheduler] scrape failed: {e}")
            return
        if not posts:
            self._last_run = time.time()
            return
        try:
            self.scraper.save_to_db(posts)
        except Exception as e:
            logger.error(f"[SignalScanScheduler] save_to_db failed: {e}", exc_info=True)
            return
        self._last_run = time.time()
        if self._ws_broadcast:
            for post in posts:
                try:
                    await self._ws_broadcast("signal:new", post)
                except Exception as e:
                    logger.warning(f"[SignalScanScheduler] broadcast failed for post: {e}")

    def _is_enabled(self) -> bool:
        return bool(self._config_provider().get("signal_scan_enabled", False))

    def _interval_seconds(self) -> float:
        return float(self._config_provider().get("signal_scan_interval_minutes", 30)) * 60.0

    def _interval_minutes(self) -> int:
        return int(self._config_provider().get("signal_scan_interval_minutes", 30))

    def get_status(self) -> dict[str, Any]:
        """Return the task's current state for the workflow API.

        Fields:
        - id, name: stable identifier + display name
        - enabled: config flag (whether the task is *allowed* to run)
        - running: whether the background loop is currently active
        - interval_minutes: re-read live from config
        - last_run: epoch seconds of the most recent completed tick (or None)
        - next_run: epoch seconds of the next scheduled tick (or None when paused)
        """
        enabled = self._is_enabled()
        running = self._task is not None and not self._task.done()
        return {
            "id": self.TASK_ID,
            "name": self.TASK_NAME,
            "enabled": enabled,
            "running": running,
            "status": "running" if running else ("paused" if not enabled else "idle"),
            "interval_minutes": self._interval_minutes(),
            "last_run": self._last_run,
            "next_run": self._next_run,
        }

    def run_now(self) -> None:
        """Fire a single tick in the background. Non-blocking.

        The task returns immediately; the tick runs asynchronously and
        updates last_run when it completes.
        """
        if not self._is_enabled():
            raise RuntimeError("Signal Scanner is disabled in config — cannot run_now")
        asyncio.create_task(self._tick(), name="signal-scan-run-now")

    async def start(self) -> None:
        """Start the background scan loop. No-op if disabled in config. Idempotent."""
        if not self._is_enabled():
            logger.info("[SignalScanScheduler] disabled in config — not starting")
            return
        if self._task and not self._task.done():
            return  # already running
        self._stopped.clear()
        # Set next_run eagerly so the API can report a scheduled time even
        # before the background task hits its first iteration. The task
        # overwrites this value at the top of each loop iteration.
        self._next_run = time.time() + self._interval_seconds()
        self._task = asyncio.create_task(self._loop(), name="signal-scan-scheduler")
        logger.info(
            f"[SignalScanScheduler] started, interval={self._interval_seconds() / 60:.1f}m"
        )

    async def _loop(self) -> None:
        """Main loop. Sleeps `_interval_seconds` between ticks. Cancellable via stop()."""
        while not self._stopped.is_set():
            self._next_run = time.time() + self._interval_seconds()
            await self._tick()
            try:
                await asyncio.wait_for(
                    self._stopped.wait(),
                    timeout=self._interval_seconds(),
                )
                break  # stopped event fired
            except asyncio.TimeoutError:
                pass  # normal — sleep elapsed, next tick
        self._next_run = None


# --- PolymarketScheduler ------------------------------------------------------

def _read_polymarket_config() -> dict[str, Any]:
    """Default config provider for PolymarketScheduler — reads polymarket_config table."""
    from services.database import get_db
    conn = get_db()
    row = conn.execute("SELECT * FROM polymarket_config WHERE id = 1").fetchone()
    conn.close()
    return dict(row) if row else {}


def _default_poller_factory(cfg: dict[str, Any]) -> Any:
    """Construct a TopUsersPoller from the polymarket_config row."""
    from services.polymarket_poller import TopUsersPoller
    return TopUsersPoller(
        poll_interval=cfg.get("poll_interval") or 60,
        cluster_min_users=cfg.get("cluster_min_users") or 3,
        cluster_min_value=cfg.get("cluster_min_value") or 1000.0,
        market_expiry_hours=cfg.get("market_expiry_hours") or 6,
        min_price=cfg.get("min_price") or 0.01,
        max_price=cfg.get("max_price") or 0.99,
    )


def _default_monitor_factory(cfg: dict[str, Any]) -> Any:
    """Construct a PositionMonitor + PolymarketTrader from the polymarket_config row."""
    from services.polymarket_monitor import PositionMonitor
    from services.polymarket_trader import PolymarketTrader
    trader = PolymarketTrader(
        api_key=cfg.get("api_key"),
        api_secret=cfg.get("api_secret"),
        api_passphrase=cfg.get("api_passphrase"),
        private_key=cfg.get("private_key"),
        dry_run=bool(cfg.get("dry_run", 1)),
    )
    return PositionMonitor(trader=trader, check_interval=30)


class PolymarketScheduler:
    """Background loop for the top-200 cluster signal poller.

    Wraps a `TopUsersPoller` (signal detection) and a `PositionMonitor`
    (SL/TP enforcement). Owns the timing — calls
    `poller._refresh_leaderboard() + _poll_all_trades()` on each tick
    so the scheduler's interval (in `polymarket_config.poll_interval`)
    is the single source of truth.

    The monitor runs its own internal loop on its own cadence
    (`check_interval`, hard-coded 30s) because position monitoring is
    independent of signal detection rate.

    `signal_handler` is the async callback the poller invokes when a
    cluster signal is detected (typically the api-level handler that
    persists + optionally executes the signal). It's registered on the
    poller in `start()`. Optional — leave None for tests that don't
    exercise the signal path.
    """

    TASK_ID = 2
    TASK_NAME = "Polymarket Poller"

    def __init__(
        self,
        signal_handler: Callable | None = None,
        poller_factory: Callable[[dict], Any] | None = None,
        monitor_factory: Callable[[dict], Any] | None = None,
        config_provider: Callable[[], dict] | None = None,
    ):
        self._signal_handler = signal_handler
        self._poller_factory = poller_factory or _default_poller_factory
        self._monitor_factory = monitor_factory or _default_monitor_factory
        self._config_provider = config_provider or _read_polymarket_config
        self._poller: Any | None = None
        self._monitor: Any | None = None
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()
        self._last_run: float | None = None
        self._next_run: float | None = None
        self._interval_override: float | None = None  # for tests

    def _set_interval_seconds(self, seconds: float) -> None:
        """Test hook: override the live config interval (e.g. for fast tests)."""
        self._interval_override = float(seconds)

    def _is_enabled(self) -> bool:
        return bool(self._config_provider().get("enabled", 0))

    def _interval_seconds(self) -> float:
        if self._interval_override is not None:
            return self._interval_override
        return float(self._config_provider().get("poll_interval") or 60)

    def _interval_minutes(self) -> int:
        return max(1, int(self._interval_seconds() // 60))

    async def _tick(self) -> None:
        """One poller cycle. Errors are swallowed so the loop survives.

        Updates `last_run` on every invocation, including no-op ticks
        (no poller constructed yet, or poller raised). Mirrors
        SignalScanScheduler._tick's contract: `last_run` reflects the
        last time the loop completed, not whether work was done.
        """
        try:
            if self._poller:
                await self._poller._refresh_leaderboard()
                await self._poller._poll_all_trades()
        except Exception as e:
            logger.warning(f"[PolymarketScheduler] tick failed: {e}")
        finally:
            self._last_run = time.time()

    async def start(self) -> None:
        """Construct poller + monitor from config and start the background loop."""
        if not self._is_enabled():
            logger.info("[PolymarketScheduler] disabled in config — not starting")
            return
        if self._task and not self._task.done():
            return  # already running

        cfg = self._config_provider()
        self._poller = self._poller_factory(cfg)
        if self._signal_handler and hasattr(self._poller, "on_signal"):
            self._poller.on_signal(self._signal_handler)
        self._monitor = self._monitor_factory(cfg)
        await self._monitor.start()

        self._stopped.clear()
        self._next_run = time.time() + self._interval_seconds()
        self._task = asyncio.create_task(self._loop(), name="polymarket-scheduler")
        logger.info(
            f"[PolymarketScheduler] started, interval={self._interval_seconds():.0f}s"
        )

    async def stop(self) -> None:
        """Cancel the loop, stop the monitor, and clear the poller reference."""
        if not self._task and not self._monitor and not self._poller:
            return
        self._stopped.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._monitor:
            try:
                await self._monitor.stop()
            except Exception as e:
                logger.warning(f"[PolymarketScheduler] monitor.stop failed: {e}")
            self._monitor = None
        # Poller may hold an open HTTP client — close it if it exposes aclose().
        if self._poller and hasattr(self._poller, "data_api") and hasattr(self._poller.data_api, "close"):
            try:
                await self._poller.data_api.close()
            except Exception as e:
                logger.debug(f"[PolymarketScheduler] poller data_api close failed: {e}")
        if self._poller and hasattr(self._poller, "aclose"):
            try:
                await self._poller.aclose()
            except Exception:
                pass
        self._poller = None
        self._next_run = None
        logger.info("[PolymarketScheduler] stopped")

    async def _loop(self) -> None:
        """Main loop. Sleeps `_interval_seconds` between ticks."""
        while not self._stopped.is_set():
            self._next_run = time.time() + self._interval_seconds()
            await self._tick()
            try:
                await asyncio.wait_for(
                    self._stopped.wait(),
                    timeout=self._interval_seconds(),
                )
                break
            except asyncio.TimeoutError:
                pass
        self._next_run = None

    def run_now(self) -> None:
        """Fire a single tick in the background. Non-blocking.

        Requires the scheduler to be enabled. Constructs poller/monitor
        on demand if start() hasn't been called yet, so the operator can
        use this to smoke-test the polling path without a full start.
        """
        if not self._is_enabled():
            raise RuntimeError("Polymarket is disabled in config — cannot run_now")
        if self._poller is None:
            cfg = self._config_provider()
            self._poller = self._poller_factory(cfg)
        asyncio.create_task(self._tick(), name="polymarket-run-now")

    def get_status(self) -> dict[str, Any]:
        """Snapshot of the scheduler's runtime state for the workflow API."""
        enabled = self._is_enabled()
        running = self._task is not None and not self._task.done()
        return {
            "id": self.TASK_ID,
            "name": self.TASK_NAME,
            "enabled": enabled,
            "running": running,
            "status": "running" if running else ("paused" if not enabled else "idle"),
            "interval_minutes": self._interval_minutes(),
            "last_run": self._last_run,
            "next_run": self._next_run,
        }
