"""Trading execution engine with risk management."""
from contextlib import closing
from typing import Any

from services.binance_trader import BinanceFuturesTrader, create_binance_trader
from services.database import count_open_positions, get_db, insert_trade
from services.risk import RiskConfig, position_size, stop_loss_price, take_profit_price


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
        self._risk = risk

    async def execute_signal(self, signal: dict[str, Any]) -> dict[str, Any]:
        """Execute a validated trading signal using RiskConfig parameters."""
        token = signal.get("token", "")
        sentiment = signal.get("sentiment", "")

        if sentiment not in ("bullish",):
            return {"status": "skipped", "reason": "Only bullish signals are traded"}

        symbol = f"{token}USDT"

        balance_info = await self.trader.get_balance()
        available = balance_info.get("availableBalance", 0)

        size = position_size(available, self._risk)
        if size < self._risk.min_position_usd:
            return {"status": "skipped", "reason": "Position size too small"}

        # count_open_positions reads from the local DB (source-of-truth for "filled" trades),
        # not self.trader.get_positions(). The two can disagree when a position is open on
        # Binance but not yet recorded to DB; for those, the /api/trading/positions endpoint
        # (which still queries Binance) is the source-of-truth for "actually open" positions.
        with closing(get_db()) as conn:
            if count_open_positions(conn) >= self._risk.max_open_positions:
                return {"status": "skipped", "reason": "Max positions reached"}

            try:
                result = await self.trader.open_long(symbol, size)
                order_id = result.order_id

                price = await self.trader.get_market_price(symbol)
                tp_price = take_profit_price(price, sentiment, self._risk)
                sl_price = stop_loss_price(price, sentiment, self._risk)

                await self.trader.set_take_profit(symbol, "long", size, tp_price)
                await self.trader.set_stop_loss(symbol, "long", size, sl_price)

                insert_trade(
                    conn,
                    signal_id=signal.get("signal_id"),
                    token=token, side="buy", exchange="binance", market_type="futures",
                    order_id=order_id, quantity=size, price=price,
                    tp_price=tp_price, sl_price=sl_price,
                )
                conn.commit()

                return {
                    "status": "executed",
                    "order_id": order_id,
                    "symbol": symbol,
                    "quantity": size,
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
