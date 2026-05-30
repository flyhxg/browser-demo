import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.agent_runner import StepEvent, ResultEvent, ErrorEvent, runner

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    async def on_step(event: StepEvent):
        await ws.send_json({
            "type": "step",
            "data": {
                "step": event.step,
                "action": event.action,
                "target": event.target,
                "status": event.status,
                "screenshot": event.screenshot,
            },
        })

    async def on_result(event: ResultEvent):
        await ws.send_json({
            "type": "result",
            "data": {
                "output": event.output,
                "steps": event.steps,
                "duration_ms": event.duration_ms,
            },
        })

    async def on_error(event: ErrorEvent):
        await ws.send_json({
            "type": "error",
            "data": {
                "message": event.message,
                "step": event.step,
            },
        })

    runner.on_step(on_step)
    runner.on_result(on_result)
    runner.on_error(on_error)

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
