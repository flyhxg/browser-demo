import pytest
from services.datasources.whale_alert import get_large_transactions


@pytest.mark.asyncio
async def test_get_large_transactions_returns_dict():
    result = await get_large_transactions("BTC")
    assert isinstance(result, dict)
