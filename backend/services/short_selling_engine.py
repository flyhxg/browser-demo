import asyncio
from typing import List
from services.datasources.binance_futures import get_24h_ticker, get_funding_rate, get_open_interest, get_long_short_ratio, get_liquidations
from services.datasources.technical import get_klines, calculate_rsi, calculate_support_resistance
from services.datasources.arkham import get_exchange_netflow, get_whale_movements
from services.datasources.whale_alert import get_large_transactions
from services.datasources.coingecko import get_coin_details
from services.memory_manager import update_token_memory
from services.database import get_db
import json


class ShortSellingEngine:
    def __init__(self):
        self.dimension_map = {
            "derivatives": self._fetch_derivatives,
            "onchain": self._fetch_onchain,
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

        report = {
            "symbol": symbol.upper(),
            "timestamp": self._now_iso(),
            "dimensions": results,
            "llm_analysis": {
                "summary": f"Analysis for {symbol.upper()} across {len(dimensions)} dimensions.",
                "strengths": [],
                "risks": [],
                "confidence": 0.0,
                "recommendation": "neutral",
            },
        }

        self._persist_report(report, dimensions)
        update_token_memory(symbol, analysis_history=[report.get("timestamp")])
        return report

    async def compare(self, symbols: List[str], dimensions: List[str] = None) -> dict:
        reports = []
        for sym in symbols:
            r = await self.analyze(sym, dimensions)
            reports.append(r)
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
        return {
            "exchange_netflow_24h": results[0].get("exchange_netflow_24h") if not isinstance(results[0], Exception) else None,
            "whale_movements": results[1].get("whale_movements") if not isinstance(results[1], Exception) else [],
        }

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

    def _now_iso(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat() + "Z"

    def _persist_report(self, report: dict, dimensions: list):
        conn = get_db()
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
