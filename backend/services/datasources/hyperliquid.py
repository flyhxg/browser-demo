"""Hyperliquid data source implementation."""
from typing import Any

import httpx

from .base import DataSource

HYPERLIQUID_API = "https://api.hyperliquid.xyz/info"


class HyperliquidSource(DataSource):
    name = "hyperliquid"
    description = "Get whale alerts, large transfers, and market data from Hyperliquid"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=30)

    async def search(self, query: str, **kwargs) -> dict[str, Any]:
        """Search Hyperliquid data. Supports 'whale', 'funding', 'meta'."""
        query_lower = query.lower().strip()

        if "whale" in query_lower or "alert" in query_lower:
            return await self.get_whale_alerts()
        elif "funding" in query_lower:
            return await self.get_funding_rates()
        elif "meta" in query_lower or "tokens" in query_lower:
            return await self.get_meta()
        else:
            return {
                "source": self.name,
                "type": "unknown_query",
                "data": [],
                "message": "Supported queries: whale, funding, meta",
            }

    async def get_meta(self) -> dict[str, Any]:
        """Get all available tokens and their metadata."""
        resp = await self._client.post(
            HYPERLIQUID_API,
            json={"type": "meta"},
        )
        resp.raise_for_status()
        data = resp.json()
        tokens = data.get("universe", [])
        return {
            "source": self.name,
            "type": "meta",
            "data": [
                {
                    "name": token.get("name"),
                    "szDecimals": token.get("szDecimals"),
                    "maxLeverage": token.get("maxLeverage"),
                }
                for token in tokens
            ],
        }

    async def get_whale_alerts(self) -> dict[str, Any]:
        """Get recent large trades/positions."""
        resp = await self._client.post(
            HYPERLIQUID_API,
            json={"type": "frontendPerformance"},
        )
        resp.raise_for_status()
        data = resp.json()
        # Hyperliquid doesn't have a direct "whale alert" API,
        # so we return recent large trades
        return {
            "source": self.name,
            "type": "whale_alerts",
            "data": data if isinstance(data, list) else [data],
            "note": "Returns recent market activity. For precise whale tracking, consider Arkham.",
        }

    async def get_funding_rates(self) -> dict[str, Any]:
        """Get current funding rates for all tokens."""
        resp = await self._client.post(
            HYPERLIQUID_API,
            json={"type": "metaAndAssetCtxs"},
        )
        resp.raise_for_status()
        data = resp.json()
        meta = data.get("meta", {}) if isinstance(data, dict) else {}
        asset_ctxs = data.get("assetCtxs", []) if isinstance(data, dict) else []

        tokens = meta.get("universe", []) if isinstance(meta, dict) else []
        results = []
        for idx, token in enumerate(tokens):
            ctx = asset_ctxs[idx] if idx < len(asset_ctxs) else {}
            results.append({
                "name": token.get("name"),
                "funding": ctx.get("funding"),
                "openInterest": ctx.get("openInterest"),
                "markPrice": ctx.get("markPrice"),
                "prevDayPx": ctx.get("prevDayPx"),
            })

        return {
            "source": self.name,
            "type": "funding_rates",
            "data": results,
        }

    async def health(self) -> bool:
        try:
            resp = await self._client.post(
                HYPERLIQUID_API,
                json={"type": "meta"},
            )
            return resp.status_code == 200
        except Exception:
            return False
