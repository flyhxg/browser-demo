"""End-to-end integration test for the function calling flow."""
import pytest
from unittest.mock import AsyncMock, patch
from services.agent_graph import AgentGraph, AgentState


@pytest.mark.asyncio
async def test_e2e_function_calling_flow():
    """Simulate a full agent graph run with mocked LLM."""
    events = []

    async def capture_event(event_type, data):
        events.append((event_type, data))

    graph = AgentGraph(event_callback=capture_event)
    state = AgentState(user_message="Check BTC price")

    with patch("services.agent_graph.create_llm") as mock_create_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value.content = (
            '[{"name": "get_price", "arguments": {"symbol": "BTC"}}]'
        )
        mock_create_llm.return_value = mock_llm

        result = await graph.run(state)

    assert result.selected_tools
    assert result.summary
    assert any(e[0] == "thinking" for e in events)
    assert any(e[0] == "tool_call_start" for e in events)
    assert any(e[0] == "tool_call_result" for e in events)
