"""Tests for ShortSellingEngine LLM analysis pipeline.

The `_run_llm_analysis` method is the most error-prone part of the
analyze flow: it depends on the LLM, parses free-form JSON, and
must never raise. These tests cover the parser and fallback path
without requiring a live LLM.
"""
import json

import pytest

from services.short_selling_engine import ShortSellingEngine


FALLBACK = {
    "summary": "fallback",
    "strengths": [],
    "risks": [],
    "confidence": 0.0,
    "recommendation": "neutral",
    "time_horizon": "medium_term",
}


def test_parse_llm_response_valid_json():
    text = json.dumps({
        "summary": "Funding rate is very negative, OI rising.",
        "strengths": ["Negative funding", "High OI"],
        "risks": ["Whale accumulation"],
        "confidence": 0.78,
        "recommendation": "weak_short",
        "time_horizon": "short_term",
    })
    parsed = ShortSellingEngine._parse_llm_response(text, FALLBACK)
    assert parsed["recommendation"] == "weak_short"
    assert parsed["time_horizon"] == "short_term"
    assert parsed["confidence"] == pytest.approx(0.78)
    assert parsed["strengths"] == ["Negative funding", "High OI"]


def test_parse_llm_response_with_code_fence():
    text = "```json\n" + json.dumps({
        "summary": "ok", "strengths": [], "risks": [],
        "confidence": 0.5, "recommendation": "neutral",
        "time_horizon": "medium_term",
    }) + "\n```"
    parsed = ShortSellingEngine._parse_llm_response(text, FALLBACK)
    assert parsed["recommendation"] == "neutral"
    assert parsed["confidence"] == pytest.approx(0.5)


def test_parse_llm_response_invalid_recommendation_clamped_to_neutral():
    text = json.dumps({
        "summary": "x", "strengths": [], "risks": [],
        "confidence": 0.5, "recommendation": "definitely_short",
        "time_horizon": "medium_term",
    })
    parsed = ShortSellingEngine._parse_llm_response(text, FALLBACK)
    assert parsed["recommendation"] == "neutral"


def test_parse_llm_response_confidence_clamped_to_unit_interval():
    text = json.dumps({
        "summary": "x", "strengths": [], "risks": [],
        "confidence": 5.0, "recommendation": "neutral",
        "time_horizon": "medium_term",
    })
    parsed = ShortSellingEngine._parse_llm_response(text, FALLBACK)
    assert parsed["confidence"] == 1.0


def test_parse_llm_response_invalid_json_returns_fallback():
    parsed = ShortSellingEngine._parse_llm_response("not json at all", FALLBACK)
    assert parsed == FALLBACK


def test_parse_llm_response_missing_brace_returns_fallback():
    parsed = ShortSellingEngine._parse_llm_response("analysis: bullish", FALLBACK)
    assert parsed == FALLBACK


def test_compact_dimensions_truncates_long_lists():
    long_list = list(range(100))
    out = ShortSellingEngine._compact_dimensions({
        "onchain": {"whale_movements": long_list, "exchange_netflow_24h": -100}
    })
    assert "<100 entries>" in out["onchain"]["whale_movements"]
    assert out["onchain"]["exchange_netflow_24h"] == -100


def test_compact_dimensions_strips_none_values():
    out = ShortSellingEngine._compact_dimensions({
        "derivatives": {"price": 50000.0, "funding_rate": None, "oi": 0}
    })
    assert "funding_rate" not in out["derivatives"]
    assert out["derivatives"]["price"] == 50000.0


@pytest.mark.asyncio
async def test_run_llm_analysis_returns_fallback_when_no_provider(monkeypatch):
    """When llm_factory raises ProviderNotConfiguredError, must return fallback."""
    from services.llm_factory import ProviderNotConfiguredError

    def _raise():
        raise ProviderNotConfiguredError("no key")

    monkeypatch.setattr("services.short_selling_engine.create_llm", _raise)

    engine = ShortSellingEngine()
    result = await engine._run_llm_analysis("BTC", ["derivatives"], {"derivatives": {}})
    assert result == {
        "summary": "Analysis for BTC across 1 dimensions.",
        "strengths": [],
        "risks": [],
        "confidence": 0.0,
        "recommendation": "neutral",
        "time_horizon": "medium_term",
    }


@pytest.mark.asyncio
async def test_run_llm_analysis_uses_mocked_llm(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(completion=json.dumps({
        "summary": "Mock analysis", "strengths": ["s1"], "risks": ["r1"],
        "confidence": 0.6, "recommendation": "weak_short",
        "time_horizon": "short_term",
    })))
    monkeypatch.setattr("services.short_selling_engine.create_llm", lambda: mock_llm)

    engine = ShortSellingEngine()
    result = await engine._run_llm_analysis(
        "BTC", ["derivatives"], {"derivatives": {"price": 50000.0}}
    )
    assert result["recommendation"] == "weak_short"
    assert result["confidence"] == pytest.approx(0.6)
    assert mock_llm.ainvoke.await_count == 1
