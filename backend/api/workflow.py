"""Workflow and scheduled task API endpoints.

Exposes the registered schedulers from `services.scheduler`. Each
scheduler is dispatched by `task_id` rather than hardcoded to a
singleton. Out of the box two tasks are supported:

- id=1, name="Signal Scanner" (Binance Square signal scraper on an interval)
- id=2, name="Polymarket Poller" (top-200 cluster signal poller)

Per-task actions (`/toggle`, `/run`, `/enable`, `/disable`) look the
scheduler up via the registry and 404 if it isn't registered. The
`/config` endpoint requires a `task_id` so the same UI form can
address both tasks.
"""
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.config_store import (
    get_trading_config_from_db,
    set_polymarket_enabled,
    set_polymarket_interval,
    set_signal_scan_enabled,
    set_signal_scan_interval,
)
from services.scheduler import get_scheduler, get_schedulers

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workflow", tags=["workflow"])


def _resolve(task_id: int):
    """Look up a scheduler by task_id, or raise 404."""
    scheduler = get_scheduler(task_id)
    if scheduler is None:
        raise HTTPException(
            status_code=404, detail=f"No scheduler registered for task_id {task_id}"
        )
    return scheduler


class WorkflowConfigPayload(BaseModel):
    """Body for PUT /api/workflow/config — task_id is required."""

    task_id: int = Field(..., ge=1, description="Scheduler task_id to configure")
    interval_minutes: int = Field(..., ge=0, description="Interval in minutes (≥1 for signal scan; converts to seconds for Polymarket)")


@router.get("/tasks")
async def get_tasks() -> dict[str, Any]:
    """Return a status snapshot of every registered scheduler.

    The frontend treats an empty list as "loading done, nothing to show" —
    we return `{"tasks": []}` rather than 503 when the registry is empty
    (e.g. during the very first milliseconds of app boot, or in tests).
    """
    return {"tasks": [s.get_status() for s in get_schedulers()]}


@router.post("/tasks/{task_id}/toggle")
async def toggle_task(task_id: int) -> dict[str, Any]:
    """Toggle a task between running and paused.

    Does NOT change the persisted kill switch — use `/enable` or
    `/disable` to flip that. The toggle is a runtime-only flip.
    """
    scheduler = _resolve(task_id)
    status = scheduler.get_status()
    if status["running"]:
        await scheduler.stop()
    else:
        await scheduler.start()
    return {"status": "toggled", "task_id": task_id, "task": scheduler.get_status()}


@router.post("/tasks/{task_id}/run")
async def run_task_now(task_id: int) -> dict[str, Any]:
    """Fire a single tick of the task immediately (non-blocking)."""
    scheduler = _resolve(task_id)
    try:
        scheduler.run_now()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "started", "task_id": task_id, "task": scheduler.get_status()}


@router.post("/tasks/{task_id}/enable")
async def enable_task(task_id: int) -> dict[str, Any]:
    """Persist the kill switch ON for the task and start it.

    Routes the persistence write to the right table:
    - task_id=1 → trading_config.signal_scan_enabled
    - task_id=2 → polymarket_config.enabled
    """
    scheduler = _resolve(task_id)
    if task_id == 1:
        set_signal_scan_enabled(True)
    elif task_id == 2:
        set_polymarket_enabled(True)
    else:
        # Defensive — _resolve would have already 404'd for unknown ids.
        raise HTTPException(status_code=404, detail=f"Unknown task_id {task_id}")
    await scheduler.start()
    return {"status": "enabled", "task_id": task_id, "task": scheduler.get_status()}


@router.post("/tasks/{task_id}/disable")
async def disable_task(task_id: int) -> dict[str, Any]:
    """Stop the task and persist the kill switch OFF."""
    scheduler = _resolve(task_id)
    await scheduler.stop()
    if task_id == 1:
        set_signal_scan_enabled(False)
    elif task_id == 2:
        set_polymarket_enabled(False)
    else:
        raise HTTPException(status_code=404, detail=f"Unknown task_id {task_id}")
    return {"status": "disabled", "task_id": task_id, "task": scheduler.get_status()}


@router.put("/config")
async def update_workflow_config(payload: WorkflowConfigPayload) -> dict[str, Any]:
    """Update a task's polling interval.

    The API takes minutes (a unified frontend UX). For task_id=1 the
    minutes value is written directly; for task_id=2 it's converted to
    seconds because `set_polymarket_interval` enforces a 10-second floor.
    The kill switch lives at `/enable` and `/disable` — this endpoint
    only owns the interval knob.
    """
    task_id = payload.task_id
    minutes = int(payload.interval_minutes)
    try:
        if task_id == 1:
            set_signal_scan_interval(minutes)
        elif task_id == 2:
            set_polymarket_interval(minutes * 60)
        else:
            raise HTTPException(status_code=404, detail=f"Unknown task_id {task_id}")
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "updated", "config": get_trading_config_from_db()}
