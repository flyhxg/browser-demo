"""Session management for persistent chat conversations."""
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from services.database import get_db

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages chat sessions: creation, message persistence, and cleanup."""

    async def create_session(self) -> dict[str, Any]:
        """Create a new session and return its metadata."""
        session_id = str(uuid.uuid4())
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sessions (id, created_at, last_active_at) VALUES (?, ?, ?)",
            (session_id, datetime.utcnow(), datetime.utcnow()),
        )
        conn.commit()
        conn.close()
        return {"id": session_id, "created_at": datetime.utcnow().isoformat()}

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Retrieve a session by ID, or None if not found."""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, created_at, last_active_at FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"id": row[0], "created_at": row[1], "last_active_at": row[2]}
        return None

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: Optional[list[dict[str, Any]]] = None,
        thinking_steps: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO messages (session_id, role, content, tool_calls, thinking_steps)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                role,
                content,
                json.dumps(tool_calls) if tool_calls else None,
                json.dumps(thinking_steps) if thinking_steps else None,
            ),
        )
        cursor.execute(
            "UPDATE sessions SET last_active_at = ? WHERE id = ?",
            (datetime.utcnow(), session_id),
        )
        conn.commit()
        conn.close()

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content, tool_calls, thinking_steps, created_at FROM messages WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "role": row[0],
                "content": row[1],
                "tool_calls": json.loads(row[2]) if row[2] else None,
                "thinking_steps": json.loads(row[3]) if row[3] else None,
                "created_at": row[4],
            }
            for row in rows
        ]

    async def clear_messages(self, session_id: str) -> int:
        """Delete all messages for a session, keeping the session itself."""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        return deleted

    async def cleanup_expired_sessions(self, days: int = 7) -> int:
        """Delete sessions and messages older than N days."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE session_id IN (SELECT id FROM sessions WHERE last_active_at < ?)", (cutoff,))
        cursor.execute("DELETE FROM sessions WHERE last_active_at < ?", (cutoff,))
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        return deleted
