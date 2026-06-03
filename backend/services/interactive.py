import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SessionManager:
    """管理浏览器会话的持久化"""

    def __init__(self, storage_dir: str = "./sessions"):
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def get_session_path(self, session_name: str) -> Path:
        """获取会话文件路径"""
        return self._storage_dir / f"{session_name}.json"

    def save_session(self, session_name: str, session_data: dict) -> bool:
        """保存浏览器会话状态（cookies/localStorage 等）"""
        try:
            session_path = self.get_session_path(session_name)
            session_path.write_text(json.dumps(session_data, indent=2, ensure_ascii=False))
            logger.info(f"Session saved: {session_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            return False

    def load_session(self, session_name: str) -> dict | None:
        """加载浏览器会话"""
        try:
            session_path = self.get_session_path(session_name)
            if not session_path.exists():
                return None
            return json.loads(session_path.read_text())
        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            return None

    def list_sessions(self) -> list[str]:
        """列出所有会话"""
        try:
            return [f.stem for f in self._storage_dir.glob("*.json")]
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []

    def delete_session(self, session_name: str) -> bool:
        """删除会话"""
        try:
            session_path = self.get_session_path(session_name)
            if session_path.exists():
                session_path.unlink()
                logger.info(f"Session deleted: {session_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete session: {e}")
            return False

    def get_latest_state(self) -> dict | None:
        """从默认存储路径读取最新浏览器状态"""
        from services.agent_runner import STORAGE_STATE_PATH
        if STORAGE_STATE_PATH.exists():
            try:
                return json.loads(STORAGE_STATE_PATH.read_text())
            except Exception as e:
                logger.error(f"Failed to read latest state: {e}")
        return None
