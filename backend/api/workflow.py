"""Workflow and scheduled task API endpoints.

Exposes the real SignalScanScheduler state (registered in main.py via
`set_scheduler_instance`). Currently a single task is supported:
- id=1, name="Signal Scanner" (Binance Square signal scraper on an interval)
"""
import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from services.config_store import (
    get_trading_config_from_db,
    set_signal_scan_enabled,
    set_signal_scan_interval,
)
from services.scheduler import get_scheduler

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workflow", tags=["workflow"])


def _get_scheduler_or_404():
    scheduler = get_scheduler()
    if scheduler is None:
        raise HTTPException(
            status_code=503,
            detail="Scheduler not initialized — backend may still be starting up",
        )
    return scheduler


@router.get("/tasks")
async def get_tasks() -> dict[str, Any]:
    """Get list of scheduled workflow tasks (currently only Signal Scanner)."""
    scheduler = get_scheduler()
    if scheduler is None:
        return {"tasks": []}
    return {"tasks": [scheduler.get_status()]}


@router.post("/tasks/{task_id}/toggle")
async def toggle_task(task_id: int) -> dict[str, Any]:
    """Toggle a task between running and paused.

    For the single supported task, this calls `start()` if paused or
    `stop()` if running. The underlying config flag is NOT changed —
    use `/enable` or `/disable` to persist the kill switch.
    """
    scheduler = _get_scheduler_or_404()
    if task_id != scheduler.TASK_ID:
        raise HTTPException(status_code=404, detail=f"Unknown task_id {task_id}")
    status = scheduler.get_status()
    if status["running"]:
        await scheduler.stop()
    else:
        await scheduler.start()
    return {"status": "toggled", "task_id": task_id, "task": scheduler.get_status()}


@router.post("/tasks/{task_id}/run")
async def run_task_now(task_id: int) -> dict[str, Any]:
    """Run a single tick of the task immediately (non-blocking)."""
    scheduler = _get_scheduler_or_404()
    if task_id != scheduler.TASK_ID:
        raise HTTPException(status_code=404, detail=f"Unknown task_id {task_id}")
    try:
        scheduler.run_now()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "started", "task_id": task_id, "task": scheduler.get_status()}


@router.post("/tasks/{task_id}/enable")
async def enable_task(task_id: int) -> dict[str, Any]:
    """Persist the kill switch as enabled and start the task."""
    scheduler = _get_scheduler_or_404()
    if task_id != scheduler.TASK_ID:
        raise HTTPException(status_code=404, detail=f"Unknown task_id {task_id}")
    set_signal_scan_enabled(True)
    await scheduler.start()
    return {"status": "enabled", "task_id": task_id, "task": scheduler.get_status()}


@router.post("/tasks/{task_id}/disable")
async def disable_task(task_id: int) -> dict[str, Any]:
    """Stop the task and persist the kill switch as disabled."""
    scheduler = _get_scheduler_or_404()
    if task_id != scheduler.TASK_ID:
        raise HTTPException(status_code=404, detail=f"Unknown task_id {task_id}")
    await scheduler.stop()
    set_signal_scan_enabled(False)
    return {"status": "disabled", "task_id": task_id, "task": scheduler.get_status()}


@router.put("/config")
async def update_workflow_config(data: dict[str, Any]) -> dict[str, Any]:
    """Update workflow configuration (interval only — enabled is via enable/disable)."""
    if "interval_minutes" in data:
        try:
            set_signal_scan_interval(int(data["interval_minutes"]))
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=str(e))
    return {"status": "updated", "config": get_trading_config_from_db()}
