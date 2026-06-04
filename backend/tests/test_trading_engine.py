import pytest

from services.risk import RiskConfig
from services.trading_engine import TradingEngine


def _stub_trader(monkeypatch):
    """Replace BinanceFuturesTrader with a stub so we don't need real keys."""
    class _Stub:
        def __init__(self, *a, **kw): pass
    monkeypatch.setattr("services.trading_engine.create_binance_trader", lambda *a, **kw: _Stub())


def test_constructor_requires_risk_config(monkeypatch):
    _stub_trader(monkeypatch)
    cfg = RiskConfig.from_config_store()
    engine = TradingEngine("k", "s", False, "", risk=cfg)
    assert engine._risk is cfg


def test_constructor_rejects_missing_risk(monkeypatch):
    _stub_trader(monkeypatch)
    with pytest.raises(TypeError):
        TradingEngine("k", "s", False, "")  # no risk kwarg


@pytest.mark.asyncio
async def test_execute_signal_uses_risk_position_size(monkeypatch):
    _stub_trader(monkeypatch)

    class _T:
        async def get_balance(self): return {"availableBalance": 1000.0}
        async def get_positions(self): return []
        async def open_long(self, sym, qty):
            class _R: order_id = "ord_x"
            return _R()
        async def get_market_price(self, sym): return 100.0
        async def set_take_profit(self, *a, **kw): pass
        async def set_stop_loss(self, *a, **kw): pass

    cfg = RiskConfig(max_position_pct=0.03, max_position_usd=50.0,
                     max_open_positions=5, tp_pct=0.10, sl_pct=0.05)
    monkeypatch.setattr("services.trading_engine.create_binance_trader", lambda *a, **kw: _T())
    monkeypatch.setattr("services.trading_engine.insert_trade", lambda *a, **kw: 1)
    monkeypatch.setattr("services.trading_engine.count_open_positions", lambda *a, **kw: 0)
    monkeypatch.setattr("services.trading_engine.get_db", lambda: _FakeConn())
    engine = TradingEngine("k", "s", risk=cfg)
    result = await engine.execute_signal({"token": "BTC", "sentiment": "bullish", "signal_id": 1})
    assert result["status"] == "executed"
    # 1000 * 0.03 = 30, cap is 50, so size = 30
    assert result["quantity"] == pytest.approx(30.0)
    # tp=100*1.10=110, sl=100*0.95=95
    assert result["tp_price"] == pytest.approx(110.0)
    assert result["sl_price"] == pytest.approx(95.0)


class _FakeConn:
    def cursor(self): return _FakeCursor()
    def commit(self): pass
    def close(self): pass


class _FakeCursor:
    def execute(self, *a, **kw): pass
    def fetchone(self): return (0,)
    def fetchall(self): return []


@pytest.mark.asyncio
async def test_execute_signal_skips_bearish(monkeypatch):
    """Bearish signals are out of scope for the Binance long-only engine.

    Short-selling lives in services/short_selling_engine.py (data fetch only)
    or a separate short trader (not yet built). Engine must skip non-bullish
    signals deterministically and never call the trader.
    """
    _stub_trader(monkeypatch)

    class _T:
        def __init__(self):
            self.balance_called = False
        async def get_balance(self):
            self.balance_called = True
            return {"availableBalance": 1000.0}

    trader = _T()
    monkeypatch.setattr("services.trading_engine.create_binance_trader", lambda *a, **kw: trader)

    cfg = RiskConfig.from_config_store()
    engine = TradingEngine("k", "s", risk=cfg)
    result = await engine.execute_signal({"token": "BTC", "sentiment": "bearish", "signal_id": 1})

    assert result["status"] == "skipped"
    assert "bullish" in result["reason"].lower()
    # Short-circuit must happen before balance fetch
    assert not trader.balance_called
