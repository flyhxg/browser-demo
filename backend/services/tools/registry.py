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
    import httpx
    symbol = params.get("symbol", "").upper()
    # Use Binance Futures (合约) for accurate real-time price
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Convert symbol to Binance Futures format (e.g. BTC -> BTCUSDT)
            binance_symbol = f"{symbol}USDT"
            resp = await client.get(
                "https://fapi.binance.com/fapi/v1/ticker/price",
                params={"symbol": binance_symbol}
            )
            if resp.status_code == 200:
                data = resp.json()
                price = data.get("price")
                if price:
                    return {
                        "tool": "get_price",
                        "symbol": symbol,
                        "source": "binance_futures",
                        "result": {
                            "symbol": symbol,
                            "price_usd": float(price),
                            "source": "binance_futures",
                        },
                    }
    except Exception:
        pass

    # Fallback to CoinGecko
    from services.datasources.coingecko import CoinGeckoSource
    source = CoinGeckoSource()
    result = await source.get_token_price(symbol)
    return {"tool": "get_price", "symbol": symbol, "result": result}


async def _get_market_cap(params: dict[str, Any]) -> dict[str, Any]:
    from services.datasources.coingecko import CoinGeckoSource
    symbol = params.get("symbol", "").upper()
    source = CoinGeckoSource()
    result = await source.search(f"{symbol} market cap")
    # 过滤只保留请求的 symbol，减少数据量避免 LLM 超时
    if "data" in result:
        result["data"] = [item for item in result["data"] if item.get("symbol", "").upper() == symbol]
    return {"tool": "get_market_cap", "symbol": symbol, "result": result}


async def _get_funding_rate(params: dict[str, Any]) -> dict[str, Any]:
    from services.datasources.okx import OKXSource
    symbol = params.get("symbol", "")
    exchange = params.get("exchange", "okx")
    source = OKXSource()
    result = await source.get_funding_rate(symbol)
    return {"tool": "get_funding_rate", "symbol": symbol, "exchange": exchange, "result": result}


async def _scrape_binance_square(params: dict[str, Any]) -> dict[str, Any]:
    limit = params.get("limit", 20)
    use_browser = params.get("use_browser", False)

    if not use_browser:
        return {
            "tool": "scrape_binance_square",
            "limit": limit,
            "result": {
                "status": "ok",
                "source": "simulated",
                "posts": [
                    {
                        "id": f"post_{i}",
                        "author": f"user_{i}",
                        "content": f"Sample post {i} about crypto market trends...",
                        "mentions": ["BTC", "ETH"],
                        "likes": i * 10,
                        "created_at": "2025-01-01T00:00:00Z",
                    }
                    for i in range(1, min(limit + 1, 6))
                ],
            },
        }

    import os
    from browser_use import Agent, BrowserSession
    from services.llm_factory import create_llm, ProviderNotConfiguredError
    from services.config_store import get_provider_config

    try:
        llm = create_llm()
    except (ProviderNotConfiguredError, ValueError) as e:
        return {
            "tool": "scrape_binance_square",
            "limit": limit,
            "result": {
                "status": "error",
                "error": f"LLM not configured: {e}",
            },
        }

    config = get_provider_config() or {}
    browser_mode = config.get("browser_mode", "local")
    browser_use_api_key = config.get("browser_use_api_key", "")
    env_api_key = os.getenv("BROWSER_USE_API_KEY")
    if env_api_key:
        browser_use_api_key = env_api_key
        browser_mode = "cloud"

    browser_session = None
    try:
        if browser_use_api_key:
            os.environ["BROWSER_USE_API_KEY"] = browser_use_api_key
            browser_session = BrowserSession(use_cloud=True, cloud_browser=True)
        else:
            browser_session = BrowserSession()

        task = (
            f"Go to https://www.binance.com/en/square and scrape the latest {limit} posts. "
            "For each post, extract: post ID, author, content, likes, and timestamp. "
            "Return the results in JSON format."
        )

        agent = Agent(
            task=task,
            llm=llm,
            browser_session=browser_session,
            use_thinking=False,
        )

        await agent.run()

        result_text = ""
        if hasattr(agent, "history") and agent.history:
            result_text = agent.history.final_result() or ""

        return {
            "tool": "scrape_binance_square",
            "limit": limit,
            "result": {
                "status": "ok",
                "source": "browser",
                "posts": result_text,
            },
        }
    except Exception as e:
        return {
            "tool": "scrape_binance_square",
            "limit": limit,
            "result": {
                "status": "error",
                "error": str(e),
            },
        }
    finally:
        if browser_session:
            await browser_session.close()


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
