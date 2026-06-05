"""Polymarket Prediction Market API endpoints.

`/start`, `/stop`, and `/status` dispatch through the scheduler
registry (looking up `PolymarketScheduler` by `task_id=2`) rather
than holding module-level globals. The actual `TopUsersPoller` /
`PositionMonitor` / `PolymarketTrader` instances are owned by the
scheduler — see `services/scheduler.PolymarketScheduler.start()` —
and constructed via the injectable `poller_factory` / `monitor_factory`.

`_handle_cluster_signal` and `_execute_signal` stay in this file
because the scheduler is constructed in `main.py` (Task 6) with
`signal_handler=_handle_cluster_signal` injected. The signal
pathway writes to `polymarket_signals` / `polymarket_trades` /
`polymarket_positions` and is unchanged.
"""
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException

from services.database import get_db
from services.polymarket_poller import ClusterSignal
from services.scheduler import get_scheduler

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/polymarket")

# Module-level `task_id` for the Polymarket scheduler. Must match
# `services.scheduler.PolymarketScheduler.TASK_ID`. Encoded as a
# constant so the registry lookup is a single source of truth.
_TASK_ID = 2


@router.get("/signals")
async def get_polymarket_signals(status: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Get prediction market signals with optional filters."""
    conn = get_db()
    cursor = conn.cursor()

    if status:
        cursor.execute(
            """SELECT * FROM polymarket_signals WHERE status = ?
               ORDER BY created_at DESC LIMIT ?""",
            (status, limit),
        )
    else:
        cursor.execute(
            "SELECT * FROM polymarket_signals ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )

    rows = cursor.fetchall()
    conn.close()

    return {
        "signals": [
            {
                "id": r["id"],
                "signal_id": r["signal_id"],
                "market_slug": r["market_slug"],
                "question": r["question"],
                "outcome": r["outcome"],
                "side": r["side"],
                "avg_price": r["avg_price"],
                "total_value": r["total_value"],
                "unique_users": r["unique_users"],
                "confidence": r["confidence"],
                "net_inflow": r["net_inflow"],
                "status": r["status"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    }


@router.get("/signals/{signal_id}")
async def get_polymarket_signal(signal_id: str) -> dict[str, Any]:
    """Get a single signal."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM polymarket_signals WHERE signal_id = ?", (signal_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Signal not found")

    return {"signal": dict(row)}


@router.get("/positions")
async def get_polymarket_positions() -> dict[str, Any]:
    """Get all open prediction market positions."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM polymarket_positions WHERE status = 'open'
           ORDER BY opened_at DESC"""
    )
    rows = cursor.fetchall()
    conn.close()

    return {
        "positions": [
            {
                "position_id": r["position_id"],
                "market_slug": r["market_slug"],
                "question": r["question"],
                "outcome": r["outcome"],
                "side": r["side"],
                "entry_price": r["entry_price"],
                "current_price": r["current_price"],
                "size": r["size"],
                "pnl": r["pnl"],
                "pnl_pct": r["pnl_pct"],
                "stop_loss_price": r["stop_loss_price"],
                "take_profit_price": r["take_profit_price"],
                "opened_at": r["opened_at"],
            }
            for r in rows
        ]
    }


@router.get("/trades")
async def get_polymarket_trades(limit: int = 50) -> dict[str, Any]:
    """Get prediction market trade history."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM polymarket_trades ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()

    return {"trades": [dict(r) for r in rows]}


@router.get("/config")
async def get_polymarket_config() -> dict[str, Any]:
    """Get Polymarket configuration."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM polymarket_config WHERE id = 1")
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"config": {}}

    return {
        "config": {
            "dry_run": bool(row["dry_run"]),
            "poll_interval": row["poll_interval"],
            "cluster_min_users": row["cluster_min_users"],
            "cluster_min_value": row["cluster_min_value"],
            "min_price": row["min_price"],
            "max_price": row["max_price"],
            "market_expiry_hours": row["market_expiry_hours"],
            "auto_execute_threshold": row["auto_execute_threshold"],
            "enabled": bool(row["enabled"]),
        }
    }


@router.put("/config")
async def update_polymarket_config(data: dict[str, Any]) -> dict[str, Any]:
    """Update Polymarket configuration."""
    conn = get_db()
    cursor = conn.cursor()

    fields = []
    values = []
    allowed = [
        "api_key", "api_secret", "api_passphrase", "private_key",
        "dry_run", "poll_interval", "cluster_min_users", "cluster_min_value",
        "min_price", "max_price", "enabled",
    ]
    for key in allowed:
        if key in data:
            fields.append(f"{key} = ?")
            values.append(data[key])

    if fields:
        query = f"UPDATE polymarket_config SET {', '.join(fields)} WHERE id = 1"
        cursor.execute(query, values)
        conn.commit()

    conn.close()
    return {"status": "updated"}


@router.post("/start")
async def start_polymarket_polling() -> dict[str, Any]:
    """Start the Polymarket signal polling service.

    Looks up `PolymarketScheduler` in the registry (task_id=2) and
    delegates `start()` to it. Returns 503 if the scheduler isn't
    registered yet — this can happen during the deployment window
    before Task 6 (main.py registration) is rolled out, and lets
    the operator's UI surface a clear error instead of crashing.
    """
    scheduler = get_scheduler(_TASK_ID)
    if scheduler is None:
        raise HTTPException(
            status_code=503,
            detail="Polymarket scheduler not registered — backend may be still starting up",
        )

    if scheduler.get_status().get("running"):
        return {"status": "already_running"}

    await scheduler.start()
    return {"status": "started"}


