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
        "crowdedness_score": token.crowdedness_score,
        "squeeze_risk": token.squeeze_risk,
        "short_risk_rating": token.short_risk_rating,
        "rebound_potential": token.rebound_potential,
        # Short-selling trade reference
        "high_24h": token.high_24h,
        "low_24h": token.low_24h,
        "atr": token.atr,
        "oi_usd": token.oi_usd,
        "recommended_leverage": token.recommended_leverage,
        "stop_loss_price": token.stop_loss_price,
        "take_profit_price": token.take_profit_price,
        "funding_annualized": token.funding_annualized,
        "short_grade": token.short_grade,
        # Trend & market context
        "market_cap": token.market_cap,
        "consecutive_up_days": token.consecutive_up_days,
        "trend_strength": token.trend_strength,
        "sector": token.sector,
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
        # Short analysis
        "crowdedness_score": token.crowdedness_score,
        "squeeze_risk": token.squeeze_risk,
        "short_risk_rating": token.short_risk_rating,
        "rebound_potential": token.rebound_potential,
        # Trade reference
        "high_24h": token.high_24h,
        "low_24h": token.low_24h,
        "atr": token.atr,
        "oi_usd": token.oi_usd,
        "recommended_leverage": token.recommended_leverage,
        "stop_loss_price": token.stop_loss_price,
        "take_profit_price": token.take_profit_price,
        "funding_annualized": token.funding_annualized,
        "short_grade": token.short_grade,
        # Trend & market context
        "market_cap": token.market_cap,
        "consecutive_up_days": token.consecutive_up_days,
        "trend_strength": token.trend_strength,
        "sector": token.sector,
        "metrics": {
            "funding_annualized": token.funding_annualized,
            "oi_usd": token.oi_usd,
        },
        "signals": {
            "funding_extreme": abs(token.funding_rate) > 0.01,
            "overcrowded_short": token.crowdedness_score > 0.7,
            "squeeze_alert": token.squeeze_risk > 0.6,
            "high_rebound_potential": token.rebound_potential > 0.7,
        },
        "recommendation": _short_recommendation(token),
    }


def _short_recommendation(token: Any) -> str:
    """Generate short-selling recommendation based on metrics."""
    if token.short_risk_rating == "extreme":
        if token.squeeze_risk > 0.7:
            return "AVOID SHORT - Extreme squeeze risk. Shorts are overcrowded, funding is punitive."
        return "HIGH RISK - Very crowded short. Consider waiting for better entry."
    elif token.short_risk_rating == "high":
        return "MODERATE RISK - Short interest elevated. Watch for squeeze signals."
    elif token.short_risk_rating == "medium":
        return "CAUTION - Some short crowding. Monitor funding rate changes."
    return "LOW RISK - Conditions favorable for short analysis."


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
    use_testnet = config.get("binance_testnet", True)

    from services.risk import RiskConfig

    risk = RiskConfig.from_config_store()
    engine = TradingEngine(api_key, api_secret, use_testnet, risk=risk)

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
