import json
from pathlib import Path

import pytest


def test_changing_tp_percentage_affects_next_trade(monkeypatch, tmp_path):
    """Write tp_percentage=10 to a temp config.json, instantiate RiskConfig, assert math."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"tp_percentage": 10.0, "sl_percentage": 3.0,
                                    "max_position_size_usd": 100.0,
                                    "position_pct": 0.02, "max_open_positions": 5}))

    # Override CONFIG_PATH in config_store
    monkeypatch.setattr("services.config_store.CONFIG_PATH", cfg_file)

    from services.config_store import get_config
    from services.risk import RiskConfig, take_profit_price

    cfg = RiskConfig.from_config_store()
    # 10.0 means 10% → tp_pct must be 0.10
    assert cfg.tp_pct == 0.10
    # tp_price for bullish at entry=100 must be 110.0 (use approx for IEEE drift)
    assert take_profit_price(100.0, "bullish", cfg) == pytest.approx(110.0, abs=1e-9)
