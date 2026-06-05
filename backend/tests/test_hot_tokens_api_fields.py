"""API contract: /api/hot_tokens/ and /api/hot_tokens/{symbol}/analysis must
expose all 13 short-selling fields with values populated from the scanner
(no getattr fallbacks hiding the absence of data)."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.hot_tokens_scanner import HotToken


EXPECTED_LIST_FIELDS = {
    "symbol", "price", "price_change_24h", "volume_24h", "volume_usd",
    "funding_rate", "long_short_ratio", "open_interest", "liquidation_price",
    "heat_score", "heat_rank", "updated_at",
    "long_crowdedness", "long_squeeze_risk", "extension_score",
    "short_risk_rating", "short_grade", "short_opportunity_score",
    "oi_usd", "funding_annualized",
    # Phase 1b will fill these from FundamentalsCache; for now they should
    # be present in the response even if zero.
    "market_cap", "consecutive_up_days", "trend_strength", "sector",
    "top10_holders_pct", "gini", "fdv_mcap_ratio",
    "high_24h", "low_24h", "atr",
    "recommended_leverage", "stop_loss_price", "take_profit_price",
}


def _stub_token() -> HotToken:
    """Return a fully-populated HotToken so we can assert the response shape."""
    return HotToken(
        symbol="BTCUSDT",
        price=60000.0,
        price_change_24h=5.0,
        volume_24h=100.0,
        volume_usd=6_000_000_000.0,
        funding_rate=0.005,
        long_short_ratio=1.8,
        open_interest=50000.0,
        liquidation_price=57000.0,
        heat_score=0.85,
        heat_rank=1,
        updated_at="2026-06-05T00:00:00Z",
        long_crowdedness=0.72,
        long_squeeze_risk=0.65,
        extension_score=0.5,
        short_risk_rating="high",
        short_grade="A",
        short_opportunity_score=0.68,
        oi_usd=3_000_000_000.0,
        funding_annualized=547.5,
    )


class _FakeScanner:
    def __init__(self, token: HotToken) -> None:
        self._hot_tokens = {token.symbol: token}
        self._running = True

    def get_hot_tokens(self, limit: int = 50) -> list[HotToken]:
        return list(self._hot_tokens.values())[:limit]


def test_list_endpoint_returns_all_short_fields():
    token = _stub_token()
    with patch("api.hot_tokens.get_scanner", return_value=_FakeScanner(token)):
        from main import app
        client = TestClient(app)
        resp = client.get("/api/hot_tokens/?limit=5")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    row = body[0]
    missing = EXPECTED_LIST_FIELDS - set(row.keys())
    assert not missing, f"Missing fields: {missing}"
    # Hot fields should carry real values, not defaults
    assert row["short_grade"] == "A"
    assert row["long_crowdedness"] == pytest.approx(0.72)
    assert row["oi_usd"] == pytest.approx(3_000_000_000.0)


def test_analysis_endpoint_returns_ohlcv_derived_fields():
    token = _stub_token()
    with patch("api.hot_tokens.get_scanner", return_value=_FakeScanner(token)):
        from main import app
        client = TestClient(app)
        resp = client.get("/api/hot_tokens/BTCUSDT/analysis")

    assert resp.status_code == 200
    body = resp.json()
    for f in ("high_24h", "low_24h", "atr", "rebound_multiple",
              "consecutive_up_days", "low_7d"):
        assert f in body, f"Missing: {f}"
    assert "recommendation" in body
    # Recommendation should reflect the corrected long-side direction
    assert "long" in body["recommendation"].lower() or "extreme" in body["recommendation"].lower()
