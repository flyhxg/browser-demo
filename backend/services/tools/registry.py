"""Tool registry: maps tool names to executor coroutines."""
import asyncio
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class ToolNotFoundError(Exception):
    """Raised when an unregistered tool is requested."""


class ToolRegistry:
    """Registry for tool definitions and their executors."""

    def __init__(self) -> None:
        self._executors: dict[str, Callable[[dict[str, Any]], Awaitable[Any]]] = {}

    def register(
        self,
        name: str,
        executor: Callable[[dict[str, Any]], Awaitable[Any]],
    ) -> None:
        self._executors[name] = executor

    async def execute(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        if name not in self._executors:
            raise ToolNotFoundError(f"Tool '{name}' not found")
        return await self._executors[name](params)

    def __contains__(self, name: str) -> bool:
        return name in self._executors


registry = ToolRegistry()


# ---- Executor implementations ----

async def _get_price(params: dict[str, Any]) -> dict[str, Any]:
    from services.datasources.coingecko import CoinGeckoSource
    symbol = params.get("symbol", "")
    source = CoinGeckoSource()
    result = await source.search(f"{symbol} price")
    return {"tool": "get_price", "symbol": symbol, "result": result}


async def _get_market_cap(params: dict[str, Any]) -> dict[str, Any]:
    from services.datasources.coingecko import CoinGeckoSource
    symbol = params.get("symbol", "")
    source = CoinGeckoSource()
    result = await source.search(f"{symbol} market cap")
    return {"tool": "get_market_cap", "symbol": symbol, "result": result}


async def _get_funding_rate(params: dict[str, Any]) -> dict[str, Any]:
    from services.datasources.okx import OKXSource
    symbol = params.get("symbol", "")
    exchange = params.get("exchange", "okx")
    source = OKXSource()
    result = await source.search(f"{symbol} funding rate")
    return {"tool": "get_funding_rate", "symbol": symbol, "exchange": exchange, "result": result}


async def _scrape_binance_square(params: dict[str, Any]) -> dict[str, Any]:
    limit = params.get("limit", 20)
    # BinanceSquareScraper has no search() method; return a placeholder
    return {
        "tool": "scrape_binance_square",
        "limit": limit,
        "result": {"status": "not_implemented", "message": "BinanceSquareScraper.search() not available"},
    }


async def _analyze_sentiment(params: dict[str, Any]) -> dict[str, Any]:
    from services.llm_factory import create_llm
    from browser_use.llm.messages import UserMessage
    text = params.get("text", "")
    llm = create_llm()
    prompt = f"Analyze the sentiment of the following text. Respond with one word: bullish, bearish, or neutral.\n\nText: {text}"
    result = await llm.ainvoke([UserMessage(content=prompt)])
    sentiment = result.content if hasattr(result, "content") else str(result)
    return {"tool": "analyze_sentiment", "text_preview": text[:100], "sentiment": sentiment.strip()}


# Register all tools
registry.register("get_price", _get_price)
registry.register("get_market_cap", _get_market_cap)
registry.register("get_funding_rate", _get_funding_rate)
registry.register("scrape_binance_square", _scrape_binance_square)
registry.register("analyze_sentiment", _analyze_sentiment)
