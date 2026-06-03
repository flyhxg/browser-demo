import pytest
from services.tools.registry import registry, ToolNotFoundError


def test_registry_has_all_tools():
    assert "get_price" in registry
    assert "get_market_cap" in registry
    assert "get_funding_rate" in registry
    assert "scrape_binance_square" in registry
    assert "analyze_sentiment" in registry


def test_execute_unknown_tool_raises():
    import asyncio

    async def _run():
        with pytest.raises(ToolNotFoundError):
            await registry.execute("unknown_tool", {})

    asyncio.run(_run())
