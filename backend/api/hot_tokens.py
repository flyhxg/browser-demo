from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from services.config_store import get_config
from services.hot_tokens_scanner import get_scanner
from services.signal_analyzer import SignalAnalyzer
from services.trading_engine import TradingEngine

router = APIRouter(prefix="/api/hot_tokens")


def _token_to_dict(token: Any) -> dict[str, Any]:
    return {
        "symbol": token.symbol,
        "price": token.price,
        "price_change_24h": token.price_change_24h,
        "volume_24h": token.volume_24h,
        "volume_usd": token.volume_usd,
        "funding_rate": token.funding_rate,
        "long_short_ratio": token.long_short_ratio,
        "open_interest": token.open_interest,
        "liquidation_price": token.liquidation_price,
        "heat_score": token.heat_score,
        "heat_rank": token.heat_rank,
        "updated_at": token.updated_at,
        # Short analysis (corrected long-side direction)
        "long_crowdedness": token.long_crowdedness,
        "long_squeeze_risk": token.long_squeeze_risk,
        "extension_score": token.extension_score,
        "short_risk_rating": token.short_risk_rating,
        "short_grade": token.short_grade,
        "short_opportunity_score": token.short_opportunity_score,
        # Hot tick derivations
        "oi_usd": token.oi_usd,
        "funding_annualized": token.funding_annualized,
        # Warm / cold fields — populated by FundamentalsCache (Phase 1b)
        "market_cap": token.market_cap,
        "top10_holders_pct": token.top10_holders_pct,
        "gini": token.gini,
        "fdv_mcap_ratio": token.fdv_mcap_ratio,
        "sector": token.sector,
        "consecutive_up_days": token.consecutive_up_days,
        "trend_strength": token.trend_strength,
        "high_24h": token.high_24h,
        "low_24h": token.low_24h,
        "atr": token.atr,
        "rebound_multiple": token.rebound_multiple,
        "low_7d": token.low_7d,
        "stop_loss_price": token.stop_loss_price,
        "take_profit_price": token.take_profit_price,
        "recommended_leverage": token.recommended_leverage,
    }


@router.get("/")
async def get_hot_tokens(limit: int = 50) -> list[dict[str, Any]]:
    """Get hot tokens list sorted by heat score (DESC)."""
    scanner = get_scanner()
    tokens = scanner.get_hot_tokens(limit=limit)
    return [_token_to_dict(t) for t in tokens]


@router.get("/status")
async def scanner_status() -> dict[str, Any]:
    """Get scanner running status."""
    scanner = get_scanner()
    return {
        "running": scanner._running,
        "tokens_count": len(scanner._hot_tokens),
    }


@router.get("/sectors")
async def get_sectors() -> dict[str, Any]:
    """Get all known sector mappings for currently-tracked hot tokens.

    Returns a flat dict of `{SYMBOL: sector_name}` for tokens with a
    non-default sector. Tokens with sector="其他" (the scanner fallback)
    are excluded so the response stays focused on classified tokens.
    """
    scanner = get_scanner()
    sectors: dict[str, str] = {}
    for symbol, token in scanner._hot_tokens.items():
        sector = getattr(token, "sector", "其他") or "其他"
        if sector and sector != "其他":
            sectors[symbol] = sector
    return {"sectors": sectors, "count": len(sectors)}


@router.post("/start")
async def start_scanner() -> dict[str, str]:
    """Start the hot tokens scanner."""
    scanner = get_scanner()
    scanner.start()
    return {"status": "started"}


@router.post("/stop")
async def stop_scanner() -> dict[str, str]:
    """Stop the hot tokens scanner."""
    scanner = get_scanner()
    scanner.stop()
    return {"status": "stopped"}


@router.get("/auto/status")
async def get_auto_status() -> dict[str, Any]:
    """Get auto-trading status."""
    scanner = get_scanner()
    return scanner.get_auto_status()


@router.post("/auto/enable")
async def enable_auto_trading(data: dict[str, Any] | None = None) -> dict[str, str]:
    """Enable auto-trading mode."""
    scanner = get_scanner()
    threshold = 0.8
    if data and "threshold" in data:
        threshold = float(data["threshold"])
    scanner.set_auto_mode(True, threshold)
    return {"status": "enabled"}


