import os
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

ARKHAM_API = "https://api.arkhamintelligence.com/v1"


def _get_api_key() -> str:
    return os.getenv("ARKHAM_API_KEY", "")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_exchange_netflow(token: str) -> dict:
    """Fetch exchange netflow data for a token from Arkham Intelligence."""
    api_key = _get_api_key()
    if not api_key:
        return {"error": "ARKHAM_API_KEY not configured"}

    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"{ARKHAM_API}/exchanges/flows"
    params = {"token": token.upper(), "limit": 1}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code == 404:
            return {"exchange_netflow_24h": 0.0, "note": "No data available for token"}
        resp.raise_for_status()
        data = resp.json()
        return {
            "exchange_netflow_24h": float(data.get("netflow", 0)),
            "data_source": "arkham",
        }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_whale_movements(token: str, min_value_usd: float = 1000000.0) -> dict:
    """Fetch whale movement data from Arkham."""
    api_key = _get_api_key()
    if not api_key:
        return {"error": "ARKHAM_API_KEY not configured"}

    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"{ARKHAM_API}/wallets/transfers"
    params = {"token": token.upper(), "minValueUSD": min_value_usd, "limit": 10}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code == 404:
            return {"whale_movements": [], "note": "No data available"}
        resp.raise_for_status()
        data = resp.json()
        movements = data.get("transfers", [])
        return {
            "whale_movements": [
                {"address": m.get("from", "unknown"), "amount": m.get("value", 0), "direction": "out" if m.get("to_exchange") else "in"}
                for m in movements
            ],
            "data_source": "arkham",
        }
