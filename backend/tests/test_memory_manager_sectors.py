"""Tests for sector memory and search index in services/memory_manager.py."""
import os
import shutil

import pytest

from services import memory_manager as mm


@pytest.fixture(autouse=True)
def clean_memory_dir():
    """Reset backend/memory/{tokens,sectors,sessions} and search_index.json before each test."""
    for sub in ("tokens", "sectors", "sessions"):
        path = os.path.join(mm.MEMORY_BASE, sub)
        if os.path.exists(path):
            shutil.rmtree(path)
        os.makedirs(path, exist_ok=True)
    if os.path.exists(mm.SEARCH_INDEX_PATH):
        os.remove(mm.SEARCH_INDEX_PATH)
    yield


def test_load_sector_memory_returns_default_for_unknown():
    data = mm.load_sector_memory("ai_tokens")
    assert data["name"] == "ai_tokens"
    assert data["tokens"] == []


def test_save_and_load_sector_memory_roundtrip():
    mm.save_sector_memory("ai_tokens", {
        "name": "ai_tokens",
        "tokens": ["RNDR", "TAO"],
        "notes": "AI算力赛道",
    })
    loaded = mm.load_sector_memory("ai_tokens")
    assert loaded["tokens"] == ["RNDR", "TAO"]
    assert loaded["notes"] == "AI算力赛道"
    assert "updated_at" in loaded


def test_add_token_to_sector_is_idempotent():
    mm.add_token_to_sector("RNDR", "ai_tokens")
    mm.add_token_to_sector("RNDR", "ai_tokens")
    data = mm.load_sector_memory("ai_tokens")
    assert data["tokens"].count("RNDR") == 1


def test_add_token_to_sector_creates_both_sides_of_link():
    mm.add_token_to_sector("RNDR", "ai_tokens")
    token = mm.load_token_memory("RNDR")
    assert "ai_tokens" in token["related_sectors"]


def test_list_sectors_returns_sorted_names():
    mm.save_sector_memory("zksync", {"name": "zksync", "tokens": []})
    mm.save_sector_memory("ai_tokens", {"name": "ai_tokens", "tokens": []})
    mm.save_sector_memory("depin", {"name": "depin", "tokens": []})
    assert mm.list_sectors() == ["ai_tokens", "depin", "zksync"]


def test_search_tokens_finds_indexed_symbol_by_sector():
    mm.add_token_to_sector("RNDR", "ai_tokens")
    mm.add_token_to_sector("TAO", "ai_tokens")
    results = mm.search_tokens("ai")
    symbols = [r["symbol"] for r in results]
    assert "RNDR" in symbols
    assert "TAO" in symbols


def test_search_tokens_empty_query_returns_empty():
    assert mm.search_tokens("") == []
    assert mm.search_tokens("   ") == []


def test_search_tokens_unknown_query_returns_empty():
    mm.add_token_to_sector("RNDR", "ai_tokens")
    assert mm.search_tokens("totally_unrelated_keyword") == []


def test_search_tokens_ranks_higher_score_first():
    mm.add_token_to_sector("RNDR", "ai_tokens")
    mm.add_token_to_sector("BTC", "btc")
    results = mm.search_tokens("ai btc")
    assert results[0]["symbol"] == "RNDR"


def test_update_token_memory_keeps_index_in_sync():
    mm.update_token_memory("SOL", related_sectors=["solana_ecosystem"])
    mm.update_token_memory("SOL", related_sectors=["solana_ecosystem", "l1"])
    results = mm.search_tokens("solana")
    assert results[0]["symbol"] == "SOL"
    assert "l1" in results[0]["sectors"]
