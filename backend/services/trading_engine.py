"""Trading execution engine with risk management."""
from typing import Any

from services.binance_trader import BinanceFuturesTrader, create_binance_trader
from services.database import get_db
from services.risk import RiskConfig


class TradingEngine:
    """Handles trade execution with risk management."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        use_testnet: bool = False,
        proxy_url: str = "",
        *,
        risk: RiskConfig,
    ) -> None:
        self.trader = create_binance_trader(api_key, secret_key, "futures", use_testnet, proxy_url)
        self.use_testnet = use_testnet
        self._risk = risk

    async def execute_signal(self, signal: dict[str, Any]) -> dict[str, Any]:
        """Execute a validated trading signal.

        Args:
            signal: Dict with token, sentiment, confidence, etc.

        Returns:
            Dict with trade result.
        """
        token = signal.get("token", "")
        sentiment = signal.get("sentiment", "")

        if sentiment not in ("bullish",):
            return {"status": "skipped", "reason": "Only bullish signals are traded"}

        symbol = f"{token}USDT"

        # Get account info
        balance_info = await self.trader.get_balance()
        available = balance_info.get("availableBalance", 0)

        # Position sizing (2% of balance, max $100)
        position_size = min(available * 0.02, 100.0)
        if position_size < 10:
            return {"status": "skipped", "reason": "Position size too small"}

        # Check max positions
        positions = await self.trader.get_positions()
        if len(positions) >= 5:
            return {"status": "skipped", "reason": "Max positions reached"}

        try:
            # Open long position
            result = await self.trader.open_long(symbol, position_size)
            order_id = result.order_id

            # Get current price for TP/SL calculation
            price = await self.trader.get_market_price(symbol)

            # Calculate TP/SL
            tp_price = price * 1.05  # 5% take profit
            sl_price = price * 0.97  # 3% stop loss

            # Set TP/SL
            await self.trader.set_take_profit(symbol, "long", position_size, tp_price)
            await self.trader.set_stop_loss(symbol, "long", position_size, sl_price)

            # Record in database
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trades (signal_id, token, side, exchange, market_type, order_id, quantity, price, tp_price, sl_price, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'filled')
                """,
                (signal.get("signal_id"), token, "buy", "binance", "futures", order_id, position_size, price, tp_price, sl_price),
            )
            conn.commit()
            conn.close()

            return {
                "status": "executed",
                "order_id": order_id,
                "symbol": symbol,
                "quantity": position_size,
                "price": price,
                "tp_price": tp_price,
                "sl_price": sl_price,
            }

        except Exception as e:
            return {"status": "error", "reason": str(e)}

    async def close_position(self, symbol: str) -> dict[str, Any]:
        """Close a position.

        Args:
            symbol: Trading pair symbol (e.g., "SOLUSDT").

        Returns:
            Dict with close result.
        """
        try:
            result = await self.trader.close_long(symbol)
            return {"status": "closed", "order_id": result.order_id}
        except Exception as e:
            return {"status": "error", "reason": str(e)}
