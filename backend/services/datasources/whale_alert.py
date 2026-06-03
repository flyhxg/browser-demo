import os
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

WHALE_ALERT_API = "https://api.whale-alert.io/v1"


def _get_api_key() -> str:
    return os.getenv("WHALE_ALERT_API_KEY", "")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_large_transactions(token: str, min_value_usd: float = 1000000.0) -> dict:
    """Fetch large transaction alerts from Whale Alert."""
    api_key = _get_api_key()
    if not api_key:
        return {"error": "WHALE_ALERT_API_KEY not configured"}

    headers = {"Authorization": api_key}
    url = f"{WHALE_ALERT_API}/transactions"
    params = {
        "currency": token.lower(),
        "min_value": int(min_value_usd),
        "limit": 10,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code in (401, 403):
            return {"error": "Invalid API key"}
        if resp.status_code == 404:
            return {"transactions": [], "note": "No transactions found"}
        resp.raise_for_status()
        data = resp.json()
        transactions = data.get("transactions", [])
        return {
            "transactions": [
                {"from": t.get("from"), "to": t.get("to"), "amount": t.get("amount"), "amount_usd": t.get("amount_usd"), "blockchain": t.get("blockchain"), "timestamp": t.get("timestamp")}
                for t in transactions
            ],
            "count": len(transactions),
            "data_source": "whale_alert",
        }
