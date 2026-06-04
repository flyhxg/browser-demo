"""Tests for EventPipeline — the event-causality orchestrator."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest


def _make_event(type_: str, ts: str, title: str, severity: int = 2, **payload):
    return {
        "timestamp": ts,
        "type": type_,
        "title": title,
        "source": "test",
        "url": None,
        "payload": payload,
        "severity": severity,
    }


def test_pipeline_never_raises_on_unexpected_source_exception():
    """EventPipeline.run must never propagate exceptions from sources."""
    from services.event_pipeline import EventPipeline

    news = AsyncMock()
    news.fetch_news = AsyncMock(side_effect=RuntimeError("boom"))
    social = AsyncMock()
    social.scrape_hot = AsyncMock(side_effect=RuntimeError("boom"))
    onchain = AsyncMock()
    onchain.fetch = AsyncMock(side_effect=RuntimeError("boom"))
    derivatives = AsyncMock()
    derivatives.fetch = AsyncMock(side_effect=RuntimeError("boom"))

    pipeline = EventPipeline(
        news=news, social=social, onchain=onchain, derivatives=derivatives
    )

    result = asyncio.run(pipeline.run("BTC", "24h"))

    # All sources failed → empty events, no summary, confidence=0
    assert result["events"] == []
    assert "unavailable" in result["llm_summary"].lower() or "no data" in result["llm_summary"].lower()
    assert result["overall_confidence"] == 0.0
    assert result["symbol"] == "BTC"
    assert result["time_range"] == "24h"
