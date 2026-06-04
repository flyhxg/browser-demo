import pytest

from services.config_store import DEFAULT_CONFIG
from services.risk import RiskConfig, stop_loss_price, take_profit_price


def test_risk_config_is_frozen_dataclass():
    cfg = RiskConfig(
        max_position_pct=0.02,
        max_position_usd=100.0,
        max_open_positions=5,
        tp_pct=0.05,
        sl_pct=0.03,
    )
    assert cfg.max_position_pct == 0.02
    assert cfg.max_position_usd == 100.0
    # frozen: mutation must raise
    import dataclasses
    assert dataclasses.is_dataclass(cfg) and cfg.__dataclass_params__.frozen is True


def test_from_config_store_reads_defaults():
    # DEFAULT_CONFIG has tp_percentage=5.0 (means 5%) — must convert to 0.05
    cfg = RiskConfig.from_config_store()
    assert cfg.tp_pct == DEFAULT_CONFIG["tp_percentage"] / 100
    assert cfg.sl_pct == DEFAULT_CONFIG["sl_percentage"] / 100
    assert cfg.max_position_usd == DEFAULT_CONFIG["max_position_size_usd"]


def test_from_config_store_with_missing_keys_uses_safe_defaults():
    cfg = RiskConfig.from_config_store(config={"tp_percentage": 10.0})
    assert cfg.tp_pct == 0.10  # 10.0 → 0.10
    assert cfg.sl_pct == 0.03  # fallback default
    assert cfg.max_position_pct == 0.02  # fallback default


def test_polymarket_returns_known_constants():
    cfg = RiskConfig.polymarket()
    assert cfg.tp_pct == 0.05
    assert cfg.sl_pct == 0.15
    assert cfg.max_position_pct == 1.0
    assert cfg.max_position_usd == 10_000.0
    assert cfg.max_open_positions == 10


from services.risk import position_size


def _cfg(**overrides) -> RiskConfig:
    base = dict(max_position_pct=0.02, max_position_usd=100.0, max_open_positions=5,
                tp_pct=0.05, sl_pct=0.03)
    base.update(overrides)
    return RiskConfig(**base)


def test_position_size_uses_pct_of_available():
    assert position_size(1000.0, _cfg(max_position_pct=0.02)) == 20.0


def test_position_size_caps_at_max_usd():
    # 1000 * 0.5 = 500, but cap is 100
    assert position_size(1000.0, _cfg(max_position_pct=0.5, max_position_usd=100.0)) == 100.0


def test_position_size_zero_balance_returns_zero():
    assert position_size(0.0, _cfg()) == 0.0


def test_position_size_polymarket_uses_full_balance_when_under_cap():
    cfg = RiskConfig.polymarket()
    # 5000 * 1.0 = 5000, but cap is 10_000, so result is 5000
    assert position_size(5000.0, cfg) == 5000.0


def test_take_profit_bullish():
    cfg = _cfg(tp_pct=0.05)
    assert take_profit_price(100.0, "bullish", cfg) == 105.0


def test_take_profit_bearish():
    cfg = _cfg(tp_pct=0.05)
    assert take_profit_price(100.0, "bearish", cfg) == 95.0


def test_stop_loss_bullish():
    cfg = _cfg(sl_pct=0.03)
    assert stop_loss_price(100.0, "bullish", cfg) == 97.0


def test_stop_loss_bearish():
    cfg = _cfg(sl_pct=0.03)
    assert stop_loss_price(100.0, "bearish", cfg) == 103.0


def test_polymarket_tp_sl_via_polymarket_config():
    cfg = RiskConfig.polymarket()
    # BUY side (bullish): tp=entry*1.05, sl=entry*0.85
    assert take_profit_price(100.0, "bullish", cfg) == 105.0
    assert stop_loss_price(100.0, "bullish", cfg) == pytest.approx(85.0, abs=1e-9)
    # SELL side (bearish): tp=entry*0.95, sl=entry*1.15
    assert take_profit_price(100.0, "bearish", cfg) == 95.0
    assert stop_loss_price(100.0, "bearish", cfg) == pytest.approx(115.0, abs=1e-9)
