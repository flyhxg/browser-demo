from services.config_store import DEFAULT_CONFIG
from services.risk import RiskConfig


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
