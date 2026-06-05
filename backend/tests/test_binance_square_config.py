from services.config_store import (
    DEFAULT_BINANCE_SQUARE_CONFIG,
    get_binance_square_scrape_config,
    set_binance_square_scrape_config,
)


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
    set_binance_square_scrape_config({"max_posts_per_scrape": 30})


def test_set_ignores_unknown_keys():
    set_binance_square_scrape_config({"not_a_real_key": "x"})
    cfg = get_binance_square_scrape_config()
    assert "not_a_real_key" not in cfg
