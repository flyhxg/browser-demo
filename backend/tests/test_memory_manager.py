import pytest
import os
from services.memory_manager import load_token_memory, save_token_memory

@pytest.fixture(autouse=True)
def clean_memory_dir():
    import shutil
    path = "backend/memory/tokens"
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)

def test_save_and_load_token_memory():
    data = {"symbol": "BTC", "user_interests": ["做空分析"], "key_levels": {"support": [30000], "resistance": [40000]}}
    save_token_memory("BTC", data)
    loaded = load_token_memory("BTC")
    assert loaded["symbol"] == "BTC"
    assert loaded["user_interests"] == ["做空分析"]

def test_load_nonexistent_returns_default():
    result = load_token_memory("NONEXISTENT")
    assert result["symbol"] == "NONEXISTENT"
