"""Layer 2 / Layer 3 intent router for short-selling analysis.

The design (openspec/changes/ai-trading-system/design.md, "Intent Routing")
calls for two execution paths:

- Layer 2 (fixed pipeline): single token + predefined dimension set
  → ShortSellingEngine.analyze() runs the known fetchers in parallel.
- Layer 3 (dynamic planning): multi-token, cross-sector, or
  event-driven query → LLM plans which (symbol, dimension) pairs to
  fetch, then we execute the plan via the same engine.

Heuristics (cheap, no LLM):
  - 1 symbol and all requested dimensions are in the standard set
    → Layer 2.
  - anything else (multiple symbols, "why did X drop", sector
    comparison, free-form dimension request) → Layer 3.
"""
import asyncio
import json
import re
from typing import Any, Literal

from services.llm_factory import ProviderNotConfiguredError, create_llm
from services.short_selling_engine import ShortSellingEngine

STANDARD_DIMENSIONS = {"derivatives", "onchain", "unlock", "technical", "sentiment"}
LAYER2_DIMENSIONS = {"derivatives", "onchain", "technical"}

LAYER2_KEYWORDS_HINTS = (
    "做空", "资金费率", "funding", "多空比", "long short",
    "open interest", "持仓量", "支撑", "support", "压力", "resistance",
    "rsi",
)

EVENT_QUERY_KEYWORDS = (
    "why", "为什么", "what happened", "发生了什么",
    "drop", "pump", "crash", "暴涨", "暴跌", "plunge", "rally",
    "suddenly", "突然",
)


