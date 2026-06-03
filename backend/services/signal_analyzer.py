"""LLM-powered signal analysis service."""
import json
import re
from typing import Any

from services.llm_factory import ProviderNotConfiguredError, create_llm


class SignalAnalyzer:
    """Analyzes trading signals using LLM."""

    async def analyze(self, content: str, model: str | None = None) -> dict[str, Any]:
        """Analyze a social media post for trading signals.

        Args:
            content: The post content to analyze
            model: Optional model override

        Returns:
            Dict with tokens, sentiment, confidence, reasoning
        """
        try:
            llm = create_llm()
        except ProviderNotConfiguredError:
            return {
                "tokens": [],
                "sentiment": "unknown",
                "confidence": 0.0,
                "reasoning": "LLM not configured",
            }

        prompt = self._build_prompt(content)

        try:
            result = await llm.ainvoke([{"role": "user", "content": prompt}])
            text = result.completion if isinstance(result.completion, str) else str(result.completion)
            return self._parse_response(text)
        except Exception as e:
            return {
                "tokens": [],
                "sentiment": "error",
                "confidence": 0.0,
                "reasoning": f"Analysis failed: {e}",
            }

    def _build_prompt(self, content: str) -> str:
        return f"""Analyze the following cryptocurrency social media post.

Extract and return the following information in JSON format:
- tokens: list of token symbols mentioned (e.g., ["SOL", "ETH", "BTC"])
- sentiment: one of "bullish", "bearish", or "neutral"
- confidence: a float between 0.0 and 1.0 representing how confident the analysis is
- reasoning: a brief summary of why this sentiment was assigned

Post content:
{content}

Respond ONLY with valid JSON in this format:
{{"tokens": ["..."], "sentiment": "...", "confidence": ..., "reasoning": "..."}}"""

    def _parse_response(self, text: str) -> dict[str, Any]:
        """Parse LLM response, extracting JSON."""
        try:
            # Try to extract JSON from markdown code blocks
            if "```" in text:
                match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
                if match:
                    text = match.group(1)

            # Find JSON object
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                text = text[start:end + 1]

            data = json.loads(text)

            return {
                "tokens": data.get("tokens", []),
                "sentiment": data.get("sentiment", "neutral"),
                "confidence": float(data.get("confidence", 0.0)),
                "reasoning": data.get("reasoning", ""),
            }
        except (json.JSONDecodeError, ValueError):
            return {
                "tokens": [],
                "sentiment": "unknown",
                "confidence": 0.0,
                "reasoning": "Failed to parse LLM response",
            }
