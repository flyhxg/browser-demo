"""Tests for the /api/hot_tokens/sectors endpoint (UI overhaul Phase 2.1)."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


class FakeScanner:
    """Mimics the hot-tokens scanner's public surface used by the sectors endpoint."""
    def __init__(self, tokens: dict[str, object] | None = None):
        self._hot_tokens = tokens or {}


def _make_token(symbol: str, sector: str = "其他") -> SimpleNamespace:
    """Build a minimal token stub with a `sector` attribute."""
    return SimpleNamespace(symbol=symbol, sector=sector)


def test_sectors_excludes_default_other():
    """Tokens with sector='其他' (the scanner fallback) must be excluded."""
    tokens = {
        "BTCUSDT": _make_token("BTCUSDT", "Layer 1"),
        "ETHUSDT": _make_token("ETHUSDT", "Smart Contract Platform"),
        "OBSCURE": _make_token("OBSCURE", "其他"),
    }
    fake = FakeScanner(tokens)

    with patch("api.hot_tokens.get_scanner", return_value=fake):
        from main import app
        client = TestClient(app)
        resp = client.get("/api/hot_tokens/sectors")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["sectors"] == {
        "BTCUSDT": "Layer 1",
        "ETHUSDT": "Smart Contract Platform",
    }
    assert "OBSCURE" not in body["sectors"]


def test_sectors_handles_empty_scanner():
    """Empty hot-tokens dict must return count=0, empty sectors dict."""
    fake = FakeScanner({})

    with patch("api.hot_tokens.get_scanner", return_value=fake):
        from main import app
        client = TestClient(app)
        resp = client.get("/api/hot_tokens/sectors")

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"sectors": {}, "count": 0}


def test_sectors_skips_tokens_without_sector_attr():
    """Tokens missing the `sector` attribute (e.g., older builds) must not crash the endpoint."""
    tokens = {
        "NEWUSDT": SimpleNamespace(symbol="NEWUSDT"),  # no .sector at all
        "BTCUSDT": _make_token("BTCUSDT", "Layer 1"),
    }
    fake = FakeScanner(tokens)

    with patch("api.hot_tokens.get_scanner", return_value=fake):
        from main import app
        client = TestClient(app)
        resp = client.get("/api/hot_tokens/sectors")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["sectors"] == {"BTCUSDT": "Layer 1"}
