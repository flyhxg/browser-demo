"""Regression: _broadcast_update must not reference removed HotToken fields.

Phase 1a Task 1 removed `crowdedness_score`, `squeeze_risk`, `rebound_potential`
from the HotToken dataclass. _broadcast_update was overlooked and kept
referencing them, so every scanner tick threw AttributeError, the
WebSocket bus never received `hot_tokens_update`, and live updates
silently stopped.

This test exercises the real HotTokensScanner._broadcast_update method
and asserts the broadcast row uses only fields that exist on HotToken.
"""
import asyncio
import dataclasses
import inspect
import re

import pytest

from services.hot_tokens_scanner import HotToken, HotTokensScanner
from services import ws_manager


def _make_scanner_with(token: HotToken) -> HotTokensScanner:
    """Bypass __init__ (which would try to talk to Binance) and seed _hot_tokens."""
    scanner = HotTokensScanner.__new__(HotTokensScanner)
    scanner._hot_tokens = {token.symbol: token}
    scanner._running = False
    return scanner


def test_broadcast_update_method_body_references_no_removed_fields():
    """Static check: source of _broadcast_update must only read real fields."""
    real_field_names = {f.name for f in dataclasses.fields(HotToken)}
    source = inspect.getsource(HotTokensScanner._broadcast_update)
    accessed = set(re.findall(r"\bt\.(\w+)", source))

    missing = accessed - real_field_names
    assert not missing, (
        f"_broadcast_update references removed HotToken fields: {missing}. "
        f"Available fields: {sorted(real_field_names)}"
    )


def test_broadcast_update_does_not_raise_attribute_error():
    """End-to-end smoke: call the real method and ensure no AttributeError."""
    token = HotToken(
        symbol="ETHUSDT",
        price=3000.0,
        price_change_24h=5.0,
        funding_rate=0.0001,
        long_short_ratio=1.5,
        long_crowdedness=0.4,
        long_squeeze_risk=0.3,
        extension_score=0.5,
        short_risk_rating="medium",
        short_grade="A",
        short_opportunity_score=0.6,
    )
    scanner = _make_scanner_with(token)

    async def run():
        captured = []

        async def fake_broadcast(payload):
            captured.append(payload)
        ws_manager.manager.broadcast = fake_broadcast
        await scanner._broadcast_update()
        return captured

    sent = asyncio.run(run())
    assert len(sent) == 1
    payload = sent[0]
    assert payload["type"] == "hot_tokens_update"
    assert len(payload["data"]) == 1
    row = payload["data"][0]

    # Row must not contain keys for removed fields
    assert "crowdedness_score" not in row
    assert "squeeze_risk" not in row
    assert "rebound_potential" not in row

    # Row must contain the corrected-direction fields
    assert "long_crowdedness" in row
    assert "long_squeeze_risk" in row
    assert "extension_score" in row
    assert "short_grade" in row
    assert "short_opportunity_score" in row
    assert row["long_crowdedness"] == 0.4
    assert row["short_grade"] == "A"


def test_broadcast_update_empty_dict_when_no_tokens():
    """No tokens in store → broadcast empty list (not crash)."""
    scanner = HotTokensScanner.__new__(HotTokensScanner)
    scanner._hot_tokens = {}
    scanner._running = False

    async def run():
        captured = []

        async def fake_broadcast(payload):
            captured.append(payload)
        ws_manager.manager.broadcast = fake_broadcast
        await scanner._broadcast_update()
        return captured

    sent = asyncio.run(run())
    assert sent == [{"type": "hot_tokens_update", "data": []}]
