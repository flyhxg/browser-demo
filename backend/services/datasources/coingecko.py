"""CoinGecko data source implementation."""
import asyncio
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import DataSource

COIN_GECKO_BASE_URL = "https://api.coingecko.com/api/v3"
COINGECKO_API = "https://api.coingecko.com/api/v3"


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

    async def get_token_price(self, symbol: str) -> dict[str, Any]:
        """Get current price for a specific token."""
        # Try to resolve CoinGecko ID from symbol first
        cg_id = symbol.lower()
        try:
            search_resp = await self._client.get("/search", params={"query": symbol})
            search_resp.raise_for_status()
            search_data = search_resp.json()
            coins = search_data.get("coins", [])
            if coins:
                # Prefer exact symbol match, otherwise take first
                exact = next((c for c in coins if c.get("symbol", "").upper() == symbol.upper()), None)
                cg_id = exact["id"] if exact else coins[0]["id"]
        except Exception:
            pass

        resp = await self._client.get(
            "/simple/price",
            params={
                "ids": cg_id,
                "vs_currencies": "usd",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "source": self.name,
            "type": "price",
            "symbol": symbol.upper(),
            "cg_id": cg_id,
            "data": data,
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


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_coin_details(coin_id: str) -> dict:
    """Fetch extended coin details including FDV and supply."""
    url = f"{COINGECKO_API}/coins/{coin_id}"
    params = {
        "localization": "false",
        "tickers": "false",
        "market_data": "true",
        "community_data": "false",
        "developer_data": "false",
        "sparkline": "false",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        market_data = data.get("market_data", {})
        return {
            "id": data.get("id"),
            "symbol": data.get("symbol"),
            "name": data.get("name"),
            "fdv": market_data.get("fully_diluted_valuation"),
            "market_cap": market_data.get("market_cap", {}).get("usd"),
            "total_supply": market_data.get("total_supply"),
            "circulating_supply": market_data.get("circulating_supply"),
            "max_supply": market_data.get("max_supply"),
        }