@router.post("/auto/disable")
async def disable_auto_trading() -> dict[str, str]:
    """Disable auto-trading mode."""
    scanner = get_scanner()
    scanner.set_auto_mode(False)
    return {"status": "disabled"}


@router.get("/{symbol}")
async def get_token_detail(symbol: str) -> dict[str, Any]:
    """Get single token detail."""
    scanner = get_scanner()
    token = scanner._hot_tokens.get(symbol)
    if not token:
        raise HTTPException(status_code=404, detail=f"Token {symbol} not found")
    return _token_to_dict(token)


@router.post("/{symbol}/analyze")
async def analyze_token(symbol: str) -> dict[str, Any]:
    """LLM analyze a token."""
    scanner = get_scanner()
    token = scanner._hot_tokens.get(symbol)
    if not token:
        raise HTTPException(status_code=404, detail=f"Token {symbol} not found")

    content = (
        f"Token: {token.symbol}\n"
        f"Price: {token.price}\n"
        f"24h Change: {token.price_change_24h}%\n"
        f"24h Volume: {token.volume_24h} (USD: {token.volume_usd})\n"
        f"Funding Rate: {token.funding_rate}\n"
        f"Long/Short Ratio: {token.long_short_ratio}\n"
        f"Open Interest: {token.open_interest}\n"
        f"Heat Score: {token.heat_score}\n"
    )

    analyzer = SignalAnalyzer()
    result = await analyzer.analyze(content)
    return result


@router.get("/{symbol}/analysis")
async def get_token_analysis(symbol: str) -> dict[str, Any]:
    """Get comprehensive short-selling analysis for a token."""
    scanner = get_scanner()
    token = scanner._hot_tokens.get(symbol)
    if not token:
        raise HTTPException(status_code=404, detail=f"Token {symbol} not found")

    base = _token_to_dict(token)
    base["metrics"] = {
        "funding_annualized": token.funding_annualized,
        "oi_usd": token.oi_usd,
    }
    base["signals"] = {
        "funding_extreme": abs(token.funding_rate) > 0.01,
        "longs_crowded": token.long_crowdedness > 0.7,
        "squeeze_alert": token.long_squeeze_risk > 0.6,
        "high_short_opportunity": token.short_opportunity_score > 0.7,
    }
    base["recommendation"] = _short_recommendation(token)
    return base


def _short_recommendation(token: Any) -> str:
    """Short recommendation in the corrected long-crowd direction.

    High long_crowdedness = longs are paying funding and over-positioned
    = favorable short entry. High extension_score = price extended
    = stronger short setup.
    """
    if token.short_risk_rating == "extreme" and token.long_squeeze_risk > 0.7:
        return (
            "HIGH CONFIDENCE SHORT — Longs are extremely crowded and "
            "squeeze risk is high. Wait for funding to flip or a wick, "
            "then short into the move."
        )
    if token.short_risk_rating == "extreme":
        return (
            "STRONG SHORT — Extreme long crowding with elevated funding. "
            "Size conservatively; the position can run further before mean-reverting."
        )
    if token.short_risk_rating == "high":
        return (
            "MODERATE SHORT — Longs are crowded and funding is positive. "
            "Standard short setup; honor stop."
        )
    if token.short_risk_rating == "medium":
        return (
            "CAUTION — Some long crowding but not extreme. "
            "Wait for extension_score > 0.4 before entry."
        )
    return (
        "LOW CONVICTION — Longs are not crowded. Look elsewhere."
    )


@router.post("/{symbol}/execute")
async def execute_trade(symbol: str) -> dict[str, Any]:
    """Execute trade for a token."""
    scanner = get_scanner()
    token = scanner._hot_tokens.get(symbol)
    if not token:
        raise HTTPException(status_code=404, detail=f"Token {symbol} not found")

    config = get_config()
    api_key = config.get("binance_api_key", "")
    api_secret = config.get("binance_secret_key", "")

    from services.risk import RiskConfig

    risk = RiskConfig.from_config_store()
    engine = TradingEngine(api_key, api_secret, risk=risk)

    signal_dict = {
        "token": token.symbol.replace("USDT", ""),
        "sentiment": "bullish",
        "confidence": 1.0,
        "signal_id": None,
    }

    try:
        result = await engine.execute_signal(signal_dict)
    finally:
        await engine.trader.close()

    return result
