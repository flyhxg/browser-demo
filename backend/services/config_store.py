import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config.json"

DEFAULT_CONFIG = {
    "api_key": "",
    "base_url": "https://api.anthropic.com",
    "model": "claude-sonnet-4-20250514",
    "protocol": "anthropic",
    "browser_mode": "local",
    "browser_use_api_key": "",
    "proxy_url": "",
    "binance_api_key": "",
    "binance_secret_key": "",
    "binance_mode": "futures",
    "trading_enabled": False,
    "max_position_size_usd": 100.0,
    "tp_percentage": 5.0,
    "sl_percentage": 3.0,
    "position_pct": 0.02,
    "max_open_positions": 5,
    "min_confidence": 0.7,
    "scan_interval_minutes": 5,
    "hot_tokens_enabled": False,
    "hot_tokens_scan_interval": 60,
    "hot_tokens_max_results": 50,
    "hot_tokens_auto_execute": False,
    "hot_tokens_auto_threshold": 0.8,
    "chat_use_llm_analysis": False,
}


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return DEFAULT_CONFIG.copy()


def _save_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def get_config() -> dict:
    return _load_config()


def get_trading_config_from_db() -> dict:
    """Read the trading_config row (id=1) from the SQLite DB.

    This is the source of truth for runtime-tunable settings like
    `signal_scan_enabled` and `signal_scan_interval_minutes` — values
    that the operator flips via `PUT /api/trading/config`. Returns an
    empty dict if the row is missing.

    Use this (not `get_config()`) when you need settings the API
    endpoint can actually mutate.
    """
    from services.database import get_db
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trading_config WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {}
    return dict(row)


def mask_key(key: str) -> str:
    if not key or len(key) <= 4:
        return "****" if key else ""
    return f"****{key[-4:]}"


def get_masked_config() -> dict:
    config = _load_config()
    return {
        "api_key_masked": mask_key(config.get("api_key", "")),
        "base_url": config.get("base_url", "https://api.anthropic.com"),
        "model": config.get("model", "claude-sonnet-4-20250514"),
        "protocol": config.get("protocol", "anthropic"),
        "configured": bool(config.get("api_key")),
        "browser_mode": config.get("browser_mode", "local"),
        "browser_use_api_key_masked": mask_key(config.get("browser_use_api_key", "")),
        "binance_api_key_masked": mask_key(config.get("binance_api_key", "")),
        "binance_mode": config.get("binance_mode", "futures"),
        "trading_enabled": config.get("trading_enabled", False),
        "max_position_size_usd": config.get("max_position_size_usd", 100.0),
        "tp_percentage": config.get("tp_percentage", 5.0),
        "sl_percentage": config.get("sl_percentage", 3.0),
        "position_pct": config.get("position_pct", 0.02),
        "max_open_positions": config.get("max_open_positions", 5),
        "min_confidence": config.get("min_confidence", 0.7),
        "scan_interval_minutes": config.get("scan_interval_minutes", 5),
        "hot_tokens_enabled": config.get("hot_tokens_enabled", False),
        "hot_tokens_scan_interval": config.get("hot_tokens_scan_interval", 60),
        "hot_tokens_max_results": config.get("hot_tokens_max_results", 50),
        "hot_tokens_auto_execute": config.get("hot_tokens_auto_execute", False),
        "hot_tokens_auto_threshold": config.get("hot_tokens_auto_threshold", 0.8),
    }


def update_config(data: dict) -> dict:
    config = _load_config()
    for key in data:
        if key in config or key.startswith(("api_key", "base_url", "model", "protocol", "browser_mode",
                                            "browser_use_api_key", "binance_", "trading_enabled",
                                            "max_position_size", "tp_percentage", "sl_percentage",
                                            "position_pct", "max_open_positions",
                                            "min_confidence", "scan_interval", "hot_tokens_")):
            config[key] = data[key]
    _save_config(config)
    return get_masked_config()


def get_provider_config() -> dict | None:
    return _load_config()


def get_trading_config() -> dict:
    config = _load_config()
    return {
        "binance_api_key": config.get("binance_api_key", ""),
        "binance_secret_key": config.get("binance_secret_key", ""),
        "binance_mode": config.get("binance_mode", "futures"),
        "trading_enabled": config.get("trading_enabled", False),
        "max_position_size_usd": config.get("max_position_size_usd", 100.0),
        "tp_percentage": config.get("tp_percentage", 5.0),
        "sl_percentage": config.get("sl_percentage", 3.0),
        "position_pct": config.get("position_pct", 0.02),
        "max_open_positions": config.get("max_open_positions", 5),
        "min_confidence": config.get("min_confidence", 0.7),
        "scan_interval_minutes": config.get("scan_interval_minutes", 5),
        "hot_tokens_enabled": config.get("hot_tokens_enabled", False),
        "hot_tokens_scan_interval": config.get("hot_tokens_scan_interval", 60),
        "hot_tokens_max_results": config.get("hot_tokens_max_results", 50),
        "hot_tokens_auto_execute": config.get("hot_tokens_auto_execute", False),
        "hot_tokens_auto_threshold": config.get("hot_tokens_auto_threshold", 0.8),
    }