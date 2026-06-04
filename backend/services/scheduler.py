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