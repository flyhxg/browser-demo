import pytest
from services.short_selling_engine import ShortSellingEngine


@pytest.mark.asyncio
async def test_analyze_single_token_returns_report():
    engine = ShortSellingEngine()
    report = await engine.analyze("BTC", dimensions=["derivatives"])
    assert isinstance(report, dict)
    assert "symbol" in report
    assert report["symbol"] == "BTC"


def test_dimension_map_has_8_keys():
    from services.short_selling_engine import ShortSellingEngine
    engine = ShortSellingEngine()
    assert set(engine.dimension_map.keys()) == {
        "derivatives", "onchain", "holder_concentration", "smart_money",
        "exchange_reserves", "unlock", "technical", "sentiment",
    }


@pytest.mark.asyncio
async def test_fetch_onchain_returns_new_cex_netflow_key(monkeypatch):
    from services.short_selling_engine import ShortSellingEngine

    async def fake_netflow(token):
        return {"cex_netflow_24h": 42.0, "cex_inflow_24h": 100.0,
                "cex_outflow_24h": 58.0, "data_source": "arkham"}

    async def fake_whales(token):
        return {"whale_movements": [], "data_source": "arkham"}

    monkeypatch.setattr("services.short_selling_engine.get_exchange_netflow", fake_netflow)
    monkeypatch.setattr("services.short_selling_engine.get_whale_movements", fake_whales)

    engine = ShortSellingEngine()
    result = await engine._fetch_onchain("BTC")
    assert result["cex_netflow_24h"] == 42.0
    assert result["cex_inflow_24h"] == 100.0
    assert result["cex_outflow_24h"] == 58.0
    assert "whale_movements" in result
    assert isinstance(result["whale_movements"], list)
