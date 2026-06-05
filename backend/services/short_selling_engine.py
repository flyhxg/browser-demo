import asyncio
import json
import re
from typing import Any, List
from services.datasources.binance_futures import get_24h_ticker, get_funding_rate, get_open_interest, get_long_short_ratio, get_liquidations
from services.datasources.technical import get_klines, calculate_rsi, calculate_support_resistance
from services.datasources.arkham import (
    get_exchange_netflow,
    get_whale_movements,
    get_holder_concentration,
    get_smart_money_flow,
    get_exchange_reserves,
)
from services.datasources.whale_alert import get_large_transactions
from services.datasources.coingecko import get_coin_details
from services.llm_factory import ProviderNotConfiguredError, create_llm
from services.memory_manager import load_token_memory, update_token_memory
from services.database import get_db


VALID_RECOMMENDATIONS = {"strong_short", "weak_short", "neutral", "weak_long", "strong_long"}
VALID_HORIZONS = {"short_term", "medium_term", "long_term"}


class ShortSellingEngine:
    def __init__(self):
        self.dimension_map = {
            "derivatives": self._fetch_derivatives,
            "onchain": self._fetch_onchain,
            "holder_concentration": self._fetch_holder_concentration,
            "smart_money": self._fetch_smart_money,
            "exchange_reserves": self._fetch_exchange_reserves,
            "unlock": self._fetch_unlock,
            "technical": self._fetch_technical,
            "sentiment": self._fetch_sentiment,
        }

    async def analyze(self, symbol: str, dimensions: List[str] = None, timeframe: str = "24h") -> dict:
        if dimensions is None:
            dimensions = ["derivatives", "onchain", "technical"]

        results = {}
        tasks = []
        for dim in dimensions:
            fetcher = self.dimension_map.get(dim)
            if fetcher:
                tasks.append(fetcher(symbol))

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        for dim, result in zip(dimensions, raw_results):
            if isinstance(result, Exception):
                results[dim] = {"error": str(result)}
            else:
                results[dim] = result

        llm_analysis = await self._run_llm_analysis(symbol, dimensions, results)

        report = {
            "symbol": symbol.upper(),
            "timestamp": self._now_iso(),
            "dimensions": results,
            "llm_analysis": llm_analysis,
        }

        self._persist_report(report, dimensions)
        memory = load_token_memory(symbol)
        history = memory.get("analysis_history", [])
        history.append(report.get("timestamp"))
        update_token_memory(symbol, analysis_history=history)
        return report

    async def compare(self, symbols: List[str], dimensions: List[str] = None) -> dict:
        reports = await asyncio.gather(*[
            self.analyze(sym, dimensions) for sym in symbols
        ])
        return {
            "tokens": reports,
            "llm_comparison": f"Compared {len(symbols)} tokens.",
        }

    async def _fetch_derivatives(self, symbol: str) -> dict:
        tasks = [get_24h_ticker(symbol), get_funding_rate(symbol), get_open_interest(symbol), get_long_short_ratio(symbol), get_liquidations(symbol)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            "price": results[0].get("price") if not isinstance(results[0], Exception) else None,
            "price_change_24h_pct": results[0].get("price_change_24h_pct") if not isinstance(results[0], Exception) else None,
            "funding_rate": results[1].get("funding_rate") if not isinstance(results[1], Exception) else None,
            "open_interest": results[2].get("open_interest") if not isinstance(results[2], Exception) else None,
            "long_short_ratio": results[3].get("long_short_ratio") if not isinstance(results[3], Exception) else None,
            "liquidations_24h": results[4].get("liquidations_24h") if not isinstance(results[4], Exception) else None,
        }

    async def _fetch_onchain(self, symbol: str) -> dict:
        tasks = [get_exchange_netflow(symbol), get_whale_movements(symbol)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        netflow = results[0] if not isinstance(results[0], Exception) else {}
        whales = results[1] if not isinstance(results[1], Exception) else {}
        return {
            "cex_netflow_24h": netflow.get("cex_netflow_24h"),
            "cex_inflow_24h": netflow.get("cex_inflow_24h"),
            "cex_outflow_24h": netflow.get("cex_outflow_24h"),
            "whale_movements": whales.get("whale_movements", []),
        }

    async def _fetch_holder_concentration(self, symbol: str) -> dict:
        return await get_holder_concentration(symbol)

    async def _fetch_smart_money(self, symbol: str) -> dict:
        return await get_smart_money_flow(symbol)

    async def _fetch_exchange_reserves(self, symbol: str) -> dict:
        return await get_exchange_reserves(symbol)

    async def _fetch_unlock(self, symbol: str) -> dict:
        try:
            details = await get_coin_details(symbol.lower())
            return {
                "fdv": details.get("fdv"),
                "market_cap": details.get("market_cap"),
                "total_supply": details.get("total_supply"),
                "circulating_supply": details.get("circulating_supply"),
            }
        except Exception:
            return {"note": "Unlock data unavailable"}

    async def _fetch_technical(self, symbol: str) -> dict:
        try:
            klines = await get_klines(symbol, interval="4h", limit=100)
            rsi = calculate_rsi(klines)
            sr = calculate_support_resistance(klines)
            return {"rsi": rsi, "support": sr.get("support"), "resistance": sr.get("resistance")}
        except Exception as e:
            return {"error": str(e)}

    async def _fetch_sentiment(self, symbol: str) -> dict:
        return {"note": "Sentiment analysis via LLM on social feeds (TODO: integrate Twitter/LunarCrush)"}

    async def _run_llm_analysis(
        self, symbol: str, dimensions: List[str], results: dict
    ) -> dict[str, Any]:
        """Call LLM to produce structured short-selling analysis from fetched data.

        Returns dict with summary / strengths / risks / confidence / recommendation /
        time_horizon. Falls back to a neutral stub if LLM is unconfigured, times out,
        or returns unparseable output — never raises.
        """
        fallback = {
            "summary": f"Analysis for {symbol.upper()} across {len(dimensions)} dimensions.",
            "strengths": [],
            "risks": [],
            "confidence": 0.0,
            "recommendation": "neutral",
            "time_horizon": "medium_term",
        }

        try:
            llm = create_llm()
        except (ProviderNotConfiguredError, ValueError):
            return fallback

        compact = self._compact_dimensions(results)
        prompt = self._build_llm_prompt(symbol, dimensions, compact)

        try:
            result = await asyncio.wait_for(llm.ainvoke([{"role": "user", "content": prompt}]), timeout=25.0)
            text = result.completion if isinstance(result.completion, str) else str(result)
            return self._parse_llm_response(text, fallback)
        except (asyncio.TimeoutError, Exception):
            return fallback

    @staticmethod
    def _compact_dimensions(results: dict) -> dict:
        """Drop noisy keys to keep the LLM prompt under 3000 chars.

        We strip dicts of None values and any list over 5 items (e.g. whale_movements).
        """
        compact: dict = {}
        for dim, data in results.items():
            if not isinstance(data, dict):
                compact[dim] = data
                continue
            cleaned: dict = {}
            for k, v in data.items():
                if v is None or v == "":
                    continue
                if isinstance(v, list) and len(v) > 5:
                    cleaned[k] = f"<{len(v)} entries>"
                else:
                    cleaned[k] = v
            compact[dim] = cleaned
        return compact

    @staticmethod
    def _build_llm_prompt(symbol: str, dimensions: List[str], compact: dict) -> str:
        data_str = json.dumps(compact, ensure_ascii=False, indent=2)
        return (
            f"You are a crypto trading analyst. Given the following multi-dimension "
            f"market data for {symbol.upper()}, produce a short-selling decision.\n\n"
            f"Dimensions fetched: {', '.join(dimensions)}\n\n"
            f"Data:\n{data_str}\n\n"
            f"Respond ONLY with valid JSON in this exact format:\n"
            f'{{"summary": "<1-3 sentence analysis>", '
            f'"strengths": ["<reason supporting the position>"], '
            f'"risks": ["<reason against the position>"], '
            f'"confidence": <0.0-1.0>, '
            f'"recommendation": "<strong_short|weak_short|neutral|weak_long|strong_long>", '
            f'"time_horizon": "<short_term|medium_term|long_term>"}}'
        )

    @staticmethod
    def _parse_llm_response(text: str, fallback: dict) -> dict:
        """Extract JSON object from LLM text and validate field values."""
        try:
            if "```" in text:
                match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
                if match:
                    text = match.group(1)
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return fallback
            data = json.loads(text[start:end + 1])
        except (json.JSONDecodeError, ValueError):
            return fallback

        recommendation = str(data.get("recommendation", "neutral")).strip().lower()
        if recommendation not in VALID_RECOMMENDATIONS:
            recommendation = "neutral"

        horizon = str(data.get("time_horizon", "medium_term")).strip().lower()
        if horizon not in VALID_HORIZONS:
            horizon = "medium_term"

        try:
            confidence = float(data.get("confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.0

        return {
            "summary": str(data.get("summary", "")).strip() or fallback["summary"],
            "strengths": list(data.get("strengths") or []),
            "risks": list(data.get("risks") or []),
            "confidence": confidence,
            "recommendation": recommendation,
            "time_horizon": horizon,
        }

    def _now_iso(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    def _persist_report(self, report: dict, dimensions: list):
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO analysis_reports (symbol, dimensions, raw_data, llm_summary, confidence, recommendation, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                report["symbol"],
                json.dumps(dimensions),
                json.dumps(report["dimensions"]),
                report["llm_analysis"]["summary"],
                report["llm_analysis"]["confidence"],
                report["llm_analysis"]["recommendation"],
                "completed",
            ))
            conn.commit()
        finally:
            conn.close()
