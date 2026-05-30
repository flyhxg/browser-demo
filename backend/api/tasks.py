from fastapi import APIRouter, HTTPException

from services.agent_runner import runner

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("")
async def start_task(data: dict):
    if runner.running:
        raise HTTPException(status_code=409, detail="A task is already running")

    task = data.get("task", "").strip()
    provider = data.get("provider", "").strip()

    if not task:
        raise HTTPException(status_code=400, detail="Task description is required")
    if not provider:
        raise HTTPException(status_code=400, detail="Provider is required")

    import asyncio
    asyncio.create_task(runner.run(task, provider))

    return {"status": "started"}


@router.post("/cancel")
async def cancel_task():
    if not runner.running:
        raise HTTPException(status_code=400, detail="No task is running")
    await runner.cancel()
    return {"status": "cancelled"}
