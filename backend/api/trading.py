"""Trading API endpoints."""
import asyncio
import json
from enum import Enum
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.binance_trader import create_binance_trader
from services.config_store import get_config
from services.datasources.coingecko import get_coin_details
from services.datasources.okx import OKXSource
from services.database import get_db
from services.filter_engine import validate_signal
from services.signal_analyzer import SignalAnalyzer

router = APIRouter(prefix="/api/trading")


class TradeAction(str, Enum):
    OPEN_LONG = "open_long"
    CLOSE_LONG = "close_long"
    OPEN_SHORT = "open_short"
    CLOSE_SHORT = "close_short"


class ExecuteTradeRequest(BaseModel):
    signal_id: int | None = None
    token: str = "BTC"
    action: TradeAction = TradeAction.OPEN_LONG
    quantity: float = Field(default=0.01, gt=0)


@router.get("/signals")
async def get_signals(status: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Get trading signals with optional filters."""
    conn = get_db()
    cursor = conn.cursor()

    if status:
        cursor.execute(
            "SELECT * FROM signals WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        )
    else:
        cursor.execute("SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,))

    rows = cursor.fetchall()
    conn.close()

    return {"signals": [dict(row) for row in rows]}


@router.get("/signals/{signal_id}")
async def get_signal(signal_id: int) -> dict[str, Any]:
    """Get a single signal with analysis."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM signals WHERE id = ?", (signal_id,))
    signal = cursor.fetchone()

    if not signal:
        conn.close()
        raise HTTPException(status_code=404, detail="Signal not found")

    cursor.execute("SELECT * FROM signal_analysis WHERE signal_id = ?", (signal_id,))
    analysis = cursor.fetchall()

    cursor.execute("SELECT * FROM signal_validation WHERE signal_id = ?", (signal_id,))
    validation = cursor.fetchall()

    conn.close()

    return {
        "signal": dict(signal),
        "analysis": [dict(row) for row in analysis],
        "validation": [dict(row) for row in validation],
    }


@router.post("/signals/{signal_id}/validate")
async def validate_signal_endpoint(signal_id: int) -> dict[str, Any]:
    """Manually validate a signal.

    Pipeline:
    1. LLM analysis of the post content (sentiment, tokens, confidence)
    2. Persist to `signal_analysis` table
    3. Fetch market data for the primary extracted token
    4. Apply `filter_engine.validate_signal` rules
    5. Persist to `signal_validation` table

    The endpoint returns the full chain so the frontend can show why a
    signal passed or failed (LLM reasoning + which filter rules triggered).
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM signals WHERE id = ?", (signal_id,))
    signal = cursor.fetchone()
    if not signal:
        conn.close()
        raise HTTPException(status_code=404, detail="Signal not found")
    conn.close()

    # 1. LLM analysis
    analyzer = SignalAnalyzer()
    analysis = await analyzer.analyze(signal["content"])

    # 2. Persist analysis
    tokens = analysis.get("tokens") or []
    primary_token = tokens[0] if tokens else ""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO signal_analysis
           (signal_id, token, sentiment, confidence, reasoning, llm_model)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            signal_id,
            primary_token,
            analysis.get("sentiment"),
            analysis.get("confidence"),
            analysis.get("reasoning"),
            "default",
        ),
    )
    conn.commit()
    conn.close()

    # 3. Fetch market data for the primary token (best-effort)
    market: dict[str, Any] = {"confidence": analysis.get("confidence", 0.0)}
    if primary_token:
        try:
            details = await get_coin_details(primary_token.lower())
            market["cg_market_cap_rank"] = details.get("market_cap_rank")
            market["cg_price_change_24h"] = details.get("price_change_24h")
        except Exception:
            pass
        try:
            okx = OKXSource()
            fr = await okx.get_funding_rate(primary_token)
            market["okx_funding_rate"] = fr.get("funding_rate")
        except Exception:
            pass

    # 4. Apply filter rules
    validation = validate_signal(market)

    # 5. Persist validation
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO signal_validation
           (signal_id, token, cg_market_cap_rank, cg_price_change_24h,
            okx_funding_rate, validation_result, fail_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            signal_id,
            primary_token,
            market.get("cg_market_cap_rank"),
            market.get("cg_price_change_24h"),
            market.get("okx_funding_rate"),
            validation["validation_result"],
            validation["fail_reason"],
        ),
    )
    conn.commit()
    conn.close()

    return {
        "status": validation["validation_result"],
        "analysis": analysis,
        "market": market,
        "validation": validation,
    }


@router.get("/trades")
async def get_trades(limit: int = 50) -> dict[str, Any]:
    """Get trade history."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return {"trades": [dict(row) for row in rows]}


