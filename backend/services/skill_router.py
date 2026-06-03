"""Intent-based skill router for the AI Trading Agent."""
import re
from typing import Any

from services.agent_graph import AgentGraph, AgentState
from services.token_analyzer import token_analyzer
from services.llm_factory import create_llm
from browser_use.llm.messages import UserMessage
import asyncio
import json


class SkillRouter:
    """Routes user messages to appropriate skills."""

    # Keywords that indicate a token/coin query
    TOKEN_KEYWORDS = [
        "价格", "price", "行情", "走势", "涨", "跌", "how much", "cost",
        "代币", "token", "coin", "crypto", "bitcoin", "ethereum", "btc", "eth",
        "做多", "做空", "long", "short", "多空", "funding", "funding rate",
        "市值", "marketcap", "market cap", "volume", "成交量", "持仓",
        "liquidation", "清算", "futures", "合约", "永续", "perpetual",
    ]

    @staticmethod
    def _extract_symbol(message: str) -> str | None:
        """Extract token symbol from user message."""
        import re
        upper = message.upper()

        # 1. Try explicit "symbol is xxx" or "xxx coin" / "xxx token"
        #    Patterns like: "BTC price", "price of ETH", "how much is SOL"
        explicit_patterns = [
            r"\bprice\s+of\s+([A-Z]{2,8})\b",
            r"\bcost\s+of\s+([A-Z]{2,8})\b",
            r"\bhow\s+much\s+is\s+([A-Z]{2,8})\b",
            r"\b([A-Z]{2,8})\s+(?:price|cost|行情|走势|市值)\b",
            r"\b([A-Z]{2,8})\s+(?:coin|token|代币|币)\b",
            r"\b([A-Z]{2,8})\s+(?:perpetual|futures|合约)\b",
            r"\b(?:buy|sell|long|short)\s+([A-Z]{2,8})\b",
        ]
        for pattern in explicit_patterns:
            match = re.search(pattern, upper)
            if match:
                return match.group(1)

        # 2. Fallback: extract uppercase words that look like symbols (2-8 chars)
        #    Filter out common English words
        common_words = {"THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "ANY", "CAN", "HAD", "HER", "WAS", "ONE", "OUR", "OUT", "DAY", "GET", "HAS", "HIM", "HIS", "HOW", "MAN", "NEW", "NOW", "OLD", "SEE", "TWO", "WAY", "WHO", "BOY", "DID", "ITS", "LET", "PUT", "SAY", "SHE", "TOO", "USE", "DOW", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC", "MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN", "USD", "USDT", "USDC", "WITH", "HAVE", "FROM", "THEY", "BEEN", "WERE", "VERY", "JUST", "ABOUT", "OVER", "THANK", "THANKS", "PLEASE", "HELLO", "HIYA", "MONEY", "CASH", "PRICE", "COST", "MUCH", "MANY", "SOME", "MORE", "MOST", "OTHER", "TIME", "WORK", "LIFE", "YEAR", "BACK", "GOOD", "KNOW", "TAKE", "THINK", "COME", "COULD", "WOULD", "LIKE", "MAKE", "WANT", "NEED", "GIVE", "FIND", "TELL", "LOOK", "TURN", "HAND", "HEAD", "LONG", "LAST", "GREAT", "EACH", "MIGHT", "SAID", "EVEN", "HERE", "ONLY", "BOTH", "WHAT", "WHEN", "THAT", "THIS", "WILL", "YOUR", "THERE", "THEN", "THAN", "THEM", "INTO", "MORE", "VERY", "JUST", "ABOUT", "OVER", "ALSO", "EVEN", "WELL", "SURE", "MEAN", "SUCH", "KEEP", "CALL", "CAME", "FEEL", "SEEM", "LEFT", "DONE", "OPEN", "CASE", "SHOW", "PART", "MOVE", "LIVE", "PLAY", "WENT", "WANT", "HELP", "HOME", "SIDE", "BEST", "EASY", "HARD", "STOP", "NEXT", "ONCE", "SAME", "MUST", "NAME", "EACH", "EVEN", "EVER", "MUCH", "BOTH", "FEW", "FAR", "OWN", "UNDER", "BELOW", "ABOVE", "NEAR", "BETWEEN", "AFTER", "BEFORE", "WHILE", "DURING", "WITHOUT", "THROUGH", "AROUND", "AGAINST", "AMONG", "WITHIN", "ACROSS", "BESIDE", "BEHIND", "BEYOND", "INSIDE", "OUTSIDE", "TOWARD", "UNTIL", "SINCE", "UNTIL"}

        words = re.findall(r'\b[A-Z]{2,8}\b', upper)
        for word in words:
            if word not in common_words:
                return word

        return None

    @staticmethod
    def _is_token_query(message: str) -> bool:
        """Check if the message is a token/coin price query."""
        lower = message.lower()
        return any(kw in lower for kw in SkillRouter.TOKEN_KEYWORDS)

    async def _analyze_token(self, symbol: str) -> str:
        """Fetch and analyze token data from Binance Futures."""
        metrics = await token_analyzer.fetch_all(symbol)

        # If no price data, try CoinGecko fallback
        if metrics.price == 0:
            from services.datasources.coingecko import CoinGeckoSource
            cg = CoinGeckoSource()
            cg_result = await cg.get_token_price(symbol)
            if cg_result and "data" in cg_result:
                # Extract price from CoinGecko result
                for k, v in cg_result["data"].items():
                    if isinstance(v, dict) and "usd" in v:
                        metrics.price = float(v["usd"])
                        break

        # Format raw data
        data_text = token_analyzer.format_summary(metrics)

        # Use LLM to generate insightful analysis
        llm = create_llm()
        prompt = (
            f"You are a crypto market analyst. Analyze the following token data and provide "
            f"concise, actionable insights in Chinese. Focus on key trends and metrics.\n\n"
            f"Token Data:\n{data_text}\n\n"
            f"Provide analysis covering:\n"
            f"1. Price trend and momentum\n"
            f"2. Market sentiment (based on long/short ratio and funding rate)\n"
            f"3. Volume and liquidity assessment\n"
            f"4. Risk signals (liquidations, extreme ratios)\n\n"
            f"Analysis:"
        )
        try:
            result = await asyncio.wait_for(llm.ainvoke([UserMessage(content=prompt)]), timeout=20.0)
            analysis = result.completion if hasattr(result, "completion") and result.completion else (
                result.content if hasattr(result, "content") else str(result)
            )
            return f"{data_text}\n\n**Analysis**:\n{analysis}"
        except Exception:
            # Fallback: return raw data if LLM fails
            return data_text + "\n\n(Analysis unavailable - LLM timeout)"

    async def route(self, message: str, ws: Any = None, event_callback: Any = None) -> dict[str, Any]:
        """Route a user message using Function Calling via AgentGraph."""

        # Fast path: token/coin queries
        if self._is_token_query(message):
            symbol = self._extract_symbol(message)
            if symbol:
                # Emit thinking event
                if event_callback:
                    await event_callback("thinking", {"step": 1, "description": f"Analyzing {symbol} from Binance Futures..."})

                try:
                    output = await self._analyze_token(symbol)
                    return {
                        "type": "general",
                        "action": "chat",
                        "output": output,
                        "data": {},
                    }
                except Exception as e:
                    return {
                        "type": "general",
                        "action": "chat",
                        "output": f"Error fetching {symbol} data: {str(e)}",
                        "data": {},
                    }

        # Default path: use AgentGraph for complex queries
        state = AgentState(user_message=message)
        graph = AgentGraph(event_callback=event_callback)
        result = await graph.run(state)

        if result.summary:
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
