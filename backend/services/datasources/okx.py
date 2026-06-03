"""OKX data source implementation."""
from typing import Any

import httpx

from .base import DataSource

OKX_BASE_URL = "https://www.okx.com"


class OKXSource(DataSource):
    name = "okx"
    description = "Get trending tokens, market tickers, and trading data from OKX"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=OKX_BASE_URL, timeout=30)

    async def search(self, query: str, **kwargs) -> dict[str, Any]:
        """Search OKX data. Supports 'trending', 'tickers', or token symbol."""
        query_lower = query.lower().strip()

        if "trending" in query_lower:
            return await self.get_trending()
        elif "tickers" in query_lower or "market" in query_lower:
            return await self.get_tickers()
        else:
            # Try to get specific token info
            return await self.get_token_info(query.upper())

    async def get_trending(self) -> dict[str, Any]:
        """Get trending tokens on OKX (top gainers)."""
        resp = await self._client.get(
            "/api/v5/market/tickers",
            params={"instType": "SPOT"},
        )
        resp.raise_for_status()
        data = resp.json()
        tickers = data.get("data", [])
        # Sort by 24h change
        sorted_tickers = sorted(
            tickers,
            key=lambda x: float(x.get("last", 0)) / float(x.get("open24h", 1)) - 1
            if x.get("open24h") else 0,
            reverse=True,
        )[:10]

        return {
            "source": self.name,
            "type": "trending",
            "data": [
                {
                    "instId": t["instId"],
                    "last": t["last"],
                    "open24h": t.get("open24h"),
                    "high24h": t.get("high24h"),
                    "low24h": t.get("low24h"),
                    "vol24h": t.get("vol24h"),
                    "volCcy24h": t.get("volCcy24h"),
                }
                for t in sorted_tickers
            ],
        }

    async def get_tickers(self) -> dict[str, Any]:
        """Get all market tickers."""
        resp = await self._client.get(
            "/api/v5/market/tickers",
            params={"instType": "SPOT"},
        )
        resp.raise_for_status()
        data = resp.json()
        tickers = data.get("data", [])[:20]
        return {
            "source": self.name,
            "type": "tickers",
            "data": [
                {
                    "instId": t["instId"],
                    "last": t["last"],
                    "high24h": t.get("high24h"),
                    "low24h": t.get("low24h"),
                    "vol24h": t.get("vol24h"),
                }
                for t in tickers
            ],
        }

    async def get_token_info(self, symbol: str) -> dict[str, Any]:
        """Get specific token info."""
        resp = await self._client.get(
            "/api/v5/market/ticker",
            params={"instId": f"{symbol}-USDT"},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "source": self.name,
            "type": "token_info",
            "data": data.get("data", []),
        }

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/api/v5/public/time")
            return resp.status_code == 200
        except Exception:
            return False