@router.get("/positions")
async def get_positions() -> dict[str, Any]:
    """Get current positions from Binance."""
    try:
        config = get_config()
        api_key = config.get("binance_api_key", "")
        api_secret = config.get("binance_secret_key", "")

        if not api_key or not api_secret:
            return {"positions": [], "error": "Binance API not configured"}

        trader = create_binance_trader(api_key, api_secret, "futures", config.get("proxy_url", ""))
        positions = await trader.get_positions()
        await trader.close()

        return {"positions": positions}
    except Exception as e:
        return {"positions": [], "error": str(e)}


@router.post("/positions/{symbol}/close")
async def close_position(symbol: str) -> dict[str, Any]:
    """Close an open position. Looks up direction first; calls close_long or close_short."""
    try:
        config = get_config()
        api_key = config.get("binance_api_key", "")
        api_secret = config.get("binance_secret_key", "")

        if not api_key or not api_secret:
            return {"error": "Binance API not configured"}

        trader = create_binance_trader(api_key, api_secret, "futures", config.get("proxy_url", ""))
        try:
            positions = await trader.get_positions()
            target = next((p for p in positions if p["symbol"] == symbol), None)
            if not target:
                return {"error": f"No open position found for {symbol}"}
            side = target.get("side", "long")
            if side == "short":
                result = await trader.close_short(symbol)
            else:
                result = await trader.close_long(symbol)
            return {"status": "closed", "order_id": result.order_id, "side": side}
        finally:
            await trader.close()
    except Exception as e:
        return {"error": str(e)}


@router.get("/config")
async def get_trading_config() -> dict[str, Any]:
    """Get trading configuration."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trading_config WHERE id = 1")
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"config": {}}

    config = dict(row)
    # Mask sensitive data
    if config.get("binance_api_key"):
        config["binance_api_key"] = "****" + config["binance_api_key"][-4:]
    if config.get("binance_secret_key"):
        config["binance_secret_key"] = "****" + config["binance_secret_key"][-4:]

    return {"config": config}


@router.put("/config")
async def update_trading_config(data: dict[str, Any]) -> dict[str, Any]:
    """Update trading configuration."""
    conn = get_db()
    cursor = conn.cursor()

    fields = []
    values = []
    for key, value in data.items():
        if key in ("binance_api_key", "binance_secret_key", "max_position_size_usd",
                  "tp_percentage", "sl_percentage", "min_confidence",
                  "max_daily_loss", "scan_interval_minutes"):
            fields.append(f"{key} = ?")
            values.append(value)

    if fields:
        query = f"UPDATE trading_config SET {', '.join(fields)} WHERE id = 1"
        cursor.execute(query, values)
        conn.commit()

    conn.close()
    return {"status": "updated"}


@router.post("/trades")
async def execute_trade(req: ExecuteTradeRequest) -> dict[str, Any]:
    """Execute a manual trade. `action` is one of open_long / close_long / open_short / close_short."""
    try:
        config = get_config()
        api_key = config.get("binance_api_key", "")
        api_secret = config.get("binance_secret_key", "")

        if not api_key or not api_secret:
            return {"error": "Binance API not configured"}

        trader = create_binance_trader(api_key, api_secret, "futures", config.get("proxy_url", ""))
        try:
            symbol = f"{req.token}USDT"
            if req.action == TradeAction.OPEN_LONG:
                result = await trader.open_long(symbol, req.quantity)
            elif req.action == TradeAction.CLOSE_LONG:
                result = await trader.close_long(symbol, req.quantity)
            elif req.action == TradeAction.OPEN_SHORT:
                result = await trader.open_short(symbol, req.quantity)
            else:  # CLOSE_SHORT
                result = await trader.close_short(symbol, req.quantity)
        finally:
            await trader.close()

        # Record in DB
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO trades (signal_id, token, side, exchange, market_type, order_id, quantity, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (req.signal_id, req.token, req.action.value, "binance", "futures", result.order_id, req.quantity, result.status),
        )
        conn.commit()
        conn.close()

        return {"status": "executed", "order_id": result.order_id, "action": req.action.value}
    except Exception as e:
        return {"error": str(e)}
