"""Arkham Intelligence API client.

Endpoint contracts: Vyntral/arkham-intelligence-claude-skill
ARKHAM_API_DOCUMENTATION.md (1.0.4).

All functions return dicts and never raise. On missing key, 4xx, 5xx, or
network error, the function returns {"error": "..."}; the calling engine
treats error dims as soft-unavailable.
"""
import os
import asyncio
import logging
from typing import Any
from tenacity import retry, stop_after_attempt, wait_exponential
import httpx

logger = logging.getLogger(__name__)

ARKHAM_API = "https://api.arkm.com"

SYMBOL_TO_CG_ID = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
    "XRP": "ripple", "ADA": "cardano", "DOGE": "dogecoin", "AVAX": "avalanche-2",
    "MATIC": "matic-network", "DOT": "polkadot", "LINK": "chainlink",
    "TON": "the-open-network", "TRX": "tron", "LTC": "litecoin",
    "BCH": "bitcoin-cash", "NEAR": "near", "ATOM": "cosmos", "UNI": "uniswap",
    "APT": "aptos", "ARB": "arbitrum", "OP": "optimism", "INJ": "injective-protocol",
    "SUI": "sui", "SEI": "sei-network", "TIA": "celestia", "WLD": "worldcoin-wld",
    "PEPE": "pepe", "WIF": "dogwifcoin", "BONK": "bonk", "FLOKI": "floki",
    "SHIB": "shiba-inu", "JUP": "jupiter-exchange-solana",
    "USDT": "tether", "USDC": "usd-coin", "DAI": "dai", "FDUSD": "first-digital-usd",
}

# Arkham entity slugs (verified from public docs examples + common exchange/fund labels)
SMART_MONEY_ENTITIES = [
    "jump-trading", "wintermute", "cumberland", "galaxy-digital", "alameda-research",
]
EXCHANGE_ENTITIES = [
    "binance", "coinbase", "kraken", "okx", "bybit", "bitfinex", "htx", "kucoin",
]


def _key_from_config() -> str:
    """Read the configured API key. Returns "" if unset or config unavailable."""
    try:
        from services.config_store import get_config
        return get_config().get("arkham_api_key", "") or ""
    except Exception:
        return ""


def _get_api_key() -> str:
    """Prefer config_store; fall back to ARKHAM_API_KEY env var (CI / docker)."""
    key = _key_from_config()
    if key:
        return key
    return os.getenv("ARKHAM_API_KEY", "")


def _auth_headers() -> dict[str, str]:
    return {"API-Key": _get_api_key()}


def _gini(values: list[float]) -> float:
    """Gini coefficient. 0=perfect equality, 1=one holder owns everything."""
    if not values or sum(values) == 0:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    cum = sum((i + 1) * v for i, v in enumerate(sorted_v))
    return (2 * cum) / (n * sum(sorted_v)) - (n + 1) / n


def _symbol_to_cg_id(symbol: str) -> str:
    """Resolve Binance USDT-margined symbol to CoinGecko pricing ID.

    Falls back to lowercased symbol (best-effort; endpoint will 404 if not found).
    """
    base = symbol.upper().replace("USDT", "").replace("/USDT", "").replace(":USDT", "")
    return SYMBOL_TO_CG_ID.get(base, base.lower())


def _safe_note(message: str) -> dict[str, Any]:
    return {"error": message, "data_source": "arkham"}


