import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.agent_runner import runner, STORAGE_STATE_PATH
from services.interactive import SessionManager

router = APIRouter(prefix="/api/interactive", tags=["interactive"])
session_manager = SessionManager()


class UserInputRequest(BaseModel):
    session_id: str
    input_data: dict


@router.get("/sessions")
async def list_sessions():
    """列出所有保存的会话"""
    sessions = session_manager.list_sessions()
    return {"sessions": sessions}


@router.post("/sessions/{session_name}/save")
async def save_session(session_name: str):
    """将最新自动保存的浏览器状态归档到指定名称的会话文件"""
    session_data = session_manager.get_latest_state()
    if session_data:
        session_manager.save_session(session_name, session_data)
        return {"status": "saved", "session": session_name}
    return {"status": "no_data", "session": session_name}


@router.post("/sessions/{session_name}/load")
async def load_session(session_name: str):
    """加载会话并设置为当前使用的状态文件"""
    session_data = session_manager.load_session(session_name)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")
    target = STORAGE_STATE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(session_data, indent=2))
    return {"session": session_name, "status": "loaded"}


@router.post("/sessions/{session_name}/delete")
async def delete_session(session_name: str):
    """删除会话"""
    success = session_manager.delete_session(session_name)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session": session_name}


@router.post("/input")
async def provide_input(data: UserInputRequest):
    """用户提供交互式输入"""
    runner.provide_input(data.input_data)
    return {"status": "received"}