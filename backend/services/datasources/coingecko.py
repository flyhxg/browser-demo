"""CoinGecko data source implementation."""
import asyncio
from typing import Any

import httpx

from .base import DataSource

COIN_GECKO_BASE_URL = "https://api.coingecko.com/api/v3"


class CoinGeckoSource(DataSource):
    name = "coingecko"
    description = "Get trending tokens, market data, and detailed token info from CoinGecko"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=COIN_GECKO_BASE_URL, timeout=30)

    async def search(self, query: str, **kwargs) -> dict[str, Any]:
        """Search for token info. Supports queries like 'trending', 'top', or token name."""
        query_lower = query.lower().strip()

        if "trending" in query_lower:
            return await self.get_trending()
        elif "top" in query_lower or "market" in query_lower:
            limit = kwargs.get("limit", 10)
            return await self.get_top_market_cap(limit)
        else:
            # Try to search for a specific token
            return await self.search_token(query)

    async def get_trending(self) -> dict[str, Any]:
        """Get trending tokens on CoinGecko."""
        resp = await self._client.get("/search/trending")
        resp.raise_for_status()
        data = resp.json()
        coins = data.get("coins", [])
        return {
            "source": self.name,
            "type": "trending",
            "data": [
                {
                    "rank": idx + 1,
                    "name": coin["item"]["name"],
                    "symbol": coin["item"]["symbol"],
                    "market_cap_rank": coin["item"]["market_cap_rank"],
                    "price_btc": coin["item"].get("price_btc"),
                    "thumb": coin["item"].get("thumb"),
                }
                for idx, coin in enumerate(coins)
            ],
        }

    async def get_top_market_cap(self, limit: int = 10) -> dict[str, Any]:
        """Get top tokens by market cap."""
        resp = await self._client.get(
            "/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": limit,
                "page": 1,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "source": self.name,
            "type": "top_market_cap",
            "data": [
                {
                    "rank": idx + 1,
                    "name": coin["name"],
                    "symbol": coin["symbol"].upper(),
                    "current_price": coin["current_price"],
                    "market_cap": coin["market_cap"],
                    "price_change_24h": coin["price_change_percentage_24h"],
                    "volume_24h": coin["total_volume"],
                    "image": coin.get("image"),
                }
                for idx, coin in enumerate(data)
            ],
        }

    async def search_token(self, query: str) -> dict[str, Any]:
        """Search for a specific token."""
        resp = await self._client.get("/search", params={"query": query})
        resp.raise_for_status()
        data = resp.json()
        coins = data.get("coins", [])[:5]  # Top 5 matches
        return {
            "source": self.name,
            "type": "search",
            "data": [
                {
                    "name": coin["name"],
                    "symbol": coin["symbol"].upper(),
                    "market_cap_rank": coin["market_cap_rank"],
                    "thumb": coin.get("thumb"),
                }
                for coin in coins
            ],
        }

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/ping")
            return resp.status_code == 200
        except Exception:
            return False
