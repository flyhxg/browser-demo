"""Unified token data fetcher from Binance Futures."""
import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx


@dataclass
class TokenMetrics:
    """Comprehensive token metrics from Binance Futures."""

    symbol: str
    price: float = 0.0
    price_change_24h: float = 0.0
    price_change_pct: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    volume_24h: float = 0.0
    volume_usdt: float = 0.0
    funding_rate: float = 0.0
    long_short_ratio: float = 0.0
    long_account_pct: float = 0.0
    short_account_pct: float = 0.0
    open_interest: float = 0.0
    liquidations_24h: float = 0.0
    market_cap: Optional[float] = None


class TokenAnalyzer:
    """Fetch and analyze token data from Binance Futures."""

    BASE_URL = "https://fapi.binance.com"

    def __init__(self, proxy_url: str = "") -> None:
        self.proxy_url = proxy_url

    def _client(self) -> httpx.AsyncClient:
        """Create an HTTP client with optional proxy."""
        if self.proxy_url:
            return httpx.AsyncClient(timeout=10, proxies={"all://": self.proxy_url})
        return httpx.AsyncClient(timeout=10)

    async def fetch_all(self, symbol: str) -> TokenMetrics:
        """Fetch all metrics for a token in parallel."""
        metrics = TokenMetrics(symbol=symbol.upper())

        async with self._client() as client:
            tasks = [
                self._fetch_24h_ticker(client, symbol, metrics),
                self._fetch_funding_rate(client, symbol, metrics),
                self._fetch_long_short_ratio(client, symbol, metrics),
                self._fetch_open_interest(client, symbol, metrics),
                self._fetch_liquidations(client, symbol, metrics),
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

        return metrics

    async def _fetch_24h_ticker(self, client: httpx.AsyncClient, symbol: str, metrics: TokenMetrics) -> None:
        """Fetch 24h ticker data: price, change, volume."""
        try:
            resp = await client.get(f"{self.BASE_URL}/fapi/v1/ticker/24hr", params={"symbol": f"{symbol}USDT"})
            if resp.status_code == 200:
                data = resp.json()
                metrics.price = float(data.get("lastPrice", 0))
                metrics.price_change_24h = float(data.get("priceChange", 0))
                metrics.price_change_pct = float(data.get("priceChangePercent", 0))
                metrics.high_24h = float(data.get("highPrice", 0))
                metrics.low_24h = float(data.get("lowPrice", 0))
                metrics.volume_24h = float(data.get("volume", 0))
                metrics.volume_usdt = float(data.get("quoteVolume", 0))
        except Exception:
            pass

    async def _fetch_funding_rate(self, client: httpx.AsyncClient, symbol: str, metrics: TokenMetrics) -> None:
        """Fetch current funding rate."""
        try:
            resp = await client.get(f"{self.BASE_URL}/fapi/v1/fundingRate", params={"symbol": f"{symbol}USDT", "limit": 1})
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list) and len(data) > 0:
                    metrics.funding_rate = float(data[0].get("fundingRate", 0))
        except Exception:
            pass

    async def _fetch_long_short_ratio(self, client: httpx.AsyncClient, symbol: str, metrics: TokenMetrics) -> None:
        """Fetch top traders long/short account ratio."""
        try:
            resp = await client.get(
                f"{self.BASE_URL}/futures/data/topLongShortAccountRatio",
                params={"symbol": f"{symbol}USDT", "period": "5m", "limit": 1},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list) and len(data) > 0:
                    item = data[0]
                    long_pct = float(item.get("longAccount", 0))
                    short_pct = float(item.get("shortAccount", 0))
                    metrics.long_account_pct = long_pct
                    metrics.short_account_pct = short_pct
                    if short_pct > 0:
                        metrics.long_short_ratio = long_pct / short_pct
                    else:
                        metrics.long_short_ratio = long_pct
        except Exception:
            pass

    async def _fetch_open_interest(self, client: httpx.AsyncClient, symbol: str, metrics: TokenMetrics) -> None:
        """Fetch open interest."""
        try:
            resp = await client.get(f"{self.BASE_URL}/fapi/v1/openInterest", params={"symbol": f"{symbol}USDT"})
            if resp.status_code == 200:
                data = resp.json()
                metrics.open_interest = float(data.get("openInterest", 0))
        except Exception:
            pass

    async def _fetch_liquidations(self, client: httpx.AsyncClient, symbol: str, metrics: TokenMetrics) -> None:
        """Fetch 24h liquidations."""
        try:
            from datetime import datetime, timedelta

            start_time = int((datetime.utcnow() - timedelta(hours=24)).timestamp() * 1000)
            resp = await client.get(
                f"{self.BASE_URL}/fapi/v1/allForceOrders",
                params={"symbol": f"{symbol}USDT", "startTime": start_time, "limit": 1000},
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    total = sum(float(order.get("executedQty", 0)) * float(order.get("avgPrice", 0)) for order in data)
                    metrics.liquidations_24h = total
        except Exception:
            pass

    def format_summary(self, metrics: TokenMetrics) -> str:
        """Format metrics into a human-readable summary."""
        lines = [
            f"**{metrics.symbol} Token Metrics**",
            "",
            f"**Price**: ${metrics.price:,.4f}",
            f"**24h Change**: {metrics.price_change_pct:+.2f}% (${metrics.price_change_24h:+.4f})",
            f"**24h High/Low**: ${metrics.high_24h:,.4f} / ${metrics.low_24h:,.4f}",
            f"**24h Volume**: {metrics.volume_24h:,.2f} ({metrics.volume_usdt:,.0f} USDT)",
            "",
            "**Contract Metrics**:",
            f"**Funding Rate**: {metrics.funding_rate * 100:.4f}%",
            f"**Long/Short Ratio**: {metrics.long_short_ratio:.2f} (Long: {metrics.long_account_pct * 100:.1f}%, Short: {metrics.short_account_pct * 100:.1f}%)",
            f"**Open Interest**: {metrics.open_interest:,.0f}",
            f"**24h Liquidations**: ${metrics.liquidations_24h:,.0f}",
        ]
        return "\n".join(lines)


token_analyzer = TokenAnalyzer()
