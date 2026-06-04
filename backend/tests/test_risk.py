import math

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


def test_from_config_store_uses_position_pct_and_max_open_positions():
    cfg = RiskConfig.from_config_store(config={"position_pct": 0.05, "max_open_positions": 7})
    assert cfg.max_position_pct == 0.05
    assert cfg.max_open_positions == 7


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


def test_position_size_negative_balance_returns_negative():
    # Negative balance: position_size returns a negative number.
    # The engine's size < min_position_usd check catches this and skips.
    # This test documents the contract — caller must validate.
    assert position_size(-100.0, _cfg()) == -2.0


def test_position_size_very_large_balance_caps_at_max_usd():
    # 1e15 * 0.02 = 2e13, must be capped at 100
    assert position_size(1e15, _cfg()) == 100.0


def test_position_size_nan_input_returns_nan():
    # KNOWN ISSUE: min(NaN, x) is NaN. The engine's size < min check
    # returns False for NaN, so the engine would NOT skip — leading to
    # a NaN-sized position. This is caller-responsibility for now.
    result = position_size(float("nan"), _cfg())
    assert math.isnan(result)


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


def test_polymarket_sl_tp_matches_legacy_values():
    """Regression: must equal pre-refactor api/polymarket.py:230-231 defaults (0.15/0.05)."""
    cfg = RiskConfig.polymarket()
    assert cfg.sl_pct == 0.15
    assert cfg.tp_pct == 0.05


def test_polymarket_execute_signal_sl_tp_math():
    """Regression: must equal pre-refactor api/polymarket.py:341-346 hardcoded values."""
    cfg = RiskConfig.polymarket()
    # SELL (bearish): sl=entry*1.15, tp=entry*0.95 — drift, use approx
    assert stop_loss_price(100.0, "bearish", cfg) == pytest.approx(115.0, abs=1e-9)
    assert take_profit_price(100.0, "bearish", cfg) == pytest.approx(95.0, abs=1e-9)
    # BUY (bullish): sl=entry*0.85, tp=entry*1.05 — drift, use approx
    assert stop_loss_price(100.0, "bullish", cfg) == pytest.approx(85.0, abs=1e-9)
    assert take_profit_price(100.0, "bullish", cfg) == pytest.approx(105.0, abs=1e-9)
