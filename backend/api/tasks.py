import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.agent_runner import runner

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)


class StartTaskRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=5000, description="Task description")
    sensitive_data: dict[str, str | dict[str, str]] | None = Field(default=None, description="Sensitive data for login credentials")
    initial_actions: list[dict[str, dict[str, Any]]] | None = Field(default=None, description="Initial actions to perform before the task")
    use_vision: bool = Field(default=True, description="Whether to use vision (screenshots)")
    max_failures: int = Field(default=5, ge=1, le=20, description="Maximum number of failures before stopping")
    max_actions_per_step: int = Field(default=5, ge=1, le=10, description="Maximum number of actions per step")
    step_timeout: int = Field(default=180, ge=30, le=600, description="Timeout for each step in seconds")
    headless: bool = Field(default=True, description="Whether to run browser in headless mode")


class StartTaskResponse(BaseModel):
    status: str


@router.post("", response_model=StartTaskResponse)
async def start_task(data: StartTaskRequest):
    if runner.running:
        raise HTTPException(status_code=409, detail="A task is already running")

    task = data.task.strip()

    if not task:
        raise HTTPException(status_code=400, detail="Task description is required")

    async def _run_with_error_handling():
        try:
            await runner.run(
                task,
                sensitive_data=data.sensitive_data,
                initial_actions=data.initial_actions,
                use_vision=data.use_vision,
                max_failures=data.max_failures,
                max_actions_per_step=data.max_actions_per_step,
                step_timeout=data.step_timeout,
                headless=data.headless,
            )
        except Exception:
            logger.exception("Task execution failed")

    asyncio.create_task(_run_with_error_handling())

    return {"status": "started"}


@router.post("/cancel")
async def cancel_task():
    if not runner.running:
        raise HTTPException(status_code=400, detail="No task is running")
    await runner.cancel()
    return {"status": "cancelled"}


@router.post("/reset")
async def reset_task():
    """Force reset the runner state (use when task is stuck)"""
    await runner.cancel()
    return {"status": "reset"}