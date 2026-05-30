from browser_use import (
    ChatAnthropic,
    ChatGoogle,
    ChatGroq,
    ChatOllama,
    ChatOpenAI,
)

from services.config_store import get_provider_config

PROVIDER_CLASS_MAP = {
    "openai": ChatOpenAI,
    "anthropic": ChatAnthropic,
    "google": ChatGoogle,
    "deepseek": ChatOpenAI,
    "groq": ChatGroq,
    "ollama": ChatOllama,
}


class ProviderNotConfiguredError(Exception):
    pass


def create_llm(provider_name: str) -> ChatOpenAI | ChatAnthropic | ChatGoogle | ChatGroq | ChatOllama:
    config = get_provider_config(provider_name)
    if not config or not config.get("configured"):
        raise ProviderNotConfiguredError(f"Provider '{provider_name}' is not configured")

    cls = PROVIDER_CLASS_MAP.get(provider_name)
    if not cls:
        raise ValueError(f"Unknown provider: {provider_name}")

    if provider_name == "openai":
        return cls(model=config["model"], api_key=config["api_key"])
    elif provider_name == "anthropic":
        return cls(model=config["model"], api_key=config["api_key"])
    elif provider_name == "google":
        return cls(model=config["model"], api_key=config["api_key"])
    elif provider_name == "deepseek":
        return cls(model=config["model"], api_key=config["api_key"], base_url="https://api.deepseek.com/v1")
    elif provider_name == "groq":
        return cls(model=config["model"], api_key=config["api_key"])
    elif provider_name == "ollama":
        return cls(model=config["model"], host=config["url"])
    else:
        raise ValueError(f"Unhandled provider: {provider_name}")
