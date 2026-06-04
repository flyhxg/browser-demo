"""Risk configuration and pure pricing functions for trading.

All risk parameters live here. TradingEngine and polymarket code both
import from this module instead of hardcoding percentages.
"""
from __future__ import annotations

from dataclasses import dataclass

from services.config_store import get_config


@dataclass(frozen=True)
class RiskConfig:
    max_position_pct: float       # fraction of available balance (0.02 = 2%)
    max_position_usd: float       # absolute cap per position
    max_open_positions: int       # max concurrent open positions
    tp_pct: float                 # take-profit as decimal (0.05 = 5%)
    sl_pct: float                 # stop-loss as decimal (0.03 = 3%)
    min_position_usd: float = 10.0  # floor below which a signal is rejected

    @classmethod
    def from_config_store(cls, config: dict | None = None) -> "RiskConfig":
        cfg = config if config is not None else get_config()
        return cls(
            max_position_pct=cfg.get("position_pct", 0.02),
            max_position_usd=cfg.get("max_position_size_usd", 100.0),
            max_open_positions=cfg.get("max_open_positions", 5),
            tp_pct=cfg.get("tp_percentage", 5.0) / 100,
            sl_pct=cfg.get("sl_percentage", 3.0) / 100,
        )

    @classmethod
    def polymarket(cls) -> "RiskConfig":
        # Polymarket risk is intentionally hardcoded (not DB-backed) per ADR-XXXX.
        # max_position_pct=1.0 means "use all available" (no leverage on prediction markets).
        return cls(
            max_position_pct=1.0,
            max_position_usd=10_000.0,
            max_open_positions=10,
            tp_pct=0.05,
            sl_pct=0.15,
        )


def position_size(available: float, risk: RiskConfig) -> float:
    """Position size = min(balance * pct, hard cap)."""
    return min(available * risk.max_position_pct, risk.max_position_usd)
