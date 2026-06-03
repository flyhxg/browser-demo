"""Technical indicators data source: klines fetcher + RSI + support/resistance."""
from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

BINANCE_FAPI = "https://fapi.binance.com"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
async def get_klines(
    symbol: str,
    interval: str = "1h",
    limit: int = 100,
) -> list[dict]:
    """Fetch klines (candlestick data) from Binance Futures API.

    Returns a list of dicts with keys: open_time, open, high, low, close, volume.
    """
    url = f"{BINANCE_FAPI}/fapi/v1/klines"
    params = {
        "symbol": f"{symbol.upper()}USDT",
        "interval": interval,
        "limit": limit,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    result = []
    for item in data:
        result.append({
            "open_time": int(item[0]),
            "open": float(item[1]),
            "high": float(item[2]),
            "low": float(item[3]),
            "close": float(item[4]),
            "volume": float(item[5]),
        })
    return result


def calculate_rsi(klines: list, period: int = 14) -> float | None:
    """Calculate RSI using pandas-ta. Returns last RSI value or None."""
    try:
        import pandas as pd  # noqa: F401
        import pandas_ta as ta  # noqa: F401
    except ImportError:
        return None

    if len(klines) < period + 1:
        return None

    df = pd.DataFrame(klines)
    rsi_series = ta.rsi(df["close"], length=period)
    if rsi_series is None or rsi_series.empty:
        return None
    return float(rsi_series.iloc[-1])


def calculate_support_resistance(klines: list, lookback: int = 20) -> dict:
    """Calculate support and resistance levels from recent klines.

    Returns {"support": min_low, "resistance": max_high}.
    If insufficient data, returns {"support": None, "resistance": None}.
    """
    if len(klines) < lookback:
        return {"support": None, "resistance": None}

    recent = klines[-lookback:]
    lows = [candle["low"] for candle in recent]
    highs = [candle["high"] for candle in recent]
    return {"support": min(lows), "resistance": max(highs)}
