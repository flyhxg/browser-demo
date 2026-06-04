"""Tests for IntentRouter's event-shape query hook."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest


def test_classify_returns_event_for_why_questions():
    """classify() must return 'event' for 'why did X drop' style messages."""
    from services.intent_router import IntentRouter

    layer = IntentRouter.classify(
        symbols=["BTC"],
        dimensions=None,
        message="why did BTC drop 5% today?",
    )
    assert layer == "event"


def test_classify_returns_event_for_chinese_keywords():
    """Chinese event-shape keywords also trigger 'event' layer."""
    from services.intent_router import IntentRouter

    for msg in [
        "BTC为什么暴跌",
        "ETH发生了什么",
        "SOL突然暴涨",
    ]:
        layer = IntentRouter.classify(symbols=["BTC"], dimensions=None, message=msg)
        assert layer == "event", f"Expected 'event' for message: {msg}"


def test_route_event_dispatches_to_event_pipeline():
    """IntentRouter.route_event must call EventPipeline.run and return its result."""
    from services.intent_router import IntentRouter
    from services.event_pipeline import EventPipeline

    fake_response = {
        "symbol": "BTC",
        "time_range": "24h",
        "events": [{"type": "whale", "title": "test"}],
        "llm_summary": "Test.",
        "overall_confidence": 0.8,
    }

    with patch.object(EventPipeline, "run", new=AsyncMock(return_value=fake_response)):
        router = IntentRouter()
        result = asyncio.run(router.route_event("BTC", "why did BTC drop?"))

    assert result["layer"] == "event"
    assert result["report"] == fake_response
