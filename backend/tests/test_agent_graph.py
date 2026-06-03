import pytest
from services.agent_graph import AgentGraph, AgentState


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
