"""Background scheduler for Binance Square signal scraping.

Reads interval + enabled flag from config_store. Re-reads on every
tick so config changes take effect without restart. Never raises
out of `_tick` — exceptions are logged and swallowed.

Exposes a single task (`Signal Scanner`) and tracks last_run / next_run
timestamps so the workflow API can report real state to the UI.
"""
import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from services.config_store import get_trading_config_from_db

logger = logging.getLogger(__name__)

_scheduler_instance: "SignalScanScheduler | None" = None


def get_scheduler() -> "SignalScanScheduler | None":
    """Return the module-level scheduler singleton (set by main.py at startup).

    Returns None before main.py has constructed the scheduler.
    """
    return _scheduler_instance


def set_scheduler_instance(instance: "SignalScanScheduler") -> None:
    """Register the module-level scheduler singleton. Called from main.py."""
    global _scheduler_instance
    _scheduler_instance = instance


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
        return float(self._config_provider().get("signal_scan_interval_minutes", 15)) * 60.0

    def _interval_minutes(self) -> int:
        return int(self._config_provider().get("signal_scan_interval_minutes", 15))

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
