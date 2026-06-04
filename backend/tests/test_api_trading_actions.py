"""Tests for the P0 fixes in api/trading.py.

- close_position must look up the position's direction and call the
  correct close_long / close_short method (was: always close_long,
  which silently failed for short positions).
- execute_trade must accept the full action vocabulary
  (open_long | close_long | open_short | close_short) via a Pydantic
  model. Default action is open_long (back-compat with the existing
  frontend that only sends {signal_id}).
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import trading as trading_module
from api.trading import router


class FakeOrderResult:
    def __init__(self, order_id, symbol="BTCUSDT", status="FILLED"):
        self.order_id = order_id
        self.symbol = symbol
        self.status = status


class FakeTrader:
    """Captures which method gets called; positions are pre-loaded."""
    def __init__(self, positions):
        self.positions = positions
        self.calls: list[tuple] = []
        self.closed = False

    async def get_positions(self):
        return self.positions

    async def open_long(self, symbol, quantity, leverage=1):
        self.calls.append(("open_long", symbol, quantity, leverage))
        return FakeOrderResult("L-1", symbol)

    async def open_short(self, symbol, quantity, leverage=1):
        self.calls.append(("open_short", symbol, quantity, leverage))
        return FakeOrderResult("S-1", symbol)

    async def close_long(self, symbol, quantity=0):
        self.calls.append(("close_long", symbol, quantity))
        return FakeOrderResult("L-2", symbol)

    async def close_short(self, symbol, quantity=0):
        self.calls.append(("close_short", symbol, quantity))
        return FakeOrderResult("S-2", symbol)

    async def close(self):
        self.closed = True


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def fake_config(monkeypatch):
    monkeypatch.setattr(trading_module, "get_config", lambda: {
        "binance_api_key": "k", "binance_secret_key": "s", "proxy_url": ""
    })


# --- close_position ---


def test_close_position_long_calls_close_long(monkeypatch, client, fake_config):
    trader = FakeTrader([{"symbol": "BTCUSDT", "side": "long", "positionAmt": 0.5}])
    monkeypatch.setattr(trading_module, "create_binance_trader", lambda *a, **kw: trader)

    r = client.post("/api/trading/positions/BTCUSDT/close")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "closed"
    assert body["side"] == "long"
    assert ("close_long", "BTCUSDT", 0) in trader.calls
    assert ("close_short", "BTCUSDT", 0) not in trader.calls
    assert trader.closed is True


def test_close_position_short_calls_close_short(monkeypatch, client, fake_config):
    trader = FakeTrader([{"symbol": "ETHUSDT", "side": "short", "positionAmt": 2.0}])
    monkeypatch.setattr(trading_module, "create_binance_trader", lambda *a, **kw: trader)

    r = client.post("/api/trading/positions/ETHUSDT/close")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "closed"
    assert body["side"] == "short"
    assert ("close_short", "ETHUSDT", 0) in trader.calls
    assert ("close_long", "ETHUSDT", 0) not in trader.calls
    assert trader.closed is True


def test_close_position_returns_error_when_no_position(monkeypatch, client, fake_config):
    trader = FakeTrader([])
    monkeypatch.setattr(trading_module, "create_binance_trader", lambda *a, **kw: trader)

    r = client.post("/api/trading/positions/XRPUSDT/close")
    assert r.status_code == 200
    assert "error" in r.json()
    # No close call should be made if there's no position
    assert trader.calls == []
    # But the trader should still be cleaned up
    assert trader.closed is True


def test_close_position_without_api_keys_returns_error(client):
    r = client.post("/api/trading/positions/BTCUSDT/close")
    assert r.status_code == 200
    assert r.json() == {"error": "Binance API not configured"}


# --- execute_trade ---


def test_execute_trade_with_explicit_open_long(monkeypatch, client, fake_config):
    trader = FakeTrader([])
    monkeypatch.setattr(trading_module, "create_binance_trader", lambda *a, **kw: trader)

    r = client.post("/api/trading/trades", json={
        "token": "BTC", "action": "open_long", "quantity": 0.1
    })
    assert r.status_code == 200
    assert r.json()["status"] == "executed"
    assert r.json()["action"] == "open_long"
    assert ("open_long", "BTCUSDT", 0.1, 1) in trader.calls
    assert trader.closed is True


def test_execute_trade_with_explicit_open_short(monkeypatch, client, fake_config):
    trader = FakeTrader([])
    monkeypatch.setattr(trading_module, "create_binance_trader", lambda *a, **kw: trader)

    r = client.post("/api/trading/trades", json={
        "token": "ETH", "action": "open_short", "quantity": 0.5
    })
    assert r.status_code == 200
    assert r.json()["status"] == "executed"
    assert r.json()["action"] == "open_short"
    assert ("open_short", "ETHUSDT", 0.5, 1) in trader.calls


def test_execute_trade_with_explicit_close_long(monkeypatch, client, fake_config):
    trader = FakeTrader([])
    monkeypatch.setattr(trading_module, "create_binance_trader", lambda *a, **kw: trader)

    r = client.post("/api/trading/trades", json={
        "token": "BTC", "action": "close_long", "quantity": 0.1
    })
    assert r.status_code == 200
    assert ("close_long", "BTCUSDT", 0.1) in trader.calls


def test_execute_trade_with_explicit_close_short(monkeypatch, client, fake_config):
    trader = FakeTrader([])
    monkeypatch.setattr(trading_module, "create_binance_trader", lambda *a, **kw: trader)

    r = client.post("/api/trading/trades", json={
        "token": "BTC", "action": "close_short", "quantity": 0.1
    })
    assert r.status_code == 200
    assert ("close_short", "BTCUSDT", 0.1) in trader.calls


def test_execute_trade_rejects_unknown_action(monkeypatch, client, fake_config):
    trader = FakeTrader([])
    monkeypatch.setattr(trading_module, "create_binance_trader", lambda *a, **kw: trader)

    r = client.post("/api/trading/trades", json={
        "token": "BTC", "action": "moon", "quantity": 0.1
    })
    # Pydantic should reject unknown action values
    assert r.status_code == 422
    # No trader call should have been made
    assert trader.calls == []


def test_execute_trade_default_is_open_long(monkeypatch, client, fake_config):
    """Without explicit action, defaults to open_long (back-compat with frontend)."""
    trader = FakeTrader([])
    monkeypatch.setattr(trading_module, "create_binance_trader", lambda *a, **kw: trader)

    r = client.post("/api/trading/trades", json={"signal_id": 42, "token": "BTC"})
    assert r.status_code == 200
    assert r.json()["action"] == "open_long"
    assert ("open_long", "BTCUSDT", 0.01, 1) in trader.calls


def test_execute_trade_without_api_keys_returns_error(client):
    r = client.post("/api/trading/trades", json={"token": "BTC", "action": "open_long"})
    assert r.status_code == 200
    assert r.json() == {"error": "Binance API not configured"}


# --- signal scan config (Phase 2.4) ---


def test_update_config_persists_signal_scan_enabled(client, db_init):
    """PUT /api/trading/config must persist signal_scan_enabled to the DB."""
    # Set a known value
    r = client.put("/api/trading/config", json={"signal_scan_enabled": True})
    assert r.status_code == 200
    assert r.json() == {"status": "updated"}

    # Read it back via GET
    r2 = client.get("/api/trading/config")
    assert r2.status_code == 200
    assert r2.json()["config"].get("signal_scan_enabled") in (1, True)


def test_update_config_persists_signal_scan_interval(client, db_init):
    """PUT /api/trading/config must persist signal_scan_interval_minutes to the DB."""
    r = client.put("/api/trading/config", json={"signal_scan_interval_minutes": 7})
    assert r.status_code == 200
    assert r.json() == {"status": "updated"}

    r2 = client.get("/api/trading/config")
    assert r2.status_code == 200
    assert r2.json()["config"].get("signal_scan_interval_minutes") == 7
