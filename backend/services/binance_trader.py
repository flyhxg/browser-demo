"""Binance trading module for browser-demo.
Based on the trader interface from nofx-trading project.
Supports both Spot and Futures trading via CCXT.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional, Tuple

import ccxt


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class Position:
    symbol: str
    side: str  # "long" or "short"
    quantity: float
    entry_price: float
    mark_price: float = 0.0
    unrealized_pnl: float = 0.0
    leverage: int = 1
    liquidation_price: float = 0.0


@dataclass
class OrderResult:
    order_id: str
    symbol: str
    status: str  # "NEW", "FILLED", "PARTIALLY_FILLED", "CANCELED"
    side: str = ""
    price: float = 0.0
    quantity: float = 0.0
    filled: float = 0.0
    raw: dict = field(default_factory=dict)


@dataclass
class TradeSignal:
    symbol: str
    action: str  # "OPEN_LONG", "OPEN_SHORT", "CLOSE", "HOLD"
    confidence: float  # 0.0 - 1.0
    reason: str
    suggested_quantity: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0


# ---------------------------------------------------------------------------
# Base Trader Interface
# ---------------------------------------------------------------------------

class BaseTrader(ABC):
    """Abstract base trader following the nofx-trading interface."""

    @abstractmethod
    async def get_balance(self) -> dict[str, Any]:
        """Get account balance. Returns dict with keys like total, available, etc."""
        ...

    @abstractmethod
    async def get_positions(self) -> list[dict[str, Any]]:
        """Get all open positions."""
        ...

    @abstractmethod
    async def open_long(self, symbol: str, quantity: float, leverage: int = 1) -> OrderResult:
        """Open a long position."""
        ...

    @abstractmethod
    async def open_short(self, symbol: str, quantity: float, leverage: int = 1) -> OrderResult:
        """Open a short position."""
        ...

    @abstractmethod
    async def close_long(self, symbol: str, quantity: float = 0) -> OrderResult:
        """Close a long position. quantity=0 means close all."""
        ...

    @abstractmethod
    async def close_short(self, symbol: str, quantity: float = 0) -> OrderResult:
        """Close a short position. quantity=0 means close all."""
        ...

    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol."""
        ...

    @abstractmethod
    async def set_stop_loss(self, symbol: str, side: str, quantity: float, stop_price: float) -> bool:
        """Set stop-loss order."""
        ...

    @abstractmethod
    async def set_take_profit(self, symbol: str, side: str, quantity: float, take_profit_price: float) -> bool:
        """Set take-profit order."""
        ...

    @abstractmethod
    async def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all pending orders for a symbol."""
        ...

    @abstractmethod
    async def get_market_price(self, symbol: str) -> float:
        """Get current market price for a symbol."""
        ...


# ---------------------------------------------------------------------------
# Binance Futures Trader (CCXT)
# ---------------------------------------------------------------------------

class BinanceFuturesTrader(BaseTrader):
    """Binance Futures trader implementation using CCXT."""

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

        # Initialize CCXT Binance futures
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

        # Cache
        self._balance_cache: Optional[dict] = None
        self._balance_cache_time: float = 0
        self._cache_duration: float = 15.0  # 15 seconds

    def _is_cache_valid(self, cache_time: float) -> bool:
        return (time.time() - cache_time) < self._cache_duration

    async def get_balance(self) -> dict[str, Any]:
        if self._balance_cache and self._is_cache_valid(self._balance_cache_time):
            return self._balance_cache.copy()

        balance = await self.exchange.fetch_balance()
        result = {
            "totalWalletBalance": balance.get("USDT", {}).get("total", 0.0),
            "availableBalance": balance.get("USDT", {}).get("free", 0.0),
            "totalUnrealizedProfit": balance.get("USDT", {}).get("unrealized", 0.0),
        }
        self._balance_cache = result
        self._balance_cache_time = time.time()
        return result.copy()

    async def get_positions(self) -> list[dict[str, Any]]:
        positions = await self.exchange.fetch_positions()
        result = []
        for pos in positions:
            contracts = float(pos.get("contracts", 0))
            if contracts == 0:
                continue
            side = "long" if contracts > 0 else "short"
            result.append({
                "symbol": pos["symbol"],
                "positionAmt": abs(contracts),
                "entryPrice": float(pos.get("entryPrice", 0)),
                "markPrice": float(pos.get("markPrice", 0)),
                "unRealizedProfit": float(pos.get("unrealizedPnl", 0)),
                "leverage": int(pos.get("leverage", 1)),
                "liquidationPrice": float(pos.get("liquidationPrice", 0)),
                "side": side,
            })
        return result

    async def open_long(self, symbol: str, quantity: float, leverage: int = 1) -> OrderResult:
        await self.set_leverage(symbol, leverage)
        params = {"positionSide": "LONG"} if self._supports_hedge_mode() else {}
        order = await self.exchange.create_market_buy_order(
            symbol, quantity, params=params
        )
        return OrderResult(
            order_id=str(order["id"]),
            symbol=symbol,
            status=order["status"].upper(),
            side="BUY",
            quantity=quantity,
            raw=order,
        )

    async def open_short(self, symbol: str, quantity: float, leverage: int = 1) -> OrderResult:
        await self.set_leverage(symbol, leverage)
        params = {"positionSide": "SHORT"} if self._supports_hedge_mode() else {}
        order = await self.exchange.create_market_sell_order(
            symbol, quantity, params=params
        )
        return OrderResult(
            order_id=str(order["id"]),
            symbol=symbol,
            status=order["status"].upper(),
            side="SELL",
            quantity=quantity,
            raw=order,
        )

    async def close_long(self, symbol: str, quantity: float = 0) -> OrderResult:
        # Get current position if quantity is 0
        if quantity <= 0:
            positions = await self.get_positions()
            for pos in positions:
                if pos["symbol"] == symbol and pos["side"] == "long":
                    quantity = pos["positionAmt"]
                    break
            if quantity <= 0:
                raise ValueError(f"No long position found for {symbol}")

        params = {"positionSide": "LONG", "reduceOnly": True} if self._supports_hedge_mode() else {"reduceOnly": True}
        order = await self.exchange.create_market_sell_order(symbol, quantity, params=params)
        return OrderResult(
            order_id=str(order["id"]),
            symbol=symbol,
            status=order["status"].upper(),
            side="SELL",
            quantity=quantity,
            raw=order,
        )

    async def close_short(self, symbol: str, quantity: float = 0) -> OrderResult:
        if quantity <= 0:
            positions = await self.get_positions()
            for pos in positions:
                if pos["symbol"] == symbol and pos["side"] == "short":
                    quantity = pos["positionAmt"]
                    break
            if quantity <= 0:
                raise ValueError(f"No short position found for {symbol}")

        params = {"positionSide": "SHORT", "reduceOnly": True} if self._supports_hedge_mode() else {"reduceOnly": True}
        order = await self.exchange.create_market_buy_order(symbol, quantity, params=params)
        return OrderResult(
            order_id=str(order["id"]),
            symbol=symbol,
            status=order["status"].upper(),
            side="BUY",
            quantity=quantity,
            raw=order,
        )

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        try:
            await self.exchange.set_leverage(leverage, symbol)
            return True
        except Exception as e:
            # Leverage may already be set
            if "leverage" in str(e).lower():
                return True
            raise

    async def set_stop_loss(self, symbol: str, side: str, quantity: float, stop_price: float) -> bool:
        side_type = "SELL" if side == "long" else "BUY"
        params = {
            "stopPrice": stop_price,
            "reduceOnly": True,
        }
        if self._supports_hedge_mode():
            params["positionSide"] = side.upper()
        await self.exchange.create_order(
            symbol, "STOP_MARKET", side_type, quantity, None, params
        )
        return True

    async def set_take_profit(self, symbol: str, side: str, quantity: float, take_profit_price: float) -> bool:
        side_type = "SELL" if side == "long" else "BUY"
        params = {
            "stopPrice": take_profit_price,
            "reduceOnly": True,
        }
        if self._supports_hedge_mode():
            params["positionSide"] = side.upper()
        await self.exchange.create_order(
            symbol, "TAKE_PROFIT_MARKET", side_type, quantity, None, params
        )
        return True

    async def cancel_all_orders(self, symbol: str) -> bool:
        try:
            await self.exchange.cancel_all_orders(symbol)
            return True
        except Exception:
            return False

    async def get_market_price(self, symbol: str) -> float:
        ticker = await self.exchange.fetch_ticker(symbol)
        return float(ticker.get("last", 0))

    def _supports_hedge_mode(self) -> bool:
        """Check if exchange supports hedge mode (dual-side positions)."""
        # CCXT Binance futures supports hedge mode
        return True


# ---------------------------------------------------------------------------
# Binance Spot Trader (CCXT)
# ---------------------------------------------------------------------------

class BinanceSpotTrader(BaseTrader):
    """Binance Spot trader implementation using CCXT."""

    def __init__(self, api_key: str, api_secret: str) -> None:
        self.exchange = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "spot",
            },
        })
        self._balance_cache: Optional[dict] = None
        self._balance_cache_time: float = 0
        self._cache_duration: float = 15.0

    def _is_cache_valid(self, cache_time: float) -> bool:
        return (time.time() - cache_time) < self._cache_duration

    async def get_balance(self) -> dict[str, Any]:
        if self._balance_cache and self._is_cache_valid(self._balance_cache_time):
            return self._balance_cache.copy()

        balance = await self.exchange.fetch_balance()
        total = balance.get("USDT", {}).get("total", 0.0)
        available = balance.get("USDT", {}).get("free", 0.0)
        result = {
            "totalWalletBalance": total,
            "availableBalance": available,
            "totalUnrealizedProfit": 0.0,
        }
        self._balance_cache = result
        self._balance_cache_time = time.time()
        return result.copy()

    async def get_positions(self) -> list[dict[str, Any]]:
        # Spot has no positions; return non-USDT balances as "positions"
        balance = await self.exchange.fetch_balance()
        positions = []
        for asset, info in balance.get("total", {}).items():
            if asset == "USDT" or info <= 0:
                continue
            # Get current price for this asset
            symbol = f"{asset}/USDT"
            try:
                ticker = await self.exchange.fetch_ticker(symbol)
                price = float(ticker.get("last", 0))
            except Exception:
                price = 0

            if price > 0 and info * price < 1.0:
                continue

            positions.append({
                "symbol": symbol,
                "positionAmt": info,
                "entryPrice": price,
                "markPrice": price,
                "unRealizedProfit": 0.0,
                "leverage": 1,
                "liquidationPrice": 0.0,
                "side": "long",
            })
        return positions

    async def open_long(self, symbol: str, quantity: float, leverage: int = 1) -> OrderResult:
        # Spot: buy by USDT amount using quoteOrderQty
        order = await self.exchange.create_market_buy_order(symbol, quantity, params={"quoteOrderQty": quantity})
        return OrderResult(
            order_id=str(order["id"]),
            symbol=symbol,
            status=order["status"].upper(),
            side="BUY",
            quantity=quantity,
            raw=order,
        )

    async def open_short(self, symbol: str, quantity: float, leverage: int = 1) -> OrderResult:
        raise NotImplementedError("Spot trading does not support short positions")

    async def close_long(self, symbol: str, quantity: float = 0) -> OrderResult:
        if quantity <= 0:
            # Get asset balance
            base = symbol.replace("/USDT", "").replace("USDT", "")
            balance = await self.exchange.fetch_balance()
            quantity = float(balance.get(base, {}).get("free", 0))
            if quantity <= 0:
                raise ValueError(f"No spot balance found for {symbol}")

        order = await self.exchange.create_market_sell_order(symbol, quantity)
        return OrderResult(
            order_id=str(order["id"]),
            symbol=symbol,
            status=order["status"].upper(),
            side="SELL",
            quantity=quantity,
            raw=order,
        )

    async def close_short(self, symbol: str, quantity: float = 0) -> OrderResult:
        raise NotImplementedError("Spot trading does not support short positions")

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        # No-op for spot
        return True

    async def set_stop_loss(self, symbol: str, side: str, quantity: float, stop_price: float) -> bool:
        raise NotImplementedError("Spot stop-loss via OCO not yet implemented")

    async def set_take_profit(self, symbol: str, side: str, quantity: float, take_profit_price: float) -> bool:
        raise NotImplementedError("Spot take-profit via OCO not yet implemented")

    async def cancel_all_orders(self, symbol: str) -> bool:
        try:
            await self.exchange.cancel_all_orders(symbol)
            return True
        except Exception:
            return False

    async def get_market_price(self, symbol: str) -> float:
        ticker = await self.exchange.fetch_ticker(symbol)
        return float(ticker.get("last", 0))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_binance_trader(
    api_key: str,
    api_secret: str,
    mode: str = "futures",
    testnet: bool = False,
) -> BaseTrader:
    """Factory function to create a Binance trader."""
    if mode == "futures":
        return BinanceFuturesTrader(api_key, api_secret, testnet)
    elif mode == "spot":
        return BinanceSpotTrader(api_key, api_secret)
    else:
        raise ValueError(f"Unsupported trading mode: {mode}")
