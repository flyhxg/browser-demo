"""Agent execution graph: orchestrates intent analysis, tool selection, execution, and summarization."""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from services.llm_factory import create_llm
from services.tools.definitions import tools_list
from services.tools.registry import registry
from browser_use.llm.messages import UserMessage

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    """Mutable state carried through the graph."""
    user_message: str
    session_context: list[dict[str, Any]] = field(default_factory=list)
    selected_tools: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    thinking_steps: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    error: Optional[str] = None


class AgentGraph:
    """Agent state-machine for tool-calling workflow."""

    def __init__(self, event_callback: Optional[Callable[[str, dict[str, Any]], Awaitable[None]]] = None):
        self._event_callback = event_callback

    async def run(self, state: AgentState) -> AgentState:
        try:
            await self._analyze_intent(state)
            await self._select_tools(state)
            await self._execute_tools(state)
            await self._summarize(state)
        except Exception as e:
            logger.exception("Agent graph error")
            state.error = str(e)
        return state

    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._event_callback:
            await self._event_callback(event_type, data)

    async def _analyze_intent(self, state: AgentState) -> None:
        step = {"step": 1, "description": "Analyzing user intent..."}
        state.thinking_steps.append(step)
        await self._emit("thinking", step)

    async def _select_tools(self, state: AgentState) -> None:
        step = {"step": 2, "description": "Selecting tools based on user request..."}
        state.thinking_steps.append(step)
        await self._emit("thinking", step)

        llm = create_llm()
        tools_json = json.dumps(tools_list, ensure_ascii=False)
        prompt = (
            f"You are an AI assistant with access to tools. "
            f"Based on the user's message, select the appropriate tools to call. "
            f"Respond ONLY with a JSON array of objects, each with 'name' and 'arguments'.\n\n"
            f"User message: {state.user_message}\n\n"
            f"Available tools: {tools_json}\n\n"
            f"If no tools are needed, respond with an empty array []."
        )
        result = await llm.ainvoke([UserMessage(content=prompt)])
        raw = result.completion if hasattr(result, "completion") else str(result)
        try:
            selected = json.loads(raw)
            if isinstance(selected, list):
                state.selected_tools = selected
            else:
                state.selected_tools = []
        except json.JSONDecodeError:
            state.selected_tools = []

    async def _execute_tools(self, state: AgentState) -> None:
        if not state.selected_tools:
            return

        step = {"step": 3, "description": f"Executing {len(state.selected_tools)} tools..."}
        state.thinking_steps.append(step)
        await self._emit("thinking", step)

        async def run_tool(tool_def: dict[str, Any]) -> dict[str, Any]:
            name = tool_def.get("name", "")
            args = tool_def.get("arguments", {})
            await self._emit("tool_call_start", {"tool": name, "arguments": args})
            try:
                result = await registry.execute(name, args)
            except Exception as e:
                result = {"tool": name, "error": str(e)}
            await self._emit("tool_call_result", {"tool": name, "result": result})
            return result

        tasks = [run_tool(t) for t in state.selected_tools]
        state.tool_results = await asyncio.gather(*tasks, return_exceptions=True)

    async def _summarize(self, state: AgentState) -> None:
        if not state.tool_results:
            state.summary = "I couldn't determine which tools to use for your request."
            return

        step = {"step": 4, "description": "Summarizing results..."}
        state.thinking_steps.append(step)
        await self._emit("thinking", step)

        llm = create_llm()
        results_text = json.dumps(state.tool_results, ensure_ascii=False, indent=2)
        prompt = (
            f"You are an AI assistant. Summarize the following tool results into a concise, "
            f"helpful response for the user.\n\nUser request: {state.user_message}\n\n"
            f"Tool results:\n{results_text}\n\nSummary:"
        )
        result = await llm.ainvoke([UserMessage(content=prompt)])
        state.summary = result.completion if hasattr(result, "completion") else str(result)
