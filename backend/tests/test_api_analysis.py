import pytest
from httpx import AsyncClient, ASGITransport
from main import app

transport = ASGITransport(app=app)

@pytest.mark.asyncio
async def test_analyze_short_endpoint():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/analyze/short", json={"symbol": "BTC", "dimensions": ["derivatives"]})
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTC"

@pytest.mark.asyncio
async def test_analyze_compare_endpoint():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/analyze/compare", json={"symbols": ["BTC", "ETH"], "dimensions": ["derivatives"]})
        assert response.status_code == 200
        data = response.json()
        assert "tokens" in data
