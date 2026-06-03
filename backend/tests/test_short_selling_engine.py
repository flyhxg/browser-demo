import pytest
from services.short_selling_engine import ShortSellingEngine


@pytest.mark.asyncio
async def test_analyze_single_token_returns_report():
    engine = ShortSellingEngine()
    report = await engine.analyze("BTC", dimensions=["derivatives"])
    assert isinstance(report, dict)
    assert "symbol" in report
    assert report["symbol"] == "BTC"
