"""Tests for Binance Futures data source."""
import pytest

from services.datasources.binance_futures import (
    get_24h_ticker,
    get_funding_rate,
    get_long_short_ratio,
    get_liquidations,
    get_open_interest,
)


@pytest.mark.asyncio
async def test_get_24h_ticker():
    result = await get_24h_ticker("BTC")
    assert isinstance(result, dict)
    assert "price" in result
    assert "price_change_24h_pct" in result
    assert "volume_24h" in result


@pytest.mark.asyncio
async def test_get_funding_rate():
    result = await get_funding_rate("BTC")
    assert isinstance(result, dict)
    assert "funding_rate" in result
    assert "funding_time" in result


@pytest.mark.asyncio
async def test_get_open_interest():
    result = await get_open_interest("BTC")
    assert isinstance(result, dict)
    assert "open_interest" in result
    assert "oi_time" in result


@pytest.mark.asyncio
async def test_get_long_short_ratio():
    result = await get_long_short_ratio("BTC")
    assert isinstance(result, dict)
    assert "long_short_ratio" in result
    assert "long_account_pct" in result
    assert "short_account_pct" in result


@pytest.mark.asyncio
async def test_get_liquidations():
    result = await get_liquidations("BTC")
    assert isinstance(result, dict)
    assert "liquidations_24h" in result
