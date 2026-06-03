"""Intent-based skill router for the AI Trading Agent."""
import asyncio
import json
import logging
from typing import Any

from services.llm_factory import create_llm
from services.agent_graph import AgentGraph, AgentState

logger = logging.getLogger(__name__)


class SkillRouter:
    """Routes user messages to appropriate skills based on intent."""

    def __init__(self):
        self._intent_cache: dict[str, str] = {}

    async def route(self, message: str, ws: Any) -> dict[str, Any]:
        """Route a user message to the appropriate skill.

        First tries Function Calling via AgentGraph, then falls back to
        keyword-based routing.
        """
        try:
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
        except Exception as e:
            logger.warning(f"[SkillRouter] AgentGraph routing failed: {e}")

        # Fallback to keyword-based routing
        return await self._route_by_keyword(message, ws)

    async def _route_by_keyword(self, message: str, ws: Any) -> dict[str, Any]:
        """Original keyword-based routing logic."""
        intent = await self._classify_intent(message)
        logger.info(f"[SkillRouter] Intent: {intent} for: {message[:50]}...")

        if intent == "browser":
            return {"type": "browser", "action": "run", "output": "Launching browser task..."}
        elif intent == "market_data":
            return await self._handle_market_data(message)
        elif intent == "trading":
            return await self._handle_trading(message)
        elif intent == "signal_analysis":
            return await self._handle_signal_analysis(message)
        elif intent == "workflow":
            return await self._handle_workflow(message)
        else:
            return await self._handle_general_chat(message)

    async def _classify_intent(self, message: str) -> str:
        """Classify user intent using keyword matching + LLM fallback."""
        msg_lower = message.lower()

        # Quick keyword matching
        browser_keywords = [
            "go to", "navigate", "open ", "visit ", "click", "login", "sign in",
            "browse", "search google", "search for", "go on", "打开网页",
            "访问", "登录", "浏览", "点击", "扫码", "scan qr"
        ]
        if any(k in msg_lower for k in browser_keywords):
            return "browser"

        market_keywords = [
            "price", "market cap", "marketcap", "trending", "top tokens",
            "funding rate", "volume", "market data", "coin", "token price",
            "bitcoin", "ethereum", "btc", "eth", "价格", "市值", "行情",
            "走势", "涨跌幅", "funding"
        ]
        if any(k in msg_lower for k in market_keywords):
            return "market_data"

        trading_keywords = [
            "trade", "buy", "sell", "position", "order", "execute",
            "open long", "close position", "tp", "sl", "leverage",
            "仓位", "持仓", "下单", "平仓", "止盈", "止损", "开仓",
            "做多", "做空", "交易"
        ]
        if any(k in msg_lower for k in trading_keywords):
            return "trading"

        signal_keywords = [
            "signal", "sentiment", "analyze", "scan binance", "binance square",
            "scrape", "analyze signal", "bullish", "bearish", "情绪", "信号",
            "分析信号", "扫描"
        ]
        if any(k in msg_lower for k in signal_keywords):
            return "signal_analysis"

        workflow_keywords = [
            "workflow", "auto scan", "auto execute", "scheduled task",
            "automation", "config", "setting", "工作流", "定时任务",
            "自动扫描", "配置"
        ]
        if any(k in msg_lower for k in workflow_keywords):
            return "workflow"

        return "general"

    async def _handle_market_data(self, message: str) -> dict[str, Any]:
        """Handle market data queries."""
        try:
            from services.datasources.coingecko import CoinGeckoSource
            from services.datasources.okx import OKXSource
            from services.datasources.hyperliquid import HyperliquidSource

            msg_lower = message.lower()

            # Determine which data source to use
            if "funding" in msg_lower or "okx" in msg_lower:
                source = OKXSource()
                result = await source.search(message)
            elif "hyperliquid" in msg_lower or "hl" in msg_lower:
                source = HyperliquidSource()
                result = await source.search(message)
            else:
                source = CoinGeckoSource()
                result = await source.search(message)

            return {
                "type": "market_data",
                "action": "query",
                "output": self._format_market_data(result),
                "data": result,
            }
        except Exception as e:
            logger.error(f"[SkillRouter] Market data error: {e}")
            return {
                "type": "market_data",
                "action": "query",
                "output": f"Error fetching market data: {e}",
                "data": {},
            }

    def _format_market_data(self, result: dict[str, Any]) -> str:
        """Format market data for display."""
        data_type = result.get("type", "")
        data = result.get("data", [])

        if not data:
            return "No market data found."

        if data_type == "trending":
            lines = ["**Trending Tokens**"]
            for item in data[:10]:
                lines.append(f"{item['rank']}. {item['name']} ({item['symbol']}) - Rank #{item['market_cap_rank']}")
            return "\n".join(lines)
        elif data_type == "top_market_cap":
            lines = ["**Top Tokens by Market Cap**"]
            for item in data[:10]:
                lines.append(f"{item['rank']}. {item['name']} ({item['symbol']}) - ${item['current_price']:,.2f} ({item['price_change_24h']:.2f}%)")
            return "\n".join(lines)
        else:
            return f"Found {len(data)} results. Data: {json.dumps(data[:3], indent=2)}"

    async def _handle_trading(self, message: str) -> dict[str, Any]:
        """Handle trading commands."""
        return {
            "type": "trading",
            "action": "info",
            "output": "Trading commands should be executed through the Trading page. Navigate to Trading > Positions to manage your trades.",
            "data": {},
        }

    async def _handle_signal_analysis(self, message: str) -> dict[str, Any]:
        """Handle signal analysis commands."""
        return {
            "type": "signal_analysis",
            "action": "info",
            "output": "Signal analysis is available on the Trading page. Go to Trading > Signals to view and analyze signals.",
            "data": {},
        }

    async def _handle_workflow(self, message: str) -> dict[str, Any]:
        """Handle workflow configuration commands."""
        return {
            "type": "workflow",
            "action": "info",
            "output": "Workflow settings can be configured on the Workflow page. Set up auto-scan, auto-execute, and trading parameters there.",
            "data": {},
        }

    async def _handle_general_chat(self, message: str) -> dict[str, Any]:
        """Handle general chat with LLM."""
        try:
            llm = create_llm()
            from browser_use.llm.messages import UserMessage
            result = await llm.ainvoke([UserMessage(content=message)])
            output = result.content if hasattr(result, "content") else str(result)
            return {
                "type": "general",
                "action": "chat",
                "output": output,
                "data": {},
            }
        except Exception as e:
            logger.error(f"[SkillRouter] General chat error: {e}")
            return {
                "type": "general",
                "action": "chat",
                "output": f"I'm your AI Trading Agent. I can help with market data, trading, signal analysis, and browser tasks. What would you like to do?",
                "data": {},
            }


skill_router = SkillRouter()