class IntentRouter:
    """Classify a query and dispatch to Layer 2 or Layer 3."""

    def __init__(self) -> None:
        self.engine = ShortSellingEngine()

    @staticmethod
    def classify(
        symbols: list[str] | None,
        dimensions: list[str] | None,
        message: str | None = None,
    ) -> Literal["layer2", "layer3", "event"]:
        """Decide which execution layer to use.

        Returns "layer2" for the simple fixed-pipeline case,
        "layer3" for anything requiring LLM planning,
        "event" for event-causality queries ("why did X drop").
        """
        if message:
            lower = message.lower()
            if any(kw in lower for kw in EVENT_QUERY_KEYWORDS):
                return "event"

        symbols = symbols or []
        if len(symbols) != 1:
            return "layer3"

        if dimensions is not None:
            non_standard = [d for d in dimensions if d not in STANDARD_DIMENSIONS]
            if non_standard:
                return "layer3"

        if message:
            lower = message.lower()
            if any(kw in lower for kw in ("why", "为什么", "compare", "比较", "sector", "赛道")):
                return "layer3"
            if re.search(r"\bwhy\b|\bcompare\b|\bacross\b", lower):
                return "layer3"

        return "layer2"

    async def route_event(
        self,
        symbol: str,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch an event-shaped query to EventPipeline."""
        from services.event_pipeline import EventPipeline
        pipeline = EventPipeline()
        report = await pipeline.run(symbol, "24h")
        return {
            "layer": "event",
            "report": report,
        }

    async def route(
        self,
        message: str | None = None,
        symbols: list[str] | None = None,
        dimensions: list[str | None] | None = None,
    ) -> dict[str, Any]:
        """Dispatch to the appropriate layer and return a unified report.

        The shape of the returned dict depends on the layer:
        - layer2: same shape as ShortSellingEngine.analyze() (single report)
        - layer3: {"plan": ..., "tokens": [report, ...], "llm_synthesis": "..."}
        """
        layer = self.classify(symbols, dimensions, message)

        if layer == "layer2":
            symbol = (symbols or [""])[0]
            return {
                "layer": "layer2",
                "report": await self.engine.analyze(symbol, dimensions=dimensions),
            }

        return await self._route_layer3(message, symbols, dimensions)

    async def _route_layer3(
        self,
        message: str | None,
        symbols: list[str] | None,
        dimensions: list[str | None] | None,
    ) -> dict[str, Any]:
        """Layer 3: LLM plans a sequence of fetches, we execute, then synthesize."""
        plan = await self._llm_plan(message, symbols, dimensions)
        reports: list[dict] = []
        for step in plan.get("steps", []):
            try:
                report = await self.engine.analyze(
                    step["symbol"],
                    dimensions=step.get("dimensions"),
                )
                reports.append(report)
            except Exception as e:
                reports.append({"symbol": step.get("symbol"), "error": str(e)})

        synthesis = await self._synthesize(message, reports)

        return {
            "layer": "layer3",
            "plan": plan,
            "tokens": reports,
            "llm_synthesis": synthesis,
        }

    async def _llm_plan(
        self,
        message: str | None,
        symbols: list[str] | None,
        dimensions: list[str | None] | None,
    ) -> dict[str, Any]:
        """Ask LLM to produce a fetch plan: list of (symbol, dimensions) steps."""
        fallback = self._fallback_plan(symbols, dimensions)
        try:
            llm = create_llm()
        except (ProviderNotConfiguredError, ValueError):
            return {"rationale": "LLM not configured — using uniform plan.", "steps": fallback}

        prompt = self._build_plan_prompt(message, symbols, dimensions)
        try:
            result = await asyncio.wait_for(
                llm.ainvoke([{"role": "user", "content": prompt}]),
                timeout=20.0,
            )
            text = result.completion if isinstance(result.completion, str) else str(result)
            return self._parse_plan(text, fallback)
        except (asyncio.TimeoutError, Exception):
            return {"rationale": "LLM plan timed out — using uniform plan.", "steps": fallback}

    @staticmethod
    def _fallback_plan(
        symbols: list[str] | None,
        dimensions: list[str | None] | None,
    ) -> list[dict[str, Any]]:
        """Uniform plan: every (symbol, dimension) pair, 1 step per symbol."""
        symbols = symbols or []
        if not symbols:
            return []
        dims = [d for d in (dimensions or ["derivatives", "onchain", "technical"]) if d]
        return [{"symbol": s, "dimensions": dims} for s in symbols]

    @staticmethod
    def _build_plan_prompt(
        message: str | None,
        symbols: list[str] | None,
        dimensions: list[str | None] | None,
    ) -> str:
        syms = ", ".join(symbols or []) or "(extract from user message)"
        dims = ", ".join(d for d in (dimensions or []) if d) or "any of: derivatives, onchain, unlock, technical, sentiment"
        user_msg = message or "(no message provided)"
        return (
            f"You are a crypto research planner. Given the user's question, produce a JSON "
            f"plan that lists the (symbol, dimensions) data fetches needed to answer it.\n\n"
            f"User question: {user_msg}\n"
            f"Symbols of interest: {syms}\n"
            f"Requested dimensions: {dims}\n\n"
            f"Available dimensions: derivatives, onchain, unlock, technical, sentiment.\n\n"
            f"Respond ONLY with valid JSON in this format:\n"
            f'{{"rationale": "<why this plan>", '
            f'"steps": [{{"symbol": "<TICKER>", "dimensions": ["derivatives", "onchain"]}}]}}'
        )

    @staticmethod
    def _parse_plan(text: str, fallback: list[dict]) -> dict[str, Any]:
        try:
            if "```" in text:
                import re as _re
                m = _re.search(r"```(?:json)?\s*(.*?)\s*```", text, _re.DOTALL)
                if m:
                    text = m.group(1)
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return {"rationale": "Could not parse plan.", "steps": fallback}
            data = json.loads(text[start:end + 1])
            steps = data.get("steps")
            if not isinstance(steps, list):
                return {"rationale": "Plan has no steps.", "steps": fallback}
            valid_steps: list[dict] = []
            for step in steps:
                if not isinstance(step, dict):
                    continue
                symbol = str(step.get("symbol", "")).strip().upper()
                if not symbol:
                    continue
                step_dims = step.get("dimensions") or []
                if not isinstance(step_dims, list):
                    step_dims = []
                step_dims = [d for d in step_dims if isinstance(d, str) and d in STANDARD_DIMENSIONS]
                if not step_dims:
                    step_dims = ["derivatives", "onchain"]
                valid_steps.append({"symbol": symbol, "dimensions": step_dims})
            if not valid_steps:
                return {"rationale": "Plan had no valid steps.", "steps": fallback}
            return {"rationale": str(data.get("rationale", "")), "steps": valid_steps}
        except (json.JSONDecodeError, ValueError):
            return {"rationale": "Plan parse error.", "steps": fallback}

    async def _synthesize(self, message: str | None, reports: list[dict]) -> str:
        """Have LLM write a one-paragraph synthesis across the fetched reports."""
        if not reports:
            return "No data fetched."
        try:
            llm = create_llm()
        except (ProviderNotConfiguredError, ValueError):
            return f"Cross-token synthesis unavailable. Fetched {len(reports)} report(s)."

        compact = [
            {
                "symbol": r.get("symbol"),
                "recommendation": r.get("llm_analysis", {}).get("recommendation"),
                "confidence": r.get("llm_analysis", {}).get("confidence"),
                "summary": r.get("llm_analysis", {}).get("summary"),
            }
            for r in reports
        ]
        prompt = (
            f"User question: {message or '(none)'}\n\n"
            f"Token reports:\n{json.dumps(compact, ensure_ascii=False, indent=2)}\n\n"
            f"Write a concise synthesis (2-4 sentences) comparing these tokens in light of "
            f"the user's question. Respond in the same language the user used."
        )
        try:
            result = await asyncio.wait_for(
                llm.ainvoke([{"role": "user", "content": prompt}]),
                timeout=20.0,
            )
            text = result.completion if isinstance(result.completion, str) else str(result)
            return text.strip()
        except (asyncio.TimeoutError, Exception):
            return f"Cross-token synthesis timed out. Fetched {len(reports)} report(s)."
