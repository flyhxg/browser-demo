import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config.json"

DEFAULT_CONFIG = {
    "providers": {
        "openai": {"api_key": "", "model": "gpt-4o", "configured": False},
        "anthropic": {"api_key": "", "model": "claude-sonnet-4-20250514", "configured": False},
        "google": {"api_key": "", "model": "gemini-2.5-pro", "configured": False},
        "deepseek": {"api_key": "", "model": "deepseek-chat", "configured": False},
        "groq": {"api_key": "", "model": "meta-llama/llama-4-maverick-17b-128e-instruct", "configured": False},
        "ollama": {"url": "http://localhost:11434", "model": "", "configured": False},
    },
    "browser": {"mode": "local", "cloud_api_key": ""},
}


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return DEFAULT_CONFIG.copy()


def _save_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def get_config() -> dict:
    return _load_config()


def mask_key(key: str) -> str:
    if not key or len(key) <= 4:
        return "****" if key else ""
    return f"****{key[-4:]}"


def get_masked_config() -> dict:
    config = _load_config()
    masked = json.loads(json.dumps(config))  # deep copy
    for name, provider in masked.get("providers", {}).items():
        if name == "ollama":
            continue
        key = provider.get("api_key", "")
        provider["api_key_masked"] = mask_key(key)
        provider["configured"] = bool(key)
        del provider["api_key"]
    return masked


def update_provider(provider_name: str, data: dict) -> dict:
    config = _load_config()
    providers = config.setdefault("providers", {})
    if provider_name not in providers:
        providers[provider_name] = {}
    provider = providers[provider_name]

    if provider_name == "ollama":
        if "url" in data:
            provider["url"] = data["url"]
        if "model" in data:
            provider["model"] = data["model"]
        provider["configured"] = bool(provider.get("model"))
    else:
        if "api_key" in data:
            provider["api_key"] = data["api_key"]
        if "model" in data:
            provider["model"] = data["model"]
        provider["configured"] = bool(provider.get("api_key"))

    _save_config(config)

    result = {}
    if provider_name == "ollama":
        result = {"url": provider.get("url", ""), "model": provider.get("model", ""), "configured": provider["configured"]}
    else:
        result = {"api_key_masked": mask_key(provider.get("api_key", "")), "model": provider.get("model", ""), "configured": provider["configured"]}
    return result


def update_browser_mode(mode: str, cloud_api_key: str = "") -> dict:
    config = _load_config()
    config["browser"] = {"mode": mode, "cloud_api_key": cloud_api_key}
    _save_config(config)
    return config["browser"]


def get_provider_config(provider_name: str) -> dict | None:
    config = _load_config()
    return config.get("providers", {}).get(provider_name)
