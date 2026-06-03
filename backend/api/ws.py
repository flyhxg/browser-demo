"""WebSocket endpoint with skill routing."""
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.agent_graph import AgentGraph, AgentState
from services.agent_runner import StepEvent, ResultEvent, ErrorEvent, InteractiveEvent, runner
from services.session import SessionManager
from services.skill_router import skill_router
from services.ws_manager import manager

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)

session_manager = SessionManager()


async def send_live_url(ws: WebSocket, url: str) -> None:
    try:
        await ws.send_json({"type": "live_url", "data": {"url": url}})
    except Exception:
        pass


async def send_queue_status(ws: WebSocket, pending: int) -> None:
    try:
        await ws.send_json({"type": "queue_status", "data": {"pending": pending}})
    except Exception:
        pass


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    await manager.connect(ws)
    runner.set_ws(ws)

    # Create a new session for this connection
    session = await session_manager.create_session()
    session_id = session["id"]

    async def on_step(event: StepEvent):
        try:
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
        except Exception as e:
            logger.warning(f"WebSocket send step failed: {e}")

    async def on_result(event: ResultEvent):
        try:
            await ws.send_json({
                "type": "result",
                "data": {
                    "output": event.output,
                    "steps": event.steps,
                    "duration_ms": event.duration_ms,
                },
            })
        except Exception as e:
            logger.warning(f"WebSocket send result failed: {e}")

    async def on_error(event: ErrorEvent):
        try:
            await ws.send_json({
                "type": "error",
                "data": {
                    "message": event.message,
                    "step": event.step,
                },
            })
        except Exception as e:
            logger.warning(f"WebSocket send error failed: {e}")

    async def on_interactive(event: InteractiveEvent):
        try:
            await ws.send_json({
                "type": "interactive",
                "data": {
                    "type": event.type,
                    "message": event.message,
                    "screenshot": event.screenshot,
                },
            })
        except Exception as e:
            logger.warning(f"WebSocket send interactive failed: {e}")

    async def on_agent_event(event_type: str, data: dict) -> None:
        try:
            from datetime import datetime
            await ws.send_json({"type": event_type, "data": data, "timestamp": datetime.utcnow().isoformat()})
        except Exception:
            pass

    runner.on_step(on_step)
    runner.on_result(on_result)
    runner.on_error(on_error)
    runner.on_interactive(on_interactive)

    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")
            if msg_type == "command":
                command_text = msg.get("command", "")
                if not command_text:
                    continue

                # Persist the user message
                await session_manager.add_message(session_id, "user", command_text)

                # Route via skill router
                route_result = await skill_router.route(command_text, ws)
                intent = route_result.get("type", "general")

                if intent == "browser":
                    # Only browser tasks go to agent runner
                    await runner.enqueue(command_text)
                else:
                    # Direct skill responses (market data, trading, etc.)
                    output = route_result.get("output", "")

                    # Persist the assistant response
                    await session_manager.add_message(session_id, "assistant", output)

                    await ws.send_json({
                        "type": "result",
                        "data": {
                            "output": output,
                            "steps": 0,
                            "duration_ms": 0,
                        },
                    })
            elif msg_type == "ping":
                await ws.send_json({"type": "pong", "data": {}})
    except WebSocketDisconnect:
        logger.debug("WebSocket client disconnected")
    finally:
        manager.disconnect(ws)
        runner.off_step(on_step)
        runner.off_result(on_result)
        runner.off_error(on_error)
        runner.off_interactive(on_interactive)
