"""Tests for POST /api/analyze/events endpoint."""
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_analyze_events_returns_pipeline_response():
    """POST /api/analyze/events must return the pipeline's response dict."""
    from api.analysis import router

    app = FastAPI()
    app.include_router(router)

    fake_response = {
        "symbol": "BTC",
        "time_range": "24h",
        "events": [],
        "llm_summary": "Test summary.",
        "overall_confidence": 0.5,
        "fetched_sources": {"news": "ok", "social": "ok", "onchain": "ok", "derivatives": "ok"},
        "fetched_at": "2026-06-04T10:00:00Z",
    }

    with patch("api.analysis.EventPipeline") as MockPipeline:
        mock_instance = MockPipeline.return_value
        mock_instance.run = AsyncMock(return_value=fake_response)
        client = TestClient(app)
        r = client.post("/api/analyze/events", json={"symbol": "BTC", "time_range": "24h"})

    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "BTC"
    assert body["llm_summary"] == "Test summary."
    assert body["overall_confidence"] == 0.5


def test_analyze_events_rejects_invalid_time_range():
    """time_range must be one of 1h, 4h, 24h, 7d — endpoint returns 400 otherwise."""
    from api.analysis import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    r = client.post("/api/analyze/events", json={"symbol": "BTC", "time_range": "2y"})
    assert r.status_code == 400
