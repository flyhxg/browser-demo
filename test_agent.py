import asyncio
import json
import sys
sys.path.insert(0, "backend")

from services.agent_graph import AgentGraph, AgentState

async def test_agent_graph():
    """Test AgentGraph directly without WebSocket."""
    print("Testing AgentGraph...")

    state = AgentState(user_message="Check BTC price")
    graph = AgentGraph()

    result = await graph.run(state)

    print(f"Selected tools: {result.selected_tools}")
    print(f"Tool results: {json.dumps(result.tool_results, indent=2)[:500]}")
    print(f"Summary: {result.summary[:200] if result.summary else 'N/A'}")
    print(f"Thinking steps: {result.thinking_steps}")

if __name__ == "__main__":
    asyncio.run(test_agent_graph())
