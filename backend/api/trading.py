"""Trading API endpoints."""
import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException

from services.binance_trader import create_binance_trader
from services.config_store import get_config
from services.database import get_db
from services.signal_analyzer import SignalAnalyzer

router = APIRouter(prefix="/api/trading")


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
    """Manually validate a signal."""
    # Get signal from DB
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM signals WHERE id = ?", (signal_id,))
    signal = cursor.fetchone()
    if not signal:
        conn.close()
        raise HTTPException(status_code=404, detail="Signal not found")
    conn.close()

    # Analyze with LLM
    analyzer = SignalAnalyzer()
    result = await analyzer.analyze(signal["content"])

    return {"status": "analyzed", "result": result}


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
        use_testnet = config.get("binance_testnet", True)

        if not api_key or not api_secret:
            return {"positions": [], "error": "Binance API not configured"}

        trader = create_binance_trader(api_key, api_secret, "futures", use_testnet, config.get("proxy_url", ""))
        positions = await trader.get_positions()
        await trader.close()

        return {"positions": positions}
    except Exception as e:
        return {"positions": [], "error": str(e)}


@router.post("/positions/{symbol}/close")
async def close_position(symbol: str) -> dict[str, Any]:
    """Close a position."""
    try:
        config = get_config()
        api_key = config.get("binance_api_key", "")
        api_secret = config.get("binance_secret_key", "")
        use_testnet = config.get("binance_testnet", True)

        if not api_key or not api_secret:
            return {"error": "Binance API not configured"}

        trader = create_binance_trader(api_key, api_secret, "futures", use_testnet, config.get("proxy_url", ""))
        result = await trader.close_long(symbol)
        await trader.close()

        return {"status": "closed", "order_id": result.order_id}
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
        if key in ("binance_api_key", "binance_secret_key", "use_testnet", "max_position_size_usd",
                  "max_positions", "tp_percentage", "sl_percentage", "min_confidence",
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
async def execute_trade(data: dict[str, Any]) -> dict[str, Any]:
    """Execute a manual trade."""
    try:
        config = get_config()
        api_key = config.get("binance_api_key", "")
        api_secret = config.get("binance_secret_key", "")
        use_testnet = config.get("binance_testnet", True)

        if not api_key or not api_secret:
            return {"error": "Binance API not configured"}

        trader = create_binance_trader(api_key, api_secret, "futures", use_testnet, config.get("proxy_url", ""))

        signal_id = data.get("signal_id")
        token = data.get("token", "BTC")
        side = data.get("side", "buy")
        quantity = data.get("quantity", 0.01)

        if side == "buy":
            result = await trader.open_long(f"{token}USDT", quantity)
        else:
            result = await trader.close_long(f"{token}USDT", quantity)

        await trader.close()

        # Record in DB
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO trades (signal_id, token, side, exchange, market_type, order_id, quantity, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (signal_id, token, side, "binance", "futures", result.order_id, quantity, result.status),
        )
        conn.commit()
        conn.close()

        return {"status": "executed", "order_id": result.order_id}
    except Exception as e:
        return {"error": str(e)}
