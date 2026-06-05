"""Binance Hot Tokens Scanner.

Periodically fetches Binance futures market data, calculates heat scores,
and broadcasts updates via WebSocket.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import ccxt.async_support as ccxt

from services.config_store import get_config
from services.database import get_db
from services.signal_analyzer import SignalAnalyzer
from services.trading_engine import TradingEngine
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
    # Short-selling analysis metrics (long-side direction)
    long_crowdedness: float = 0.0       # 0-1, higher = more crowded longs
    long_squeeze_risk: float = 0.0      # 0-1, higher = longs about to be squeezed
    extension_score: float = 0.0        # 0-1, higher = closer to short-term top
    short_risk_rating: str = "neutral"  # "low" / "medium" / "high" / "extreme"
    short_grade: str = "B"              # "S" / "A" / "B" / "C" / "D"
    short_opportunity_score: float = 0.0  # 0-1, composite for modal display
    # Hot tick derivations
    oi_usd: float = 0.0
    funding_annualized: float = 0.0
    # Warm (6h) fundamentals — populated by FundamentalsCache in Phase 1b
    market_cap: float = 0.0
    top10_holders_pct: float = 0.0
    gini: float = 0.0
    fdv_mcap_ratio: float = 0.0
    sector: str = "其他"
    # Cold (daily) OHLCV — populated lazily by get_token_analysis in Phase 1b
    consecutive_up_days: int = 0
    trend_strength: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    atr: float = 0.0
    rebound_multiple: float = 0.0
    low_7d: float = 0.0
    # Trade reference (placeholders until Phase 1b fills them)
    stop_loss_price: float = 0.0
    take_profit_price: float = 0.0
    recommended_leverage: int = 5


# ---------------------------------------------------------------------------
# Hot Tokens Scanner
# ---------------------------------------------------------------------------

class HotTokensScanner:
    """Scans Binance futures for hot tokens and broadcasts updates."""

    def __init__(self, api_key: str = "", api_secret: str = "", testnet: bool = True, proxy_url: str = ""):
        self._testnet = testnet
        exchange_config: dict[str, Any] = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
        }
        if proxy_url:
            exchange_config["aiohttp_proxy"] = proxy_url
        self.exchange = ccxt.binanceusdm(exchange_config)
        # Use mainnet for public market data (tickers are public API)
        # testnet is only used for trading with credentials

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._hot_tokens: dict[str, HotToken] = {}

        # Auto-trading state
        self._auto_enabled = False
        self._auto_threshold = 0.8
        self._auto_cooldown: dict[str, float] = {}  # symbol -> last_trade_timestamp
        self._cooldown_seconds = 3600  # 1 hour cooldown between auto-trades per symbol

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

    def set_auto_mode(self, enabled: bool, threshold: float = 0.8) -> None:
        """Enable or disable auto-trading mode."""
        self._auto_enabled = enabled
        self._auto_threshold = threshold
        logger.info(f"Auto-trading set to: {enabled}, threshold: {threshold}")

    def get_auto_status(self) -> dict:
        """Get auto-trading status."""
        return {
            "enabled": self._auto_enabled,
            "threshold": self._auto_threshold,
            "cooldowns": len(self._auto_cooldown),
        }

    def get_hot_tokens(self, limit: int = 50) -> list[HotToken]:
        """Get current hot tokens sorted by heat score."""
        tokens = list(self._hot_tokens.values())
        tokens.sort(key=lambda x: x.heat_score, reverse=True)
        return tokens[:limit]

    # --- Internal Loop ---

    async def _run_loop(self) -> None:
        """Main loop: fetch data, calculate scores, broadcast, auto-trade."""
        while self._running:
            try:
                await self._fetch_and_update()
                await self._broadcast_update()
                if self._auto_enabled:
                    await self._check_and_auto_trade()
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
            # ccxt returns "BTC/USDT:USDT" for perpetual futures
            if ":USDT" not in symbol and "/USDT" not in symbol:
                continue

            base = symbol.replace("/USDT", "").replace(":USDT", "")
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
            # ccxt returns: {'info': {...}, 'fundingRate': 0.0001, ...}
            funding_rate = float(funding.get("fundingRate", 0))
        except Exception:
            pass

        try:
            # Open interest - value is in info sub-dict
            oi_data = await self.exchange.fetch_open_interest(symbol)
            if oi_data and "info" in oi_data:
                open_interest = float(oi_data["info"].get("openInterest", 0))
            elif oi_data:
                open_interest = float(oi_data.get("openInterest", 0))
        except Exception:
            pass

        try:
            # Long/short account ratio via direct Binance futures data API
            # Using exchange's implicit API method: futures_data.topLongShortAccountRatio
            params = {"symbol": symbol, "period": "5m", "limit": 1}
            # Try ccxt's internal method for Binance futures data
            if hasattr(self.exchange, "futures_data_get_topLongShortAccountRatio"):
                ratio_data = await self.exchange.futures_data_get_topLongShortAccountRatio(params)
                if ratio_data and len(ratio_data) > 0:
                    long_short_ratio = float(ratio_data[0].get("longShortRatio", 0))
            else:
                # Fallback: use aiohttp directly via internal ccxt session
                import aiohttp
                url = "https://fapi.binance.com/futures/data/topLongShortAccountRatio"
                proxy_url = self.exchange.aiohttp_proxy if hasattr(self.exchange, "aiohttp_proxy") else ""
                async with aiohttp.ClientSession() as session:
                    req_params = {"symbol": symbol, "period": "5m", "limit": 1}
                    if proxy_url:
                        async with session.get(url, params=req_params, proxy=proxy_url) as resp:
                            if resp.status == 200:
                                ratio_data = await resp.json()
                                if ratio_data and len(ratio_data) > 0:
                                    long_short_ratio = float(ratio_data[0].get("longShortRatio", 0))
                    else:
                        async with session.get(url, params=req_params) as resp:
                            if resp.status == 200:
                                ratio_data = await resp.json()
                                if ratio_data and len(ratio_data) > 0:
                                    long_short_ratio = float(ratio_data[0].get("longShortRatio", 0))
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

            # --- Short-selling analysis metrics ---
            self._calculate_short_metrics(token)

    def _calculate_short_metrics(self, token: HotToken) -> None:
        """Calculate short-selling risk metrics for a token."""
        # Funding rate: negative = shorts pay longs (crowded short)
        # Normalize: typical range -0.01 to +0.01 per 8h
        funding_normalized = max(min(-token.funding_rate / 0.01, 1.0), -1.0)

        # Long/Short ratio: lower = more shorts
        # Normalize: 0.5 = balanced, <0.5 = short-heavy
        if token.long_short_ratio > 0:
            ls_normalized = max(min(1.0 - token.long_short_ratio, 1.0), 0.0)
        else:
            ls_normalized = 0.0

        # Price drop: larger drop = higher rebound potential
        # Normalize: 20% drop = max score
        drop_normalized = max(min(abs(token.price_change_24h) / 20.0, 1.0), 0.0) if token.price_change_24h < 0 else 0.0

        # Volume confirmation: high volume on drop = more genuine
        # Already captured in volume_score above

        # Crowdedness score: weighted average of funding and LS ratio
        # Funding is more direct signal of short crowding
        token.crowdedness_score = (
            funding_normalized * 0.6 +
            ls_normalized * 0.4
        )

        # Short squeeze risk: high crowdedness + high price drop + high volume
        token.squeeze_risk = (
            token.crowdedness_score * 0.5 +
            drop_normalized * 0.3 +
            min(token.volume_usd / (max_volume := max(t.volume_usd for t in self._hot_tokens.values()) if self._hot_tokens else 1, 1.0)) * 0.2
            if self._hot_tokens else token.crowdedness_score * 0.5 + drop_normalized * 0.3
        )
        # Fix: simplify squeeze_risk calculation
        token.squeeze_risk = min(token.crowdedness_score * 0.6 + drop_normalized * 0.4, 1.0)

        # Rebound potential: inverse of crowdedness + price drop momentum
        token.rebound_potential = min(drop_normalized * 0.7 + token.crowdedness_score * 0.3, 1.0)

        # Risk rating
        risk = token.crowdedness_score
        if risk > 0.8:
            token.short_risk_rating = "extreme"
        elif risk > 0.6:
            token.short_risk_rating = "high"
        elif risk > 0.4:
            token.short_risk_rating = "medium"
        else:
            token.short_risk_rating = "low"

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
                "crowdedness_score": t.crowdedness_score,
                "squeeze_risk": t.squeeze_risk,
                "short_risk_rating": t.short_risk_rating,
                "rebound_potential": t.rebound_potential,
            }
            for t in tokens
        ]
        await manager.broadcast({"type": "hot_tokens_update", "data": data})


    async def _check_and_auto_trade(self) -> None:
        """Check top tokens and auto-trade if conditions are met."""
        import time
        config = get_config()
        api_key = config.get("binance_api_key", "")
        api_secret = config.get("binance_secret_key", "")

        if not api_key or not api_secret:
            return

        for token in self.get_hot_tokens(limit=10):
            # Check heat threshold
            if token.heat_score < self._auto_threshold:
                continue

            # Check cooldown
            last_trade = self._auto_cooldown.get(token.symbol)
            if last_trade and (time.time() - last_trade) < self._cooldown_seconds:
                continue

            logger.info(f"Auto-trading candidate: {token.symbol} (heat={token.heat_score:.2f})")

            try:
                # LLM Analysis
                analyzer = SignalAnalyzer()
                content = (
                    f"Token: {token.symbol}\n"
                    f"Price: {token.price}\n"
                    f"24h Change: {token.price_change_24h}%\n"
                    f"24h Volume: {token.volume_usd} USD\n"
                    f"Funding Rate: {token.funding_rate}\n"
                    f"Long/Short Ratio: {token.long_short_ratio}\n"
                    f"Heat Score: {token.heat_score}\n"
                )
                analysis = await analyzer.analyze(content)
                confidence = float(analysis.get("confidence", 0))
                sentiment = analysis.get("sentiment", "neutral")

                logger.info(f"Analysis for {token.symbol}: sentiment={sentiment}, confidence={confidence}")

                # Only trade on bullish signals with high confidence
                if sentiment == "bullish" and confidence >= self._auto_threshold:
                    from services.risk import RiskConfig

                    risk = RiskConfig.from_config_store(config)
                    engine = TradingEngine(api_key, api_secret, config.get("binance_testnet", True), config.get("proxy_url", ""), risk=risk)
                    signal = {
                        "token": token.symbol.replace("USDT", ""),
                        "sentiment": "bullish",
                        "confidence": confidence,
                        "signal_id": None,
                    }
                    try:
                        result = await engine.execute_signal(signal)
                        logger.info(f"Auto-trade executed for {token.symbol}: {result}")
                        self._auto_cooldown[token.symbol] = time.time()
                    finally:
                        await engine.trader.close()
                else:
                    logger.info(f"Auto-trade skipped for {token.symbol}: sentiment={sentiment}, confidence={confidence}")

            except Exception as e:
                logger.warning(f"Auto-trade failed for {token.symbol}: {e}")


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
            proxy_url=config.get("proxy_url", ""),
        )
    return _scanner
