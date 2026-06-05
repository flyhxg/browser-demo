import os
import pytest


@pytest.mark.asyncio
async def test_get_exchange_netflow_returns_dict():
    from services.datasources.arkham import get_exchange_netflow
    result = await get_exchange_netflow("ETH")
    assert isinstance(result, dict)


def test_arkham_base_url_is_arkm():
    from services.datasources import arkham
    assert arkham.ARKHAM_API == "https://api.arkm.com"


def test_gini_perfect_equality():
    from services.datasources.arkham import _gini
    assert _gini([100, 100, 100, 100]) == 0.0


def test_gini_perfect_inequality():
    from services.datasources.arkham import _gini
    # One holder owns everything
    assert abs(_gini([0, 0, 0, 1000]) - 0.75) < 0.01


def test_gini_empty():
    from services.datasources.arkham import _gini
    assert _gini([]) == 0.0
    assert _gini([0, 0, 0]) == 0.0


def test_symbol_to_cg_id_known():
    from services.datasources.arkham import SYMBOL_TO_CG_ID
    assert SYMBOL_TO_CG_ID["BTC"] == "bitcoin"
    assert SYMBOL_TO_CG_ID["ETH"] == "ethereum"


def test_get_api_key_prefers_config_store(monkeypatch):
    from services.datasources import arkham
    monkeypatch.setattr(arkham, "_key_from_config", lambda: "from-config")
    monkeypatch.delenv("ARKHAM_API_KEY", raising=False)
    assert arkham._get_api_key() == "from-config"


def test_get_api_key_falls_back_to_env(monkeypatch):
    from services.datasources import arkham
    monkeypatch.setattr(arkham, "_key_from_config", lambda: "")
    monkeypatch.setenv("ARKHAM_API_KEY", "from-env")
    assert arkham._get_api_key() == "from-env"


@pytest.mark.asyncio
async def test_get_exchange_netflow_no_key(monkeypatch):
    from services.datasources import arkham
    monkeypatch.setattr(arkham, "_get_api_key", lambda: "")
    result = await arkham.get_exchange_netflow("BTC")
    assert result == {"error": "ARKHAM_API_KEY not configured"}


@pytest.mark.asyncio
async def test_get_exchange_netflow_happy_path(monkeypatch):
    from services.datasources import arkham

    monkeypatch.setattr(arkham, "_get_api_key", lambda: "fake-key")

    class FakeResp:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "tokens": [{
                    "token": {"id": "bitcoin", "symbol": "btc"},
                    "current": {
                        "inflowCexVolume": 100.0,
                        "outflowCexVolume": 30.0,
                    },
                }],
            }

    async def fake_get(self, url, params=None, **kwargs):
        return FakeResp()

    monkeypatch.setattr(arkham.httpx.AsyncClient, "get", fake_get)
    result = await arkham.get_exchange_netflow("BTC")
    assert result["cex_netflow_24h"] == 70.0  # 100 - 30
    assert result["data_source"] == "arkham"
