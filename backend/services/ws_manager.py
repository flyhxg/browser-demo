"""WebSocket connection manager for broadcasting messages."""

from typing import List

from fastapi import WebSocket


class WebSocketManager:
    """Manages active WebSocket connections for broadcasting."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        """Broadcast a message to all active connections."""
        disconnected = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.append(conn)

        # Clean up dead connections
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)


    async def send_analysis_short(self, report: dict) -> None:
        await self.broadcast({"type": "analysis:short", "data": report})

    async def send_signal_new(self, signal: dict) -> None:
        await self.broadcast({"type": "signal:new", "data": signal})

    async def send_signal_analyzed(self, signal: dict) -> None:
        await self.broadcast({"type": "signal:analyzed", "data": signal})

    async def send_trade_executed(self, trade: dict) -> None:
        await self.broadcast({"type": "trade:executed", "data": trade})

    async def send_trade_closed(self, trade: dict) -> None:
        await self.broadcast({"type": "trade:closed", "data": trade})


# Global instance used across the application
manager = WebSocketManager()
