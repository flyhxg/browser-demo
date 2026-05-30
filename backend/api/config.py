import httpx
from fastapi import APIRouter, HTTPException

from services.config_store import (
    get_masked_config,
    update_browser_mode,
    update_provider,
)

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def get_config():
    return get_masked_config()


@router.put("/{provider}")
async def set_provider_config(provider: str, data: dict):
    valid_providers = ["openai", "anthropic", "google", "deepseek", "groq", "ollama"]
    if provider not in valid_providers:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
    result = update_provider(provider, data)
    return result


@router.post("/{provider}/validate")
async def validate_provider(provider: str):
    from services.llm_factory import create_llm, ProviderNotConfiguredError

    try:
        llm = create_llm(provider)
    except ProviderNotConfiguredError:
        raise HTTPException(status_code=400, detail=f"Provider '{provider}' is not configured")

    try:
        if provider == "ollama":
            config = get_masked_config()
            ollama_url = config.get("providers", {}).get("ollama", {}).get("url", "http://localhost:11434")
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{ollama_url}/api/tags", timeout=5)
                resp.raise_for_status()
                models = [m["name"] for m in resp.json().get("models", [])]
                return {"valid": True, "models": models}
        else:
            result = await llm.ainvoke(
                [{"role": "user", "content": "Hi"}],
            )
            return {"valid": True}
    except Exception as e:
        return {"valid": False, "error": str(e)}


@router.put("/browser-mode")
async def set_browser_mode(data: dict):
    mode = data.get("mode", "local")
    cloud_key = data.get("cloud_api_key", "")
    if mode not in ("local", "cloud"):
        raise HTTPException(status_code=400, detail="Mode must be 'local' or 'cloud'")
    result = update_browser_mode(mode, cloud_key)
    return result


@router.get("/ollama/check")
async def check_ollama(url: str = "http://localhost:11434"):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{url}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            return {"connected": True, "models": models}
    except Exception as e:
        return {"connected": False, "error": str(e)}
