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
