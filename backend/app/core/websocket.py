"""WebSocket connection manager for real-time client updates."""

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections and channel subscriptions."""

    def __init__(self) -> None:
        self._connections: dict[WebSocket, set[str]] = {}

    @property
    def active_count(self) -> int:
        """Return number of active connections."""
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self._connections[websocket] = set()
        logger.info("WebSocket client connected (%d active)", self.active_count)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        self._connections.pop(websocket, None)
        logger.info("WebSocket client disconnected (%d active)", self.active_count)

    def subscribe(self, websocket: WebSocket, channels: list[str]) -> None:
        """Subscribe a connection to one or more channels."""
        if websocket in self._connections:
            self._connections[websocket].update(channels)

    def unsubscribe(self, websocket: WebSocket, channels: list[str]) -> None:
        """Unsubscribe a connection from one or more channels."""
        if websocket in self._connections:
            self._connections[websocket].difference_update(channels)

    async def send_personal(self, websocket: WebSocket, data: dict[str, Any]) -> None:
        """Send a message to a specific client."""
        await websocket.send_json(data)

    async def broadcast(self, channel: str, data: dict[str, Any]) -> None:
        """Broadcast a message to all clients subscribed to a channel."""
        message = json.dumps(data)
        disconnected: list[WebSocket] = []
        for ws, channels in self._connections.items():
            if channel in channels:
                try:
                    await ws.send_text(message)
                except Exception:
                    logger.debug("WS send failed for client", exc_info=True)
                    disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)


manager = ConnectionManager()
