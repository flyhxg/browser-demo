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
    assert result["cex_inflow_24h"] == 100.0
    assert result["cex_outflow_24h"] == 30.0
    assert result["data_source"] == "arkham"


@pytest.mark.asyncio
async def test_get_exchange_netflow_http_error(monkeypatch):
    """Module contract: never raise. On 5xx, return an error dict, don't propagate."""
    from services.datasources import arkham
    import httpx
    import tenacity

    monkeypatch.setattr(arkham, "_get_api_key", lambda: "fake-key")

    class FakeResp:
        status_code = 500
        def json(self):
            return {}
        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                "500 Server Error", request=None, response=None
            )

    async def fake_get(self, url, params=None, **kwargs):
        return FakeResp()

    monkeypatch.setattr(arkham.httpx.AsyncClient, "get", fake_get)

    # Bypass tenacity backoff for speed: stop after 1 attempt, no wait.
    arkham.get_exchange_netflow.retry.stop = tenacity.stop_after_attempt(1)
    arkham.get_exchange_netflow.retry.wait = tenacity.wait_fixed(0)

    result = await arkham.get_exchange_netflow("BTC")
    assert "error" in result
    assert result.get("data_source") == "arkham"


@pytest.mark.asyncio
async def test_get_whale_movements_no_key(monkeypatch):
    from services.datasources import arkham
    monkeypatch.setattr(arkham, "_get_api_key", lambda: "")
    result = await arkham.get_whale_movements("BTC")
    assert result == {"error": "ARKHAM_API_KEY not configured"}


@pytest.mark.asyncio
async def test_get_whale_movements_happy_path(monkeypatch):
    from services.datasources import arkham

    monkeypatch.setattr(arkham, "_get_api_key", lambda: "fake-key")

    class FakeResp:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "transfers": [
                    {"from": "0xaaa", "to": "0xbbb", "amount": 5.0,
                     "amountUsd": 250000.0, "timestamp": "2026-06-05T00:00:00Z",
                     "blockchain": "ethereum"},
                ],
            }

    async def fake_get(self, url, params=None, **kwargs):
        return FakeResp()

    monkeypatch.setattr(arkham.httpx.AsyncClient, "get", fake_get)
    result = await arkham.get_whale_movements("ETH", min_value_usd=100000.0)
    assert len(result["whale_movements"]) == 1
    assert result["whale_movements"][0]["from"] == "0xaaa"
    assert result["whale_movements"][0]["amount_usd"] == 250000.0
    assert result["count"] == 1
    assert result["data_source"] == "arkham"


@pytest.mark.asyncio
async def test_get_whale_movements_http_error(monkeypatch):
    """Module contract: never raise. On 5xx, return an error dict, don't propagate."""
    from services.datasources import arkham
    import httpx
    import tenacity

    monkeypatch.setattr(arkham, "_get_api_key", lambda: "fake-key")

    class FakeResp:
        status_code = 500
        def json(self):
            return {}
        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                "500 Server Error", request=None, response=None
            )

    async def fake_get(self, url, params=None, **kwargs):
        return FakeResp()

    monkeypatch.setattr(arkham.httpx.AsyncClient, "get", fake_get)

    # Bypass tenacity backoff for speed: stop after 1 attempt, no wait.
    arkham.get_whale_movements.retry.stop = tenacity.stop_after_attempt(1)
    arkham.get_whale_movements.retry.wait = tenacity.wait_fixed(0)

    result = await arkham.get_whale_movements("ETH")
    assert "error" in result
    assert result.get("data_source") == "arkham"
