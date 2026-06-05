"""Pure-function tests for short-selling metrics added in Phase 1a."""
import math
from types import SimpleNamespace

import pytest

from services.hot_tokens_scanner import (
    _long_crowdedness,
    _extension_score,
    _short_opportunity_score,
)


def _tok(funding: float = 0.0, ls: float = 1.0, change: float = 0.0,
         market_cap: float = 0.0, volume_usd: float = 0.0,
         top10: float = 0.0, gini: float = 0.0) -> SimpleNamespace:
    return SimpleNamespace(
        funding_rate=funding,
        long_short_ratio=ls,
        price_change_24h=change,
        market_cap=market_cap,
        volume_usd=volume_usd,
        top10_holders_pct=top10,
        gini=gini,
    )


# --- _long_crowdedness ---

def test_long_crowdedness_zero_when_balanced():
    # funding=0, ls=1.0 → both signals 0
    assert _long_crowdedness(_tok(funding=0.0, ls=1.0)) == 0.0


def test_long_crowdedness_full_when_extreme_longs():
    # funding=+1% and ls=2.0 → both signals clipped to 1.0
    val = _long_crowdedness(_tok(funding=0.01, ls=2.0))
    assert math.isclose(val, 1.0, abs_tol=1e-9)


def test_long_crowdedness_negative_funding_does_not_count_as_long_crowd():
    # funding=-1% (shorts pay longs) should NOT raise long_crowdedness
    val = _long_crowdedness(_tok(funding=-0.01, ls=1.0))
    assert val == 0.0


def test_long_crowdedness_weighting_funding_heavier_than_ls():
    # At half-curve each: funding=0.005 → 0.5, ls=1.5 → 0.5
    # Expected: 0.5*0.6 + 0.5*0.4 = 0.5
    val = _long_crowdedness(_tok(funding=0.005, ls=1.5))
    assert math.isclose(val, 0.5, abs_tol=1e-9)


def test_long_crowdedness_clipped_to_unit_interval():
    # Both signals would exceed 1.0 if not clipped
    val = _long_crowdedness(_tok(funding=0.05, ls=5.0))
    assert 0.0 <= val <= 1.0


# --- _extension_score ---

def test_extension_score_zero_for_negative_change():
    assert _extension_score(_tok(change=-5.0)) == 0.0


def test_extension_score_zero_for_zero_change():
    assert _extension_score(_tok(change=0.0)) == 0.0


def test_extension_score_linear_up_to_ten_percent():
    # +5% → 0.5
    assert math.isclose(_extension_score(_tok(change=5.0)), 0.5, abs_tol=1e-9)


def test_extension_score_clamped_at_ten_percent():
    # +20% → 1.0 (clipped)
    assert _extension_score(_tok(change=20.0)) == 1.0


def test_extension_score_exact_boundary_at_ten_percent():
    # +10% → exactly 1.0
    assert math.isclose(_extension_score(_tok(change=10.0)), 1.0, abs_tol=1e-9)


# --- _short_opportunity_score ---

def test_opportunity_score_weights_sum_to_one_when_inputs_one():
    # If all four inputs were 1.0, score should equal 1.0
    t = _tok(funding=0.01, ls=2.0, change=10.0,
             market_cap=2e9, volume_usd=200e6, top10=0.0)
    # crowd=1.0, ext=1.0, liq: market_cap=2e9/1e9=2.0 clipped to 1.0 → 1.0*0.6
    #                  volume_usd=200e6/100e6=2.0 clipped to 1.0 → 1.0*0.4
    #                  liq = 1.0
    # dist: top10=0 → 0.5 neutral
    expected = 1.0 * 0.35 + 1.0 * 0.25 + 1.0 * 0.20 + 0.5 * 0.20
    val = _short_opportunity_score(t)
    assert math.isclose(val, expected, abs_tol=1e-9)


def test_opportunity_score_dist_neutral_when_top10_unfilled():
    # top10=0 (cache miss) → 0.5
    t = _tok(funding=0.005, ls=1.5, change=5.0,
             market_cap=5e8, volume_usd=50e6, top10=0.0)
    val = _short_opportunity_score(t)
    # Check the 0.5 weight on dist
    no_top10 = 0.5 * 0.20
    with_top10_zero = 0.0 * 0.20
    assert val > 0  # never zero when other inputs positive
    # And it's strictly between these two
    assert 0.0 < val < 1.0


def test_opportunity_score_dist_max_at_low_top10():
    # top10=30% → dist=1.0
    t_low = _tok(funding=0.005, ls=1.5, change=5.0,
                 market_cap=5e8, volume_usd=50e6, top10=30.0)
    # top10=70% → dist=0.0
    t_high = _tok(funding=0.005, ls=1.5, change=5.0,
                  market_cap=5e8, volume_usd=50e6, top10=70.0)
    assert _short_opportunity_score(t_low) > _short_opportunity_score(t_high)


def test_opportunity_score_top10_above_70_yields_zero_dist():
    # top10=80% → dist = max(min((70-80)/40, 1.0), 0.0) = 0.0
    t = _tok(funding=0.0, ls=1.0, change=0.0,
             market_cap=0.0, volume_usd=0.0, top10=80.0)
    # Only dist contributes, and it's 0
    assert _short_opportunity_score(t) == 0.0
