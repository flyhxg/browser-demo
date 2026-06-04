"""Aggregators that fan out to multiple single-source datasources.

OnchainAggregator: whale_alert + arkham
DerivativesAggregator: binance_futures + okx

Both return normalized event dicts compatible with the EventPipeline.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Sampling thresholds (per spec)
WHALE_MIN_USD = 5_000_000
LIQUIDATION_MIN_USD = 1_000_000
FUNDING_SHIFT_THRESHOLD = 0.001  # 0.1%


def _ts_to_iso(ts: Any) -> str:
    """Normalize various timestamp inputs to ISO-8601 string."""
    if isinstance(ts, str):
        return ts
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.isoformat()
    return datetime.now(timezone.utc).isoformat()


class OnchainAggregator:
    """Combines whale_alert + arkham into normalized whale events."""

    def __init__(self, whale=None, arkham=None):
        # Lazy default imports: only resolve the real source classes when no
        # mock/injected instance is supplied. This keeps unit tests independent
        # of whether the underlying single-source classes have been added yet.
        if whale is None:
            from services.datasources.whale_alert import WhaleAlert

            whale = WhaleAlert()
        if arkham is None:
            from services.datasources.arkham import Arkham

            arkham = Arkham()
        self.whale = whale
        self.arkham = arkham

    async def fetch(self, symbol: str, time_range: str) -> list[dict]:
        """Returns whale events >= $5M USD."""
        hours = {"1h": 1, "4h": 4, "24h": 24, "7d": 24 * 7}.get(time_range, 24)
        results = await asyncio.gather(
            self._safe(self.whale.get_recent_transfers, symbol, hours),
            self._safe(self.arkham.get_flows, symbol, hours),
            return_exceptions=True,
        )

        events: list[dict] = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning(f"[OnchainAggregator] fetch error: {r}")
                continue
            for transfer in r or []:
                amount = transfer.get("amount_usd", 0)
                if amount < WHALE_MIN_USD:
                    continue
                events.append({
                    "timestamp": _ts_to_iso(transfer.get("timestamp")),
                    "type": "whale",
                    "title": f"{amount / 1_000_000:.1f}M USD {symbol} transfer",
                    "source": transfer.get("source", "WhaleAlert"),
                    "url": transfer.get("url"),
                    "payload": {
                        "amount_usd": amount,
                        "from": transfer.get("from", "unknown"),
                        "to": transfer.get("to", "unknown"),
                    },
                    "severity": 5 if amount >= 50_000_000 else 3,
                })
        return events

    @staticmethod
    async def _safe(method, *args):
        return await method(*args)


class DerivativesAggregator:
    """Combines binance_futures + okx for liquidations + funding rate shifts."""

    def __init__(self, binance=None, okx=None):
        # Lazy default imports (see OnchainAggregator for rationale).
        if binance is None:
            from services.datasources.binance_futures import BinanceFutures

            binance = BinanceFutures()
        if okx is None:
            from services.datasources.okx import OKXSource

            okx = OKXSource()
        self.binance = binance
        self.okx = okx

    async def fetch(self, symbol: str, time_range: str) -> list[dict]:
        """Returns liquidation + funding_shift events."""
        results = await asyncio.gather(
            self._safe(self.binance.get_liquidations, symbol, time_range),
            self._safe(self.binance.get_funding_rate, symbol),
            self._safe(self.okx.get_funding_rate, symbol),
            return_exceptions=True,
        )

        events: list[dict] = []

        # Liquidations
        liqs = results[0]
        if isinstance(liqs, list):
            for liq in liqs:
                amount = liq.get("amount_usd", 0)
                if amount < LIQUIDATION_MIN_USD:
                    continue
                events.append({
                    "timestamp": _ts_to_iso(liq.get("timestamp")),
                    "type": "liquidation",
                    "title": f"{liq.get('side', '?').upper()} liq ${amount / 1_000_000:.1f}M",
                    "source": "BinanceFutures",
                    "url": None,
                    "payload": {"side": liq.get("side"), "amount_usd": amount},
                    "severity": 4 if amount >= 10_000_000 else 2,
                })

        # Funding rate shifts (from binance + okx)
        for idx, source_name in [(1, "BinanceFutures"), (2, "OKX")]:
            fr = results[idx]
            if not isinstance(fr, dict):
                continue
            rate = abs(fr.get("rate", 0))
            if rate > FUNDING_SHIFT_THRESHOLD:
                events.append({
                    "timestamp": _ts_to_iso(fr.get("timestamp")),
                    "type": "funding_shift",
                    "title": f"{source_name} funding rate {fr['rate']:.4f}",
                    "source": source_name,
                    "url": None,
                    "payload": {"rate": fr["rate"], "side": "long_pays_short" if fr["rate"] > 0 else "short_pays_long"},
                    "severity": 3,
                })

        return events

    @staticmethod
    async def _safe(method, *args):
        return await method(*args)