@router.post("/stop")
async def stop_polymarket_polling() -> dict[str, Any]:
    """Stop the Polymarket signal polling service.

    Looks up `PolymarketScheduler` in the registry (task_id=2) and
    delegates `stop()` to it. `PolymarketScheduler.stop()` is
    idempotent (safe to call when nothing is running), so the
    response is always `{"status": "stopped"}` when the scheduler
    is registered. Returns 503 if not yet registered.
    """
    scheduler = get_scheduler(_TASK_ID)
    if scheduler is None:
        raise HTTPException(
            status_code=503,
            detail="Polymarket scheduler not registered — backend may be still starting up",
        )

    await scheduler.stop()
    return {"status": "stopped"}


@router.get("/status")
async def get_polymarket_status() -> dict[str, Any]:
    """Get Polymarket service status.

    Poller and monitor are started together inside
    `PolymarketScheduler.start()` and share the scheduler's `running`
    flag, so the response collapses both to the same value. When the
    scheduler is not registered (e.g. before Task 6's main.py change
    is rolled out) we return `registered=False` rather than 503 — the
    UI treats the absence of a registered scheduler as "service not
    wired up yet" and shouldn't error.
    """
    scheduler = get_scheduler(_TASK_ID)
    if scheduler is None:
        return {
            "poller_running": False,
            "monitor_running": False,
            "registered": False,
        }

    status = scheduler.get_status()
    return {
        "poller_running": status.get("running", False),
        "monitor_running": status.get("running", False),
        "registered": True,
    }


async def _handle_cluster_signal(signal: ClusterSignal) -> None:
    """Handle incoming cluster signal: save to DB and optionally execute."""
    import hashlib

    signal_id = hashlib.sha256(
        f"{signal.token_id}_{signal.outcome}_{time.time()}".encode()
    ).hexdigest()[:16]

    conn = get_db()
    cursor = conn.cursor()

    # Save signal
    cursor.execute(
        """
        INSERT INTO polymarket_signals
        (signal_id, market_slug, question, outcome, side, token_id, condition_id,
         avg_price, total_value, unique_users, confidence, net_inflow, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """,
        (
            signal_id, signal.market_slug, signal.market_slug, signal.outcome,
            signal.side, signal.token_id, signal.condition_id, signal.avg_price,
            signal.total_value, signal.unique_users, signal.confidence, signal.net_inflow,
        ),
    )
    conn.commit()
    conn.close()

    logger.info("Signal saved | id=%s | %s | %s", signal_id, signal.market_slug, signal.side)

    # Auto-execute if confidence is high enough
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM polymarket_config WHERE id = 1")
    config = cursor.fetchone()
    conn.close()

    auto_threshold = config["auto_execute_threshold"] if config else 0.7
    if signal.confidence >= auto_threshold:
        await _execute_signal(signal, signal_id)
    else:
        logger.info(
            "Signal %s skipped execution | confidence=%.2f < threshold=%.2f",
            signal_id, signal.confidence, auto_threshold
        )


async def _execute_signal(signal: ClusterSignal, signal_id: str) -> None:
    """Execute a trading signal."""
    logger.info("Executing signal %s | %s | %s | amount=$%.2f", signal_id, signal.market_slug, signal.side, signal.total_value)

    # In dry_run mode, just simulate
    # Real implementation would create actual orders

    # Record trade
    import hashlib
    trade_id = f"trade_{signal_id}"
    position_id = f"pos_{signal_id}"

    conn = get_db()
    cursor = conn.cursor()

    # Record trade
    cursor.execute(
        """
        INSERT INTO polymarket_trades
        (trade_id, signal_id, position_id, token_id, condition_id, market_slug, outcome,
         side, price, size, amount, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'filled')
        """,
        (
            trade_id, signal_id, position_id, signal.token_id, signal.condition_id,
            signal.market_slug, signal.outcome, signal.side, signal.avg_price,
            signal.total_amount, signal.total_value,
        ),
    )

    # Create position
    from services.risk import RiskConfig, stop_loss_price, take_profit_price

    _risk = RiskConfig.polymarket()
    sentiment = "bearish" if signal.side == "SELL" else "bullish"
    sl_price = stop_loss_price(signal.avg_price, sentiment, _risk)
    tp_price = take_profit_price(signal.avg_price, sentiment, _risk)

    cursor.execute(
        """
        INSERT INTO polymarket_positions
        (position_id, signal_id, token_id, condition_id, market_slug, question, outcome,
         side, entry_price, current_price, size, entry_amount, highest_price, lowest_price,
         stop_loss_price, take_profit_price, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
        """,
        (
            position_id, signal_id, signal.token_id, signal.condition_id,
            signal.market_slug, signal.question, signal.outcome, signal.side,
            signal.avg_price, signal.avg_price, signal.total_amount, signal.total_value,
            signal.avg_price, signal.avg_price, sl_price, tp_price,
        ),
    )

    # Update signal status
    cursor.execute(
        "UPDATE polymarket_signals SET status = 'executed', executed_at = ? WHERE signal_id = ?",
        (time.time(), signal_id),
    )

    conn.commit()
    conn.close()

    logger.info("Signal %s executed | position_id=%s | trade_id=%s", signal_id, position_id, trade_id)