async def _get_json(url: str, params: dict | None = None) -> httpx.Response | None:
    """GET with retry; return Response on success, None on persistent failure.

    Caller is responsible for checking .status_code and calling .json().
    """
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _do() -> httpx.Response:
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await client.get(url, headers=_auth_headers(), params=params or {})

    try:
        return await _do()
    except (httpx.HTTPError, asyncio.TimeoutError) as exc:
        logger.warning(f"Arkham request failed: {url} ({exc})")
        return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_exchange_netflow(token: str) -> dict[str, Any]:
    """Per-token CEX netflow over the last 24h.

    Endpoint: GET /token/top?tokenIds={cg_id}&orderByAgg=netflow&timeframe=24h
    Returns: {"cex_netflow_24h": float, "cex_inflow_24h": float,
              "cex_outflow_24h": float, "data_source": "arkham"}
    """
    # No-key branch keeps bare-dict shape: spec test asserts exact dict equality.
    if not _get_api_key():
        return {"error": "ARKHAM_API_KEY not configured"}

    cg_id = _symbol_to_cg_id(token)
    url = f"{ARKHAM_API}/token/top"
    params = {
        "tokenIds": cg_id,
        "orderByAgg": "netflow",
        "timeframe": "24h",
        "from": 0,
        "size": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=_auth_headers(), params=params)
            if resp.status_code == 401:
                return _safe_note("Invalid API key")
            if resp.status_code == 404:
                return _safe_note("Token not found")
            resp.raise_for_status()
            data = resp.json()
            tokens = data.get("tokens", [])
            if not tokens:
                return _safe_note("No data")
            current = tokens[0].get("current", {})
            inflow = float(current.get("inflowCexVolume", 0) or 0)
            outflow = float(current.get("outflowCexVolume", 0) or 0)
            return {
                "cex_netflow_24h": inflow - outflow,
                "cex_inflow_24h": inflow,
                "cex_outflow_24h": outflow,
                "data_source": "arkham",
            }
    except (httpx.HTTPError, asyncio.TimeoutError) as exc:
        # Module contract: never raise. Return shape-consistent error dict.
        return _safe_note(f"network error: {exc}")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_holder_concentration(token: str, top_n: int = 20) -> dict[str, Any]:
    """Holder concentration analysis (top-N % + Gini coefficient).

    Endpoint: GET /token/holders/{cg_id}?groupByEntity=true
    Returns: {"top_10_pct": float, "top_n_pct": float, "gini": float,
              "holder_count": int, "data_source": "arkham"}
    """
    # No-key branch keeps bare-dict shape: spec test asserts exact dict equality.
    if not _get_api_key():
        return {"error": "ARKHAM_API_KEY not configured"}

    cg_id = _symbol_to_cg_id(token)
    url = f"{ARKHAM_API}/token/holders/{cg_id}"
    params = {"groupByEntity": "true"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=_auth_headers(), params=params)
            if resp.status_code == 401:
                return _safe_note("Invalid API key")
            if resp.status_code == 404:
                return _safe_note("Token not found")
            resp.raise_for_status()
            data = resp.json()
            holders_by_chain: dict = data.get("holders") or {}
            all_holders: list[dict] = []
            for chain_holders in holders_by_chain.values():
                all_holders.extend(chain_holders or [])
            all_holders.sort(key=lambda h: h.get("percentage", 0) or 0, reverse=True)
            top = all_holders[:top_n]
            top_10_pct = sum(h.get("percentage", 0) or 0 for h in all_holders[:10])
            balances = [h.get("balance", 0) or 0 for h in all_holders]
            return {
                "top_10_pct": round(top_10_pct, 2),
                "top_n_pct": round(sum(h.get("percentage", 0) or 0 for h in top), 2),
                "gini": round(_gini(balances), 4),
                "holder_count": len(all_holders),
                "data_source": "arkham",
            }
    except (httpx.HTTPError, asyncio.TimeoutError) as exc:
        # Module contract: never raise. Return shape-consistent error dict.
        return _safe_note(f"network error: {exc}")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_whale_movements(token: str, min_value_usd: float = 1_000_000.0) -> dict[str, Any]:
    """Top high-value transfers for a token in the last 24h.

    Endpoint: GET /transfers?tokens={cg_id}&timeLast=24h&usdGte={min}&limit=10
    Returns: {"whale_movements": [...], "count": int, "data_source": "arkham"}
    """
    # No-key branch keeps bare-dict shape: spec test asserts exact dict equality.
    if not _get_api_key():
        return {"error": "ARKHAM_API_KEY not configured"}

    cg_id = _symbol_to_cg_id(token)
    url = f"{ARKHAM_API}/transfers"
    params = {
        "tokens": cg_id,
        "timeLast": "24h",
        "usdGte": min_value_usd,
        "limit": 10,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=_auth_headers(), params=params)
            if resp.status_code == 401:
                return _safe_note("Invalid API key")
            if resp.status_code == 404:
                # 404 = no transfers in window (not an error like a missing token)
                return {"whale_movements": [], "note": "No transfers found"}
            resp.raise_for_status()
            data = resp.json()
            if "transfers" in data:
                transfers = data["transfers"]
            else:
                transfers = data.get("transfersArray", [])
            return {
                "whale_movements": [
                    {
                        "from": t.get("fromAddress", t.get("from")),
                        "to": t.get("toAddress", t.get("to")),
                        "amount": t.get("tokenAmount", t.get("amount")),
                        "amount_usd": t.get("usdValue", t.get("amountUsd")),
                        "blockchain": t.get("chain") or t.get("blockchain"),
                        "timestamp": t.get("blockTimestamp") or t.get("timestamp"),
                    }
                    for t in transfers
                ],
                "count": len(transfers),
                "data_source": "arkham",
            }
    except (httpx.HTTPError, asyncio.TimeoutError) as exc:
        # Module contract: never raise. Return shape-consistent error dict.
        return _safe_note(f"network error: {exc}")


