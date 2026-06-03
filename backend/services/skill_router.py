"""Intent-based skill router for the AI Trading Agent."""
from typing import Any

from services.agent_graph import AgentGraph, AgentState


class SkillRouter:
    """Routes user messages to appropriate skills using Function Calling."""

    async def route(self, message: str, ws: Any) -> dict[str, Any]:
        """Route a user message using Function Calling via AgentGraph."""
        state = AgentState(user_message=message)
        graph = AgentGraph()
        result = await graph.run(state)

        if result.selected_tools and result.summary:
            return {
                "type": "general",
                "action": "chat",
                "output": result.summary,
                "data": {},
            }

        return {
            "type": "general",
            "action": "chat",
            "output": "I couldn't process your request. Please try again.",
            "data": {},
        }


skill_router = SkillRouter()
