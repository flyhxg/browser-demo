import pytest
from services.datasources.arkham import get_exchange_netflow


@pytest.mark.asyncio
async def test_get_exchange_netflow_returns_dict():
    result = await get_exchange_netflow("ETH")
    assert isinstance(result, dict)
