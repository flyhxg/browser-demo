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
        result = await asyncio.wait_for(llm.ainvoke([UserMessage(content=prompt)]), timeout=20.0)
        raw = result.completion if hasattr(result, "completion") and result.completion else (result.content if hasattr(result, "content") else str(result))
        selected = self._extract_json_from_text(raw)
        if isinstance(selected, list):
            state.selected_tools = selected
        else:
            state.selected_tools = []

    @staticmethod
    def _extract_json_from_text(text: str) -> Any:
        """Extract JSON from text that may contain thinking text prepended."""
        text = text.strip()
        # Find first '[' or '{'
        start_idx = -1
        for i, ch in enumerate(text):
            if ch in ('[', '{'):
                start_idx = i
                break
        if start_idx == -1:
            return []
        # Find matching end bracket
        stack = []
        end_idx = len(text)
        for i in range(start_idx, len(text)):
            ch = text[i]
            if ch in ('[', '{'):
                stack.append(ch)
            elif ch in (']', '}'):
                if not stack:
                    break
                stack.pop()
                if not stack:
                    end_idx = i + 1
                    break
        json_str = text[start_idx:end_idx]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return []

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
            step = {"step": 4, "description": "Generating direct response..."}
            state.thinking_steps.append(step)
            await self._emit("thinking", step)

            llm = create_llm()
            prompt = (
                f"You are an AI assistant. Please respond to the user's message directly and helpfully.\n\n"
                f"User message: {state.user_message}\n\n"
                f"Response:"
            )
            try:
                result = await asyncio.wait_for(llm.ainvoke([UserMessage(content=prompt)]), timeout=25.0)
                state.summary = result.completion if hasattr(result, "completion") and result.completion else (result.content if hasattr(result, "content") else str(result))
            except asyncio.TimeoutError:
                state.summary = "抱歉，服务响应超时，请稍后再试。"
            return

        step = {"step": 4, "description": "Summarizing results..."}
        state.thinking_steps.append(step)
        await self._emit("thinking", step)

        llm = create_llm()
        results_text = json.dumps(state.tool_results, ensure_ascii=False, indent=2)
        # 限制结果长度，避免 token 过多导致超时
        if len(results_text) > 3000:
            results_text = results_text[:3000] + "...\n[数据已截断]"
        prompt = (
            f"请根据以下工具结果，用简洁的语言回答用户的问题。\n\n"
            f"用户问题: {state.user_message}\n\n"
            f"工具结果:\n{results_text}\n\n"
            f"回答:"
        )
        try:
            result = await asyncio.wait_for(llm.ainvoke([UserMessage(content=prompt)]), timeout=25.0)
            state.summary = result.completion if hasattr(result, "completion") and result.completion else (result.content if hasattr(result, "content") else str(result))
        except asyncio.TimeoutError:
            # 超时 fallback：直接返回工具结果的简要信息
            fallback = []
            for r in state.tool_results:
                if isinstance(r, dict):
                    tool_name = r.get("tool", "")
                    tool_result = r.get("result", {})
                    if tool_name == "get_price":
                        symbol = tool_result.get("symbol", "")
                        data = tool_result.get("data", {})
                        price = ""
                        for k, v in data.items():
                            if isinstance(v, dict) and "usd" in v:
                                price = f"{v['usd']} USD"
                                break
                        if price:
                            fallback.append(f"{symbol} 当前价格: {price}")
                    elif tool_name == "get_market_cap":
                        symbol = tool_result.get("symbol", "")
                        data = tool_result.get("data", {})
                        if isinstance(data, list) and len(data) > 0:
                            item = data[0]
                            mc = item.get("market_cap", "")
                            if mc:
                                fallback.append(f"{symbol} 市值: {mc:,.0f} USD")
                    elif tool_name == "get_funding_rate":
                        symbol = tool_result.get("symbol", "")
                        data = tool_result.get("data", {})
                        if isinstance(data, list) and len(data) > 0:
                            item = data[0]
                            fr = item.get("fundingRate", "")
                            if fr:
                                fallback.append(f"{symbol} 资金费率: {fr}")
            if fallback:
                state.summary = "\n".join(fallback) + "\n\n（服务响应较慢，以上为工具返回的原始数据）"
            else:
                state.summary = "抱歉，服务响应超时，但工具已执行完毕。请重试或稍后再问。"