async def get_smart_money_flow(token: str, days: int = 7) -> dict[str, Any]:
    """Sum of USD netflow across known smart-money entities, Ethereum chain.

    Endpoint: GET /flow/entity/{entity} (one call per known entity, in parallel)
    """
    if not _get_api_key():
        return {"error": "ARKHAM_API_KEY not configured"}

    async def fetch_one(entity: str) -> tuple[str, float]:
        try:
            url = f"{ARKHAM_API}/flow/entity/{entity}"
            resp = await _get_json(url, params={"chains": "ethereum"})
            if resp is None or resp.status_code != 200:
                return entity, 0.0
            data = resp.json()
            chain_data = data.get("ethereum", [])
            if not chain_data:
                return entity, 0.0
            latest = chain_data[-1]
            net = float(latest.get("inflow", 0) or 0) - float(latest.get("outflow", 0) or 0)
            return entity, net
        except Exception as exc:
            logger.warning(f"smart-money fetch failed for {entity}: {exc}")
            return entity, 0.0

    results = await asyncio.gather(*(fetch_one(e) for e in SMART_MONEY_ENTITIES))
    by_entity = dict(results)
    total = sum(by_entity.values())
    return {
        "smart_money_netflow": round(total, 2),
        "by_entity": {k: round(v, 2) for k, v in by_entity.items()},
        "entity_count": len(by_entity),
        "data_source": "arkham",
    }


async def get_exchange_reserves(token: str) -> dict[str, Any]:
    """Sum of exchange reserves for a token across known exchange entities.

    Endpoint: GET /balances/entity/{entity} (one call per exchange, in parallel)
    """
    if not _get_api_key():
        return {"error": "ARKHAM_API_KEY not configured"}

    cg_id = _symbol_to_cg_id(token)

    async def fetch_one(entity: str) -> tuple[str, float]:
        try:
            url = f"{ARKHAM_API}/balances/entity/{entity}"
            resp = await _get_json(url, params={"chains": "ethereum"})
            if resp is None or resp.status_code != 200:
                return entity, 0.0
            data = resp.json()
            chain_data = data.get("balances", {}).get("ethereum", []) or []
            total = sum(
                float(b.get("usd", 0) or 0)
                for b in chain_data
                if (b.get("id") or "").lower() == cg_id.lower()
            )
            return entity, total
        except Exception as exc:
            logger.warning(f"exchange balances fetch failed for {entity}: {exc}")
            return entity, 0.0

    results = await asyncio.gather(*(fetch_one(e) for e in EXCHANGE_ENTITIES))
    by_exchange = dict(results)
    total = sum(by_exchange.values())
    return {
        "exchange_reserves_usd": round(total, 2),
        "by_exchange": {k: round(v, 2) for k, v in by_exchange.items()},
        "exchange_count": len(by_exchange),
        "data_source": "arkham",
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_entity_predictions(entity: str) -> dict[str, Any]:
    """ML-predicted addresses for an entity (e.g. 'binance', 'coinbase').

    Endpoint: GET /intelligence/entity_predictions/{entity}
    Returns: {"predictions": [...], "entity": str, "data_source": "arkham"}
    """
    # No-key branch keeps bare-dict shape: spec test asserts exact dict equality.
    if not _get_api_key():
        return {"error": "ARKHAM_API_KEY not configured"}

    url = f"{ARKHAM_API}/intelligence/entity_predictions/{entity}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=_auth_headers())
            if resp.status_code == 401:
                return _safe_note("Invalid API key")
            if resp.status_code == 404:
                return _safe_note("Entity not found or no predictions")
            resp.raise_for_status()
            data = resp.json() or []
            if not isinstance(data, list):
                return _safe_note("unexpected response shape")
            return {
                "predictions": [
                    {
                        "address": p.get("address"),
                        "entity_id": p.get("entityID"),
                        "usd_balance": p.get("usdBalance"),
                    }
                    for p in data
                ],
                "entity": entity,
                "data_source": "arkham",
            }
    except (httpx.HTTPError, asyncio.TimeoutError) as exc:
        # Module contract: never raise. Return shape-consistent error dict.
        return _safe_note(f"network error: {exc}")
