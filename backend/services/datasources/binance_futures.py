"""Binance Futures data source implementation."""
import asyncio
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError

BINANCE_FAPI = "https://fapi.binance.com"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
async def _fetch(client: httpx.AsyncClient, url: str, params: dict | None = None) -> dict:
    """Fetch JSON from Binance Futures API with retry."""
    resp = await client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


async def get_24h_ticker(symbol: str) -> dict:
    """Fetch 24h ticker data for a symbol from Binance Futures."""
    async with httpx.AsyncClient(base_url=BINANCE_FAPI, timeout=30) as client:
        data = await _fetch(client, "/fapi/v1/ticker/24hr", params={"symbol": f"{symbol.upper()}USDT"})
    return {
        "price": float(data["lastPrice"]),
        "price_change_24h_pct": float(data["priceChangePercent"]),
        "volume_24h": float(data["volume"]),
    }


async def get_funding_rate(symbol: str) -> dict:
    """Fetch latest funding rate for a symbol from Binance Futures."""
    async with httpx.AsyncClient(base_url=BINANCE_FAPI, timeout=30) as client:
        payload = await _fetch(
            client,
            "/fapi/v1/fundingRate",
            params={"symbol": f"{symbol.upper()}USDT", "limit": 1},
        )
    if not payload:
        return {"funding_rate": 0.0, "funding_time": 0}
    latest = payload[0]
    return {
        "funding_rate": float(latest["fundingRate"]),
        "funding_time": int(latest["fundingTime"]),
    }


async def get_open_interest(symbol: str) -> dict:
    """Fetch open interest for a symbol from Binance Futures."""
    async with httpx.AsyncClient(base_url=BINANCE_FAPI, timeout=30) as client:
        data = await _fetch(
            client,
            "/fapi/v1/openInterest",
            params={"symbol": f"{symbol.upper()}USDT"},
        )
    return {
        "open_interest": float(data["openInterest"]),
        "oi_time": int(data["time"]),
    }


async def get_long_short_ratio(symbol: str, period: str = "5m") -> dict:
    """Fetch global long/short account ratio for a symbol from Binance Futures."""
    async with httpx.AsyncClient(base_url=BINANCE_FAPI, timeout=30) as client:
        payload = await _fetch(
            client,
            "/futures/data/globalLongShortAccountRatio",
            params={"symbol": f"{symbol.upper()}USDT", "period": period, "limit": 1},
        )
    if not payload:
        return {
            "long_short_ratio": 0.0,
            "long_account_pct": 0.0,
            "short_account_pct": 0.0,
        }
    latest = payload[0]
    return {
        "long_short_ratio": float(latest["longShortRatio"]),
        "long_account_pct": float(latest["longAccount"]),
        "short_account_pct": float(latest["shortAccount"]),
    }


async def get_liquidations(symbol: str) -> dict:
    """Fetch liquidation data for a symbol from Binance Futures."""
    async with httpx.AsyncClient(base_url=BINANCE_FAPI, timeout=30) as client:
        try:
            payload = await _fetch(
                client,
                "/fapi/v1/forceOrders",
                params={
                    "symbol": f"{symbol.upper()}USDT",
                    "limit": 100,
                    "autoCloseType": "LIQUIDATION",
                },
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 401):
                return {"liquidations_24h": 0.0, "note": "Requires special permissions"}
            raise
        except RetryError as exc:
            last_exc = exc.last_attempt.exception()
            if isinstance(last_exc, httpx.HTTPStatusError) and last_exc.response.status_code in (400, 401):
                return {"liquidations_24h": 0.0, "note": "Requires special permissions"}
            raise
    total = sum(float(item["executedQty"]) for item in payload)
    return {"liquidations_24h": total}
