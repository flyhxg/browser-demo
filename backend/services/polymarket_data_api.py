"""Polymarket Data API Client.

Simplified client for fetching Polymarket prediction market data.
"""
import asyncio
import logging
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)


class PolymarketDataApiClient:
    """Client for Polymarket Data API."""

    BASE_URL = "https://data-api.polymarket.com"

    def __init__(self, session: Optional[aiohttp.ClientSession] = None) -> None:
        self._session = session
        self._own_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self._session

    async def close(self) -> None:
        if self._own_session and self._session:
            await self._session.close()
            self._session = None

    async def _request(self, endpoint: str, params: Optional[dict[str, Any]] = None) -> Any:
        url = f"{self.BASE_URL}{endpoint}"
        session = await self._get_session()
        try:
            async with session.get(url, params=params) as resp:
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as e:
            logger.error("Data API request failed: %s", e)
            return []

    async def get_leaderboard(
        self,
        category: str = "OVERALL",
        time_period: str = "WEEK",
        order_by: str = "PNL",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch top traders from leaderboard."""
        params = {
            "category": category,
            "time_period": time_period,
            "order_by": order_by,
            "limit": limit,
            "offset": offset,
        }
        return await self._request("/api/v1/leaderboard", params)

    async def get_user_activity(
        self,
        user: str,
        limit: int = 20,
        start: Optional[int] = None,
        sort_by: str = "TIMESTAMP",
        sort_direction: str = "DESC",
    ) -> list[dict[str, Any]]:
        """Fetch recent activity (trades) for a user."""
        params: dict[str, Any] = {
            "user": user,
            "limit": limit,
            "sort_by": sort_by,
            "sort_direction": sort_direction,
        }
        if start:
            params["start"] = start
        return await self._request("/api/v1/activity", params)

    async def get_market_info(self, slug: str) -> Optional[dict[str, Any]]:
        """Fetch market info by slug."""
        params = {"slug": slug}
        return await self._request("/api/v1/market", params)

    async def get_market_price(self, token_id: str) -> Optional[dict[str, Any]]:
        """Fetch current market price for a token."""
        params = {"token_id": token_id}
        return await self._request("/api/v1/price", params)
