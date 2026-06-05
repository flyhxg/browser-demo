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


@pytest.mark.asyncio
async def test_get_whale_movements_min_value_usd_propagates(monkeypatch):
    """Custom min_value_usd should reach the usdGte query param."""
    from services.datasources import arkham

    monkeypatch.setattr(arkham, "_get_api_key", lambda: "fake-key")
    captured = {}

    class FakeResp:
        status_code = 200
        def json(self): return {"transfers": []}
        def raise_for_status(self): return None

    async def fake_get(self, url, params=None, **kwargs):
        captured["params"] = params
        return FakeResp()

    monkeypatch.setattr(arkham.httpx.AsyncClient, "get", fake_get)
    await arkham.get_whale_movements("BTC", min_value_usd=500_000.0)
    assert captured["params"]["usdGte"] == 500_000.0
    assert captured["params"]["limit"] == 10
    assert captured["params"]["timeLast"] == "24h"


@pytest.mark.asyncio
async def test_get_whale_movements_primary_field_names(monkeypatch):
    """Exercise the primary Arkham field names (camelCase), not the fallback aliases."""
    from services.datasources import arkham

    monkeypatch.setattr(arkham, "_get_api_key", lambda: "fake-key")

    class FakeResp:
        status_code = 200
        def json(self):
            return {
                "transfersArray": [
                    {
                        "fromAddress": "0xccc",
                        "toAddress": "0xddd",
                        "tokenAmount": 10.5,
                        "usdValue": 750_000.0,
                        "chain": "polygon",
                        "blockTimestamp": "2026-06-05T01:00:00Z",
                    },
                ],
            }
        def raise_for_status(self): return None

    async def fake_get(self, url, params=None, **kwargs):
        return FakeResp()

    monkeypatch.setattr(arkham.httpx.AsyncClient, "get", fake_get)
    result = await arkham.get_whale_movements("ETH")
    assert len(result["whale_movements"]) == 1
    m = result["whale_movements"][0]
    assert m["from"] == "0xccc"
    assert m["to"] == "0xddd"
    assert m["amount"] == 10.5
    assert m["amount_usd"] == 750_000.0
    assert m["blockchain"] == "polygon"
    assert m["timestamp"] == "2026-06-05T01:00:00Z"


@pytest.mark.asyncio
async def test_get_holder_concentration_no_key(monkeypatch):
    from services.datasources import arkham
    monkeypatch.setattr(arkham, "_get_api_key", lambda: "")
    result = await arkham.get_holder_concentration("ETH")
    assert result == {"error": "ARKHAM_API_KEY not configured"}


@pytest.mark.asyncio
async def test_get_holder_concentration_happy_path(monkeypatch):
    from services.datasources import arkham

    monkeypatch.setattr(arkham, "_get_api_key", lambda: "fake-key")

    class FakeResp:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "token": {"symbol": "eth"},
                "holders": {
                    "ethereum": [
                        {"address": "0xa", "balance": 1000, "percentage": 40.0},
                        {"address": "0xb", "balance": 500, "percentage": 20.0},
                        {"address": "0xc", "balance": 100, "percentage": 5.0},
                    ],
                    "arbitrum": [
                        {"address": "0xd", "balance": 200, "percentage": 10.0},
                    ],
                },
            }

    async def fake_get(self, url, params=None, **kwargs):
        return FakeResp()

    monkeypatch.setattr(arkham.httpx.AsyncClient, "get", fake_get)
    result = await arkham.get_holder_concentration("ETH", top_n=10)
    assert result["holder_count"] == 4
    # 40 + 20 + 5 + 10 = 75; top_n=10 covers all 4 holders, so top_10 == top_n
    assert abs(result["top_10_pct"] - 75.0) < 0.01
    assert result["top_n_pct"] == 75.0
    assert 0.0 < result["gini"] <= 1.0
    assert result["data_source"] == "arkham"


@pytest.mark.asyncio
async def test_get_holder_concentration_http_error(monkeypatch):
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
    arkham.get_holder_concentration.retry.stop = tenacity.stop_after_attempt(1)
    arkham.get_holder_concentration.retry.wait = tenacity.wait_fixed(0)

    result = await arkham.get_holder_concentration("ETH")
    assert "error" in result
    assert result.get("data_source") == "arkham"


@pytest.mark.asyncio
async def test_get_holder_concentration_gini_equal_balances(monkeypatch):
    """Equal balances → Gini ≈ 0 (verified by _gini unit test); confirm integration passes balances correctly."""
    from services.datasources import arkham

    monkeypatch.setattr(arkham, "_get_api_key", lambda: "fake-key")

    class FakeResp:
        status_code = 200
        def json(self):
            # Four holders with identical balances → Gini should be 0
            return {
                "holders": {
                    "ethereum": [
                        {"address": "0x1", "balance": 100, "percentage": 25.0},
                        {"address": "0x2", "balance": 100, "percentage": 25.0},
                        {"address": "0x3", "balance": 100, "percentage": 25.0},
                        {"address": "0x4", "balance": 100, "percentage": 25.0},
                    ],
                },
            }
        def raise_for_status(self): return None

    async def fake_get(self, url, params=None, **kwargs):
        return FakeResp()

    monkeypatch.setattr(arkham.httpx.AsyncClient, "get", fake_get)
    result = await arkham.get_holder_concentration("ETH")
    assert result["gini"] == 0.0
    assert result["holder_count"] == 4
    assert result["top_10_pct"] == 100.0  # all 4 holders fit in the slice


@pytest.mark.asyncio
async def test_get_holder_concentration_null_holders(monkeypatch):
    """Tolerate Arkham returning null for a chain or for holders dict (no crash)."""
    from services.datasources import arkham

    monkeypatch.setattr(arkham, "_get_api_key", lambda: "fake-key")

    class FakeResp:
        status_code = 200
        def json(self):
            return {"holders": {"ethereum": None, "arbitrum": []}}
        def raise_for_status(self): return None

    async def fake_get(self, url, params=None, **kwargs):
        return FakeResp()

    monkeypatch.setattr(arkham.httpx.AsyncClient, "get", fake_get)
    result = await arkham.get_holder_concentration("ETH")
    assert result["holder_count"] == 0
    assert result["gini"] == 0.0
    assert result["data_source"] == "arkham"
