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
