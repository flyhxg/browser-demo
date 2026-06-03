import json
from fastapi import APIRouter, HTTPException

from services.config_store import get_masked_config, update_config

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def get_config():
    return get_masked_config()


@router.put("")
async def set_config(data: dict):
    result = update_config(data)
    return result


@router.post("/validate")
async def validate_config():
    from services.llm_factory import create_llm, ProviderNotConfiguredError

    try:
        llm = create_llm()
    except ProviderNotConfiguredError:
        raise HTTPException(status_code=400, detail="Provider not configured")

    try:
        from browser_use.llm.messages import UserMessage
        result = await llm.ainvoke([UserMessage(content="Hi")])
        return {"valid": True}
    except Exception as e:
        return {"valid": False, "error": str(e)}