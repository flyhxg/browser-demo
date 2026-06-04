"""Tests for the Layer 2/3 intent router."""
import pytest

from services.intent_router import IntentRouter, STANDARD_DIMENSIONS


def test_classify_single_symbol_no_message_is_layer2():
    layer = IntentRouter.classify(symbols=["BTC"], dimensions=["derivatives"], message=None)
    assert layer == "layer2"


def test_classify_single_symbol_standard_dims_is_layer2():
    layer = IntentRouter.classify(
        symbols=["ETH"],
        dimensions=["derivatives", "onchain", "technical"],
        message="analyze ETH for shorting",
    )
    assert layer == "layer2"


def test_classify_multiple_symbols_is_layer3():
    layer = IntentRouter.classify(symbols=["BTC", "ETH"], dimensions=["derivatives"], message=None)
    assert layer == "layer3"


def test_classify_nonstandard_dimension_is_layer3():
    layer = IntentRouter.classify(
        symbols=["BTC"],
        dimensions=["derivatives", "macro"],
        message=None,
    )
    assert layer == "layer3"


def test_classify_why_question_is_layer3():
    layer = IntentRouter.classify(
        symbols=["BTC"],
        dimensions=["derivatives", "onchain"],
        message="why did BTC drop today?",
    )
    assert layer == "layer3"


def test_classify_chinese_why_question_is_layer3():
    layer = IntentRouter.classify(
        symbols=["BTC"],
        dimensions=["derivatives", "onchain"],
        message="为什么 BTC 今天突然暴跌？",
    )
    assert layer == "layer3"


def test_classify_sector_question_is_layer3():
    layer = IntentRouter.classify(
        symbols=["RNDR", "TAO", "NEAR"],
        dimensions=["derivatives"],
        message="比较 AI 赛道几个代币的做空性价比",
    )
    assert layer == "layer3"


def test_fallback_plan_uniform_across_symbols():
    plan = IntentRouter._fallback_plan(["BTC", "ETH", "SOL"], ["derivatives", "onchain"])
    assert len(plan) == 3
    assert all(step["dimensions"] == ["derivatives", "onchain"] for step in plan)


def test_fallback_plan_empty_symbols_returns_empty():
    assert IntentRouter._fallback_plan([], None) == []


def test_parse_plan_valid_json():
    import json
    text = json.dumps({
        "rationale": "test",
        "steps": [
            {"symbol": "btc", "dimensions": ["derivatives", "onchain"]},
            {"symbol": "ETH", "dimensions": ["technical"]},
        ],
    })
    parsed = IntentRouter._parse_plan(text, fallback=[])
    assert len(parsed["steps"]) == 2
    assert parsed["steps"][0]["symbol"] == "BTC"
    assert "derivatives" in parsed["steps"][0]["dimensions"]


def test_parse_plan_drops_unknown_dimensions():
    import json
    text = json.dumps({
        "rationale": "x",
        "steps": [{"symbol": "BTC", "dimensions": ["derivatives", "macro", "weather"]}],
    })
    parsed = IntentRouter._parse_plan(text, fallback=[])
    assert parsed["steps"][0]["dimensions"] == ["derivatives"]


def test_parse_plan_invalid_json_returns_fallback():
    parsed = IntentRouter._parse_plan("not json at all", fallback=[{"symbol": "X"}])
    assert parsed["steps"] == [{"symbol": "X"}]


def test_parse_plan_empty_steps_returns_fallback():
    import json
    parsed = IntentRouter._parse_plan(json.dumps({"rationale": "x", "steps": []}), fallback=[{"symbol": "X"}])
    assert parsed["steps"] == [{"symbol": "X"}]


def test_parse_plan_with_code_fence():
    import json
    text = "```json\n" + json.dumps({
        "rationale": "x",
        "steps": [{"symbol": "BTC", "dimensions": ["derivatives"]}],
    }) + "\n```"
    parsed = IntentRouter._parse_plan(text, fallback=[])
    assert parsed["steps"][0]["symbol"] == "BTC"


@pytest.mark.asyncio
async def test_route_layer2_uses_short_selling_engine(monkeypatch):
    """Layer 2 should dispatch to ShortSellingEngine.analyze without LLM planning."""
    from unittest.mock import AsyncMock

    fake_report = {
        "symbol": "BTC",
        "timestamp": "2026-06-04T00:00:00Z",
        "dimensions": {"derivatives": {"price": 50000.0}},
        "llm_analysis": {"summary": "x", "strengths": [], "risks": [],
                         "confidence": 0.5, "recommendation": "neutral",
                         "time_horizon": "medium_term"},
    }
    router = IntentRouter()
    monkeypatch.setattr(router.engine, "analyze", AsyncMock(return_value=fake_report))

    result = await router.route(message=None, symbols=["BTC"], dimensions=["derivatives"])
    assert result["layer"] == "layer2"
    assert result["report"]["symbol"] == "BTC"
    assert router.engine.analyze.await_count == 1


@pytest.mark.asyncio
async def test_route_layer3_executes_plan(monkeypatch):
    """Layer 3 should produce a plan and execute it, returning a synthesis."""
    from unittest.mock import AsyncMock

    fake_reports = [
        {"symbol": "BTC", "llm_analysis": {"recommendation": "weak_short", "confidence": 0.6,
                                           "summary": "x"}},
        {"symbol": "ETH", "llm_analysis": {"recommendation": "neutral", "confidence": 0.4,
                                           "summary": "y"}},
    ]
    router = IntentRouter()
    monkeypatch.setattr(router.engine, "analyze", AsyncMock(side_effect=fake_reports))
    monkeypatch.setattr(router, "_synthesize", AsyncMock(return_value="synthesis text"))

    result = await router.route(
        message="compare BTC and ETH short setup",
        symbols=["BTC", "ETH"],
        dimensions=["derivatives"],
    )
    assert result["layer"] == "layer3"
    assert len(result["tokens"]) == 2
    assert result["llm_synthesis"] == "synthesis text"
    assert router.engine.analyze.await_count == 2
