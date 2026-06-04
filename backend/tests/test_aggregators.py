"""Tests for OnchainAggregator and DerivativesAggregator."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_onchain_aggregator_combines_whale_and_arkham():
    """OnchainAggregator.fetch must combine whale + arkham results."""
    from services.datasources.aggregators import OnchainAggregator

    whale = AsyncMock()
    whale.get_recent_transfers = AsyncMock(return_value=[
        {"amount_usd": 10_000_000, "from": "unknown", "to": "binance", "timestamp": "2026-06-03T14:00:00Z"},
    ])
    arkham = AsyncMock()
    arkham.get_flows = AsyncMock(return_value=[
        {"amount_usd": 7_000_000, "from": "coinbase", "to": "unknown", "timestamp": "2026-06-03T15:00:00Z"},
    ])

    agg = OnchainAggregator(whale=whale, arkham=arkham)
    events = await agg.fetch("BTC", "24h")

    assert len(events) == 2
    types = sorted([e["type"] for e in events])
    assert types == ["whale", "whale"]


@pytest.mark.asyncio
async def test_derivatives_aggregator_returns_liquidations_and_funding():
    """DerivativesAggregator.fetch must include both liquidation and funding events."""
    from services.datasources.aggregators import DerivativesAggregator

    binance = AsyncMock()
    binance.get_liquidations = AsyncMock(return_value=[
        {"side": "long", "amount_usd": 2_000_000, "timestamp": "2026-06-03T14:30:00Z"},
    ])
    binance.get_funding_rate = AsyncMock(return_value={
        "rate": 0.0015, "timestamp": "2026-06-03T15:00:00Z"
    })
    okx = AsyncMock()
    okx.get_funding_rate = AsyncMock(return_value={
        "rate": 0.0008, "timestamp": "2026-06-03T15:00:00Z"
    })

    agg = DerivativesAggregator(binance=binance, okx=okx)
    events = await agg.fetch("BTC", "24h")

    types = [e["type"] for e in events]
    assert "liquidation" in types
    # Funding shift only included if |rate| > 0.001 (0.1%)
    funding_events = [e for e in events if e["type"] == "funding_shift"]
    assert len(funding_events) >= 1
