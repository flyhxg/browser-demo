import pytest

import services.config_store as _store_module
from services.config_store import (
    get_binance_square_scrape_config,
    set_binance_square_scrape_config,
)


@pytest.fixture(autouse=True)
def _reset_overrides():
    """Clear in-process overrides before/after each test so ordering doesn't matter."""
    _store_module._scrape_config_overrides.clear()
    yield
    _store_module._scrape_config_overrides.clear()


def test_defaults_when_no_overrides():
    cfg = get_binance_square_scrape_config()
    assert cfg["url"] == "https://www.binance.com/en/square"
    assert cfg["max_posts_per_scrape"] == 30
    assert cfg["headless"] is True


def test_set_overrides_merge_with_defaults():
    set_binance_square_scrape_config({"max_posts_per_scrape": 10})
    cfg = get_binance_square_scrape_config()
    assert cfg["max_posts_per_scrape"] == 10
    assert cfg["url"] == "https://www.binance.com/en/square"


def test_set_ignores_unknown_keys():
    set_binance_square_scrape_config({"not_a_real_key": "x"})
    cfg = get_binance_square_scrape_config()
    assert "not_a_real_key" not in cfg


def test_set_returns_effective_config():
    """set_* must return the new effective config so callers can chain."""
    result = set_binance_square_scrape_config({"headless": False})
    assert result["headless"] is False
    assert result["url"] == "https://www.binance.com/en/square"
