"""Binance Hot Tokens Scanner.

Periodically fetches Binance futures market data, calculates heat scores,
and broadcasts updates via WebSocket.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import ccxt

from services.config_store import get_config
from services.database import get_db
from services.ws_manager import manager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class HotToken:
    symbol: str
    price: float = 0.0
    price_change_24h: float = 0.0
    volume_24h: float = 0.0
    volume_usd: float = 0.0
    funding_rate: float = 0.0
    long_short_ratio: float = 0.0
    open_interest: float = 0.0
    liquidation_price: float = 0.0
    heat_score: float = 0.0
    heat_rank: int = 0
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Hot Tokens Scanner
# ---------------------------------------------------------------------------

class HotTokensScanner:
    """Scans Binance futures for hot tokens and broadcasts updates."""

    def __init__(self, api_key: str = "", api_secret: str = "", testnet: bool = True):
        self.exchange = ccxt.binanceusdm({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
        })
        if testnet:
            self.exchange.set_sandbox_mode(True)

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._hot_tokens: dict[str, HotToken] = {}

    # --- Public API ---

    def start(self) -> None:
        """Start the scanner background task."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run_loop())
            logger.info("HotTokensScanner started")

    def stop(self) -> None:
        """Stop the scanner."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("HotTokensScanner stopped")

    def get_hot_tokens(self, limit: int = 50) -> list[HotToken]:
        """Get current hot tokens sorted by heat score."""
        tokens = list(self._hot_tokens.values())
        tokens.sort(key=lambda x: x.heat_score, reverse=True)
        return tokens[:limit]

    # --- Internal Loop ---

    async def _run_loop(self) -> None:
        """Main loop: fetch data, calculate scores, broadcast."""
        while self._running:
            try:
                await self._fetch_and_update()
                await self._broadcast_update()
            except Exception as e:
                logger.warning(f"HotTokensScanner loop error: {e}")
            await asyncio.sleep(60)  # Scan every 60 seconds

    async def _fetch_and_update(self) -> None:
        """Fetch market data and update hot tokens."""
        # Fetch 24h ticker data (price, volume, change)
        tickers = await self.exchange.fetch_tickers()

        # Filter only USDT futures and calculate metrics
        hot_list: list[HotToken] = []
        for symbol, ticker in tickers.items():
            if not symbol.endswith("/USDT"):
                continue

            base = symbol.replace("/USDT", "")
            # Use symbol like "BTCUSDT" for Binance
            binance_symbol = f"{base}USDT"

            price = float(ticker.get("last", 0))
            price_change = float(ticker.get("percentage", 0))
            volume = float(ticker.get("baseVolume", 0))
            volume_usd = volume * price

            # Fetch additional data (funding rate, long/short ratio, open interest)
            funding_rate, long_short_ratio, open_interest = await self._fetch_token_metrics(binance_symbol)

            # Calculate liquidation price (simplified)
            liquidation_price = self._calculate_liquidation_price(price)

            hot = HotToken(
                symbol=binance_symbol,
                price=price,
                price_change_24h=price_change,
                volume_24h=volume,
                volume_usd=volume_usd,
                funding_rate=funding_rate,
                long_short_ratio=long_short_ratio,
                open_interest=open_interest,
                liquidation_price=liquidation_price,
            )
            hot_list.append(hot)

        # Calculate heat scores
        if hot_list:
            self._calculate_heat_scores(hot_list)
            # Store in memory dict
            self._hot_tokens = {t.symbol: t for t in hot_list}
            # Persist to DB
            await self._save_to_db(hot_list)

    async def _fetch_token_metrics(self, symbol: str) -> tuple[float, float, float]:
        """Fetch funding rate, long/short ratio, and open interest for a token."""
        funding_rate = 0.0
        long_short_ratio = 0.0
        open_interest = 0.0

        try:
            # Funding rate
            funding = await self.exchange.fetch_funding_rate(symbol)
            funding_rate = float(funding.get("fundingRate", 0))
        except Exception:
            pass

        try:
            # Long/short account ratio (Binance futures data API)
            params = {"symbol": symbol, "period": "5m", "limit": 1}
            ratio_data = await self.exchange.fapiDataGet_globalLongShortAccountRatio(params)
            if ratio_data:
                long_short_ratio = float(ratio_data[0].get("longShortRatio", 0))
        except Exception:
            pass

        try:
            # Open interest
            oi_data = await self.exchange.fetch_open_interest(symbol)
            open_interest = float(oi_data.get("openInterest", 0))
        except Exception:
            pass

        return funding_rate, long_short_ratio, open_interest

    def _calculate_liquidation_price(self, price: float, leverage: int = 20) -> float:
        """Simplified liquidation price calculation."""
        # For long: liq = price * (1 - 1/leverage)
        # For short: liq = price * (1 + 1/leverage)
        return price * (1 - 1 / leverage)

    def _calculate_heat_scores(self, tokens: list[HotToken]) -> None:
        """Calculate heat scores for all tokens."""
        if not tokens:
            return

        # Normalize metrics (0-1 scale)
        max_volume = max(t.volume_usd for t in tokens) if tokens else 1
        max_change = max(abs(t.price_change_24h) for t in tokens) if tokens else 1
        max_funding = max(abs(t.funding_rate) for t in tokens) if tokens else 1

        for token in tokens:
            volume_score = min(token.volume_usd / max_volume, 1.0) if max_volume else 0
            change_score = min(abs(token.price_change_24h) / max_change, 1.0) if max_change else 0
            funding_score = min(abs(token.funding_rate) / max_funding, 1.0) if max_funding else 0

            # Weighted heat score (MVP: volume > change > funding)
            token.heat_score = (
                volume_score * 0.5 +
                change_score * 0.3 +
                funding_score * 0.2
            )

    async def _save_to_db(self, tokens: list[HotToken]) -> None:
        """Save hot tokens snapshot to database."""
        conn = get_db()
        cursor = conn.cursor()
        for token in tokens:
            cursor.execute(
                """
                INSERT INTO hot_tokens (symbol, price, price_change_24h, volume_24h,
                    volume_usd, funding_rate, long_short_ratio, open_interest,
                    liquidation_price, heat_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    token.symbol,
                    token.price,
                    token.price_change_24h,
                    token.volume_24h,
                    token.volume_usd,
                    token.funding_rate,
                    token.long_short_ratio,
                    token.open_interest,
                    token.liquidation_price,
                    token.heat_score,
                ),
            )
        conn.commit()
        conn.close()

    async def _broadcast_update(self) -> None:
        """Broadcast hot tokens update via WebSocket."""
        tokens = self.get_hot_tokens(limit=50)
        data = [
            {
                "symbol": t.symbol,
                "price": t.price,
                "price_change_24h": t.price_change_24h,
                "volume_24h": t.volume_24h,
                "volume_usd": t.volume_usd,
                "funding_rate": t.funding_rate,
                "long_short_ratio": t.long_short_ratio,
                "open_interest": t.open_interest,
                "liquidation_price": t.liquidation_price,
                "heat_score": t.heat_score,
            }
            for t in tokens
        ]
        await manager.broadcast({"type": "hot_tokens_update", "data": data})


# Global singleton
_scanner: Optional[HotTokensScanner] = None


def get_scanner() -> HotTokensScanner:
    global _scanner
    if _scanner is None:
        config = get_config()
        _scanner = HotTokensScanner(
            api_key=config.get("binance_api_key", ""),
            api_secret=config.get("binance_secret_key", ""),
            testnet=config.get("binance_testnet", True),
        )
    return _scanner
