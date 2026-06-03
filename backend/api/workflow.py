"""Workflow and scheduled task API endpoints."""
from typing import Any

from fastapi import APIRouter

from services.config_store import get_config, update_config
from services.database import get_db

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


@router.get("/tasks")
async def get_tasks() -> dict[str, Any]:
    """Get list of scheduled workflow tasks."""
    # For now, return default trading scanner task
    tasks = [
        {
            "id": 1,
            "name": "Signal Scanner",
            "interval": "5 min",
            "status": "paused",
            "last_run": None,
            "next_run": None,
        },
        {
            "id": 2,
            "name": "Position Monitor",
            "interval": "1 min",
            "status": "paused",
            "last_run": None,
            "next_run": None,
        },
        {
            "id": 3,
            "name": "Auto Trader",
            "interval": "Event-driven",
            "status": "paused",
            "last_run": None,
            "next_run": None,
        },
    ]
    return {"tasks": tasks}


@router.post("/tasks/{task_id}/toggle")
async def toggle_task(task_id: int) -> dict[str, Any]:
    """Toggle a task between running and paused."""
    # In a real implementation, this would toggle the actual task
    return {"status": "toggled", "task_id": task_id}


@router.post("/tasks/{task_id}/run")
async def run_task_now(task_id: int) -> dict[str, Any]:
    """Run a task immediately."""
    # In a real implementation, this would trigger the task
    return {"status": "started", "task_id": task_id}


@router.put("/config")
async def update_workflow_config(data: dict[str, Any]) -> dict[str, Any]:
    """Update workflow configuration."""
    # Merge into main config
    update_config(data)
    return {"status": "updated"}
