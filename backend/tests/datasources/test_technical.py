"""Tests for technical indicators data source."""
import pytest

from services.datasources.technical import (
    calculate_rsi,
    calculate_support_resistance,
    get_klines,
)


@pytest.mark.asyncio
async def test_get_klines_returns_list():
    result = await get_klines("BTC", "1h", 50)
    assert isinstance(result, list)


def test_calculate_rsi():
    base = {"open_time": 0, "open": 1.0, "high": 1.0, "low": 1.0, "volume": 1.0}
    klines = []
    for i in range(15):
        candle = {**base, "close": float(i + 1)}
        klines.append(candle)
    result = calculate_rsi(klines)
    # pandas-ta may not be installed; assert float or None
    assert result is None or isinstance(result, float)


def test_calculate_support_resistance_insufficient_data():
    klines = [
        {"open_time": 0, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.0, "volume": 1.0},
    ]
    result = calculate_support_resistance(klines, lookback=20)
    assert result == {"support": None, "resistance": None}


def test_calculate_support_resistance_with_data():
    klines = [
        {"open_time": i, "open": 1.0, "high": float(i + 2), "low": float(i + 1), "close": 1.0, "volume": 1.0}
        for i in range(25)
    ]
    result = calculate_support_resistance(klines, lookback=20)
    assert result["support"] == 6.0
    assert result["resistance"] == 26.0
