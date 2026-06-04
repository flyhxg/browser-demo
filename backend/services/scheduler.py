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

    def _is_enabled(self) -> bool:
        return bool(self._config_provider().get("signal_scan_enabled", False))

    def _interval_seconds(self) -> float:
        return float(self._config_provider().get("signal_scan_interval_minutes", 15)) * 60.0

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