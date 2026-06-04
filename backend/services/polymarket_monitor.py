"""Polymarket Position Monitor.

Monitors open positions for stop-loss / take-profit conditions.
Polls current market prices and triggers close orders when thresholds hit.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from services.database import get_db
from services.polymarket_data_api import PolymarketDataApiClient
from services.polymarket_trader import PolymarketTrader

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Open position tracking."""

    position_id: str
    token_id: str
    condition_id: str
    market_slug: str
    question: str
    outcome: str
    side: str
    entry_price: float
    size: float
    highest_price: float
    lowest_price: float
    stop_loss_price: float
    take_profit_price: float
    status: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class PositionMonitor:
    """Monitor open positions for SL/TP triggers."""

    def __init__(
        self,
        trader: PolymarketTrader,
        check_interval: int = 30,
    ) -> None:
        self.trader = trader
        self.data_api = PolymarketDataApiClient()
        self.check_interval = check_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start monitoring loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("PositionMonitor started | interval=%ds", self.check_interval)

    async def stop(self) -> None:
        """Stop monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.data_api.close()
        logger.info("PositionMonitor stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_positions()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Monitor loop error: %s", e)
                await asyncio.sleep(self.check_interval)

    async def _check_positions(self) -> None:
        """Check all open positions for SL/TP."""
        positions = self._get_open_positions()
        if not positions:
            return

        for pos in positions:
            try:
                current_price = await self._get_current_price(pos.token_id)
                if current_price is None:
                    continue

                await self._update_position_price(pos, current_price)

                # Check SL / TP with direction awareness
                if pos.side == "BUY":
                    # For BUY: price going down hits SL, going up hits TP
                    if current_price <= pos.stop_loss_price:
                        await self._close_position(pos, "stop_loss", current_price)
                        continue
                    if current_price >= pos.take_profit_price:
                        await self._close_position(pos, "take_profit", current_price)
                        continue
                else:
                    # For SELL: price going up hits SL, going down hits TP
                    if current_price >= pos.stop_loss_price:
                        await self._close_position(pos, "stop_loss", current_price)
                        continue
                    if current_price <= pos.take_profit_price:
                        await self._close_position(pos, "take_profit", current_price)
                        continue

                # Update trailing high/low
                if current_price > pos.highest_price:
                    self._update_highest_price(pos, current_price)
                if current_price < pos.lowest_price:
                    self._update_lowest_price(pos, current_price)

            except Exception as e:
                logger.error("Check position %s error: %s", pos.position_id, e)

    def _get_open_positions(self) -> list[Position]:
        """Load open positions from DB."""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT position_id, token_id, condition_id, market_slug, question, outcome,
                   side, entry_price, size, highest_price, lowest_price,
                   stop_loss_price, take_profit_price, status, created_at
            FROM polymarket_positions
            WHERE status = 'open'
            """
        )
        rows = cursor.fetchall()
        conn.close()

        positions = []
        for row in rows:
            positions.append(Position(
                position_id=row["position_id"],
                token_id=row["token_id"],
                condition_id=row["condition_id"],
                market_slug=row["market_slug"],
                question=row["question"],
                outcome=row["outcome"],
                side=row["side"],
                entry_price=row["entry_price"],
                size=row["size"],
                highest_price=row["highest_price"] or row["entry_price"],
                lowest_price=row["lowest_price"] or row["entry_price"],
                stop_loss_price=row["stop_loss_price"],
                take_profit_price=row["take_profit_price"],
                status=row["status"],
                created_at=row["created_at"],
            ))
        return positions

    async def _get_current_price(self, token_id: str) -> Optional[float]:
        """Fetch current market price for a token."""
        try:
            data = await self.data_api.get_market_price(token_id)
            if data and "price" in data:
                return float(data["price"])
        except Exception as e:
            logger.debug("Price fetch error for %s: %s", token_id[:16], e)
        return None

    def _update_position_price(self, pos: Position, current_price: float) -> None:
        """Update current price in DB."""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE polymarket_positions SET current_price = ?, updated_at = ? WHERE position_id = ?",
            (current_price, time.time(), pos.position_id),
        )
        conn.commit()
        conn.close()

    def _update_highest_price(self, pos: Position, price: float) -> None:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE polymarket_positions SET highest_price = ? WHERE position_id = ?",
            (price, pos.position_id),
        )
        conn.commit()
        conn.close()

    def _update_lowest_price(self, pos: Position, price: float) -> None:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE polymarket_positions SET lowest_price = ? WHERE position_id = ?",
            (price, pos.position_id),
        )
        conn.commit()
        conn.close()

    async def _close_position(self, pos: Position, reason: str, close_price: float) -> None:
        """Close a position and record P&L."""
        logger.info("Closing position %s | reason=%s | price=%.4f", pos.position_id, reason, close_price)

        # Execute close order
        result = await self.trader.create_market_order(
            token_id=pos.token_id,
            side="SELL",
            amount=pos.size,
        )

        # Calculate P&L (direction-aware)
        if pos.side == "BUY":
            pnl = (close_price - pos.entry_price) * pos.size
            pnl_pct = (close_price - pos.entry_price) / pos.entry_price if pos.entry_price else 0
        else:
            # For SELL: profit when price goes down
            pnl = (pos.entry_price - close_price) * pos.size
            pnl_pct = (pos.entry_price - close_price) / pos.entry_price if pos.entry_price else 0

        # Update DB
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE polymarket_positions
            SET status = 'closed', close_price = ?, close_reason = ?, pnl = ?, pnl_pct = ?, closed_at = ?
            WHERE position_id = ?
            """,
            (close_price, reason, pnl, pnl_pct, time.time(), pos.position_id),
        )
        conn.commit()
        conn.close()

        logger.info(
            "Position %s closed | P&L=$%.2f (%.1f%%) | reason=%s",
            pos.position_id, pnl, pnl_pct * 100, reason,
        )
