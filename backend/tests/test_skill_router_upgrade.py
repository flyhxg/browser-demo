import pytest
from unittest.mock import AsyncMock, patch
from services.skill_router import SkillRouter


@pytest.mark.asyncio
async def test_route_uses_function_calling_when_tools_selected():
    router = SkillRouter()
    with patch("services.skill_router.AgentGraph") as MockGraph:
        mock_graph = AsyncMock()
        mock_graph.run.return_value.selected_tools = [
            {"name": "get_price", "arguments": {"symbol": "BTC"}}
        ]
        mock_graph.run.return_value.summary = "BTC is $50,000"
        MockGraph.return_value = mock_graph

        result = await router.route("Check BTC price", None)
        assert result["type"] == "general"
        assert result["output"] == "BTC is $50,000"


@pytest.mark.asyncio
async def test_route_fallback_to_keywords_when_no_tools():
    router = SkillRouter()
    with patch("services.skill_router.AgentGraph") as MockGraph:
        mock_graph = AsyncMock()
        mock_graph.run.return_value.selected_tools = []
        mock_graph.run.return_value.summary = ""
        MockGraph.return_value = mock_graph

        result = await router.route("price", None)
        assert result["type"] == "market_data"
