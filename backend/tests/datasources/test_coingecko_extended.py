import pytest
from services.datasources.coingecko import get_coin_details


@pytest.mark.asyncio
async def test_get_coin_details_returns_dict():
    result = await get_coin_details("bitcoin")
    assert isinstance(result, dict)
    assert "fdv" in result or "error" in result
