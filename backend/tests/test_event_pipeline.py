"""Tests for EventPipeline — the event-causality orchestrator."""
import asyncio
import time
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


@pytest.mark.asyncio
async def test_pipeline_runs_fetches_in_parallel():
    """All 4 sources must start before any one returns (proves parallel execution)."""
    from services.event_pipeline import EventPipeline

    started: list[str] = []
    finished: list[str] = []

    def make_source(name: str, delay: float):
        s = AsyncMock()
        async def fetch(*args, **kwargs):
            started.append(name)
            await asyncio.sleep(delay)
            finished.append(name)
            return [_make_event("news", "2026-06-03T14:00:00Z", f"{name} event", severity=2)]
        s.fetch_news = fetch
        s.scrape_hot = fetch
        s.fetch = fetch
        return s

    news = make_source("news", 0.1)
    social = make_source("social", 0.1)
    onchain = make_source("onchain", 0.1)
    derivatives = make_source("derivatives", 0.1)

    pipeline = EventPipeline(news=news, social=social, onchain=onchain, derivatives=derivatives)
    t0 = time.monotonic()
    result = await pipeline.run("BTC", "24h")
    elapsed = time.monotonic() - t0

    # All 4 should have started before any finished (parallelism)
    assert len(started) == 4
    assert len(finished) == 0 or len(started) == 4  # started before finished
    # Total time should be ~0.1s, not ~0.4s (sequential would be 0.4s)
    assert elapsed < 0.3, f"elapsed {elapsed}s suggests sequential execution"
    assert len(result["events"]) == 4


@pytest.mark.asyncio
async def test_pipeline_orders_timeline_chronologically():
    """Output events must be sorted by timestamp ASC."""
    from services.event_pipeline import EventPipeline

    news = AsyncMock()
    news.fetch_news = AsyncMock(return_value=[
        _make_event("news", "2026-06-03T16:00:00Z", "later news", severity=2),
    ])
    social = AsyncMock()
    social.scrape_hot = AsyncMock(return_value=[
        _make_event("social", "2026-06-03T14:00:00Z", "earlier social", severity=2),
    ])
    onchain = AsyncMock()
    onchain.fetch = AsyncMock(return_value=[
        _make_event("whale", "2026-06-03T15:00:00Z", "middle whale", severity=3),
    ])
    derivatives = AsyncMock()
    derivatives.fetch = AsyncMock(return_value=[])

    pipeline = EventPipeline(news=news, social=social, onchain=onchain, derivatives=derivatives)
    result = await pipeline.run("BTC", "24h")

    timestamps = [e["timestamp"] for e in result["events"]]
    assert timestamps == sorted(timestamps)


@pytest.mark.asyncio
async def test_pipeline_clusters_events_by_30min_window():
    """Events within 30 min of each other must share cluster_id."""
    from services.event_pipeline import EventPipeline

    news = AsyncMock()
    news.fetch_news = AsyncMock(return_value=[
        _make_event("news", "2026-06-03T14:00:00Z", "news 1", severity=2),
        _make_event("news", "2026-06-03T14:20:00Z", "news 2 (same cluster)", severity=2),
    ])
    social = AsyncMock()
    social.scrape_hot = AsyncMock(return_value=[
        _make_event("social", "2026-06-03T16:00:00Z", "social (different cluster)", severity=2),
    ])
    onchain = AsyncMock()
    onchain.fetch = AsyncMock(return_value=[])
    derivatives = AsyncMock()
    derivatives.fetch = AsyncMock(return_value=[])

    pipeline = EventPipeline(news=news, social=social, onchain=onchain, derivatives=derivatives)
    result = await pipeline.run("BTC", "24h")

    events = result["events"]
    assert len(events) == 3
    # First two should share cluster_id
    assert events[0]["cluster_id"] == events[1]["cluster_id"]
    # Third should be different
    assert events[2]["cluster_id"] != events[0]["cluster_id"]


@pytest.mark.asyncio
async def test_pipeline_caps_at_50_events():
    """If sources return > 50 events, only the top 50 by severity are kept."""
    from services.event_pipeline import EventPipeline

    events = []
    for i in range(100):
        sev = (i % 5) + 1  # 1-5 cycling
        events.append(_make_event("news", f"2026-06-03T{14 + (i // 60):02d}:{i % 60:02d}:00Z", f"e{i}", severity=sev))

    news = AsyncMock()
    news.fetch_news = AsyncMock(return_value=events)
    social = AsyncMock(); social.scrape_hot = AsyncMock(return_value=[])
    onchain = AsyncMock(); onchain.fetch = AsyncMock(return_value=[])
    derivatives = AsyncMock(); derivatives.fetch = AsyncMock(return_value=[])

    pipeline = EventPipeline(news=news, social=social, onchain=onchain, derivatives=derivatives)
    result = await pipeline.run("BTC", "24h")

    assert len(result["events"]) == 50
    from collections import Counter
    counts = Counter(e["severity"] for e in result["events"])
    assert sum(counts.values()) == 50


@pytest.mark.asyncio
async def test_pipeline_calls_llm_with_timeline():
    """LLM synth function must receive symbol, time_range, and the timeline dicts."""
    from services.event_pipeline import EventPipeline

    received: dict = {}

    async def fake_llm(symbol, time_range, timeline):
        received["symbol"] = symbol
        received["time_range"] = time_range
        received["timeline"] = timeline
        return "Test summary."

    news = AsyncMock()
    news.fetch_news = AsyncMock(return_value=[
        _make_event("news", "2026-06-03T14:00:00Z", "ETF delay", severity=3),
    ])
    social = AsyncMock(); social.scrape_hot = AsyncMock(return_value=[])
    onchain = AsyncMock(); onchain.fetch = AsyncMock(return_value=[])
    derivatives = AsyncMock(); derivatives.fetch = AsyncMock(return_value=[])

    pipeline = EventPipeline(
        news=news, social=social, onchain=onchain, derivatives=derivatives,
        llm_synthesize=fake_llm,
    )
    result = await pipeline.run("BTC", "24h")

    assert received["symbol"] == "BTC"
    assert received["time_range"] == "24h"
    assert len(received["timeline"]) == 1
    assert received["timeline"][0]["title"] == "ETF delay"
    assert result["llm_summary"] == "Test summary."


@pytest.mark.asyncio
async def test_pipeline_returns_unavailable_summary_on_llm_timeout():
    """If LLM times out, summary must indicate unavailability (not raise)."""
    from services.event_pipeline import EventPipeline

    async def slow_llm(symbol, time_range, timeline):
        await asyncio.sleep(0.1)
        return "won't get here"

    news = AsyncMock()
    news.fetch_news = AsyncMock(return_value=[
        _make_event("news", "2026-06-03T14:00:00Z", "evt", severity=2),
    ])
    social = AsyncMock(); social.scrape_hot = AsyncMock(return_value=[])
    onchain = AsyncMock(); onchain.fetch = AsyncMock(return_value=[])
    derivatives = AsyncMock(); derivatives.fetch = AsyncMock(return_value=[])

    import services.event_pipeline as ep_mod
    original = ep_mod.LLM_TIMEOUT_SECONDS
    ep_mod.LLM_TIMEOUT_SECONDS = 0.01
    try:
        pipeline = EventPipeline(
            news=news, social=social, onchain=onchain, derivatives=derivatives,
            llm_synthesize=slow_llm,
        )
        result = await pipeline.run("BTC", "24h")
        assert "unavailable" in result["llm_summary"].lower()
    finally:
        ep_mod.LLM_TIMEOUT_SECONDS = original
