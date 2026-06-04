import pytest
from unittest.mock import AsyncMock, patch

from services.agent_graph import AgentGraph, AgentState, _default_source_for


def test_agent_state_initial():
    state = AgentState(user_message="Check BTC price")
    assert state.user_message == "Check BTC price"
    assert state.selected_tools == []
    assert state.tool_results == []
    assert state.thinking_steps == []


@pytest.mark.asyncio
async def test_graph_has_run_method():
    graph = AgentGraph()
    assert hasattr(graph, "run")


def test_default_source_for_known_tools():
    assert _default_source_for("get_price") == {
        "label": "Binance Futures",
        "url": "https://www.binance.com/en/futures",
    }
    assert _default_source_for("get_market_cap")["label"] == "CoinGecko"
    assert _default_source_for("get_funding_rate")["label"] == "OKX"
    assert _default_source_for("scrape_binance_square")["label"] == "Binance Square"
    assert _default_source_for("analyze_sentiment") == {"label": "LLM", "url": ""}


def test_default_source_for_unknown_tool_falls_back():
    assert _default_source_for("future_tool") == {"label": "future_tool", "url": ""}


@pytest.mark.asyncio
async def test_execute_tools_emits_source_on_tool_call_start():
    graph = AgentGraph()
    state = AgentState(user_message="BTC price")
    state.selected_tools = [{"name": "get_price", "arguments": {"symbol": "BTC"}}]
    captured: list[tuple[str, dict]] = []

    async def cb(event_type: str, data: dict) -> None:
        captured.append((event_type, data))

    graph._event_callback = cb
    with patch("services.agent_graph.registry.execute", new=AsyncMock(return_value={"price_usd": 1})):
        await graph._execute_tools(state)

    starts = [d for et, d in captured if et == "tool_call_start"]
    assert len(starts) == 1
    assert starts[0]["source"] == {
        "label": "Binance Futures",
        "url": "https://www.binance.com/en/futures",
    }
    assert starts[0]["tool"] == "get_price"
    assert starts[0]["arguments"] == {"symbol": "BTC"}


@pytest.mark.asyncio
async def test_execute_tools_emits_source_for_unknown_tool_with_safe_fallback():
    graph = AgentGraph()
    state = AgentState(user_message="x")
    state.selected_tools = [{"name": "future_tool", "arguments": {}}]
    captured: list[tuple[str, dict]] = []

    async def cb(event_type: str, data: dict) -> None:
        captured.append((event_type, data))

    graph._event_callback = cb
    with patch("services.agent_graph.registry.execute", new=AsyncMock(return_value={})):
        await graph._execute_tools(state)

    starts = [d for et, d in captured if et == "tool_call_start"]
    assert starts[0]["source"] == {"label": "future_tool", "url": ""}
