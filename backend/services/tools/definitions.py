"""Tool definitions using JSON Schema."""
from typing import Any

get_price_tool: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_price",
        "description": "Get the current price of a cryptocurrency token",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The token symbol, e.g. BTC, ETH, SOL",
                }
            },
            "required": ["symbol"],
        },
    },
}

get_market_cap_tool: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_market_cap",
        "description": "Get the current market capitalization of a cryptocurrency token",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The token symbol, e.g. BTC, ETH, SOL",
                }
            },
            "required": ["symbol"],
        },
    },
}

get_funding_rate_tool: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_funding_rate",
        "description": "Get the funding rate for a token on perpetual futures markets (e.g. OKX, Hyperliquid)",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The token symbol, e.g. BTC, ETH, SOL",
                },
                "exchange": {
                    "type": "string",
                    "enum": ["okx", "hyperliquid"],
                    "description": "Exchange to query (optional, defaults to okx)",
                },
            },
            "required": ["symbol"],
        },
    },
}

scrape_binance_square_tool: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "scrape_binance_square",
        "description": "Scrape recent posts from Binance Square (feed/social) for token mentions and sentiment. Set use_browser=true when real-time data is required.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of posts to scrape (default 20)",
                },
                "use_browser": {
                    "type": "boolean",
                    "description": "Whether to use a real browser to scrape live data (default false, uses simulated data)",
                }
            },
            "required": [],
        },
    },
}

analyze_sentiment_tool: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "analyze_sentiment",
        "description": "Analyze sentiment of provided text using LLM (bullish, bearish, neutral)",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to analyze",
                }
            },
            "required": ["text"],
        },
    },
}

tools_list = [
    get_price_tool,
    get_market_cap_tool,
    get_funding_rate_tool,
    scrape_binance_square_tool,
    analyze_sentiment_tool,
]
