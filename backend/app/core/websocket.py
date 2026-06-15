"""WebSocket connection manager for real-time client updates with message batching."""

import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Batching configuration
FLUSH_INTERVAL_SECONDS: float = 0.1  # 100ms
MAX_BUFFER_SIZE: int = 50

# Heartbeat configuration
HEARTBEAT_INTERVAL_SECONDS: float = 30.0
HEARTBEAT_TIMEOUT_SECONDS: float = 90.0  # disconnect if no pong in 90s


class ConnectionManager:
    """Manages active WebSocket connections and channel subscriptions.

    Messages are buffered per channel and flushed either every 100ms or when
    the buffer reaches MAX_BUFFER_SIZE messages, whichever comes first.
    Single-message buffers are sent as plain objects for backward compatibility;
    multi-message buffers are sent as JSON arrays.

    A heartbeat loop sends PING frames every 30 seconds to all connected clients
    and disconnects any client that has not responded with a PONG within 90 seconds.
    """

    _heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS

    def __init__(self) -> None:
        self._connections: dict[WebSocket, set[str]] = {}
        self._buffers: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._flush_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._last_pong: dict[WebSocket, float] = {}

    @property
    def active_count(self) -> int:
        """Return number of active connections."""
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection.

        Starts the background flush loop and heartbeat loop when the first
        connection is established. Records initial pong time so the client
        has a full heartbeat interval before being considered stale.
        """
        await websocket.accept()
        self._connections[websocket] = set()
        self._last_pong[websocket] = time.time()
        logger.info("WebSocket client connected (%d active)", self.active_count)

        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._flush_loop())
            logger.debug("Flush loop started")

        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            logger.debug("Heartbeat loop started")

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection.

        Stops the background flush loop and heartbeat loop when no connections remain.
        """
        self._connections.pop(websocket, None)
        self._last_pong.pop(websocket, None)
        logger.info("WebSocket client disconnected (%d active)", self.active_count)

        if self.active_count == 0:
            if self._flush_task is not None and not self._flush_task.done():
                self._flush_task.cancel()
                self._flush_task = None
                self._buffers.clear()
                logger.debug("Flush loop stopped — no active connections")

            if self._heartbeat_task is not None and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
                self._heartbeat_task = None
                logger.debug("Heartbeat loop stopped — no active connections")

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
        """Buffer a message for broadcast to all clients subscribed to a channel.

        The message is added to the per-channel buffer and will be flushed
        either on the next flush tick or immediately if the buffer reaches
        MAX_BUFFER_SIZE.
        """
        self._buffers[channel].append(data)

        if len(self._buffers[channel]) >= MAX_BUFFER_SIZE:
            await self._flush_channel(channel)

    def handle_pong(self, websocket: WebSocket, data: dict[str, Any]) -> None:
        """Update last pong time for a connection upon receiving a PONG message.

        Should be called from the WebSocket message handler whenever a message
        with ``{"type": "PONG"}`` is received from the client.

        Args:
            websocket: The WebSocket connection that sent the pong.
            data: The raw message payload (used for optional timestamp logging).
        """
        if websocket in self._connections:
            self._last_pong[websocket] = time.time()
            logger.debug(
                "PONG received from client (client_ts=%s)",
                data.get("timestamp"),
            )

    async def _heartbeat_loop(self) -> None:
        """Send PING frames to all connected clients every heartbeat interval.

        If a client fails to acknowledge (PONG) within HEARTBEAT_TIMEOUT_SECONDS
        it is forcibly disconnected. Handles asyncio.CancelledError gracefully.
        """
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)

                now = time.time()
                ping_payload = json.dumps({"type": "PING", "timestamp": now})

                # Snapshot to avoid mutation during iteration
                connections = list(self._connections.keys())
                stale: list[WebSocket] = []

                for ws in connections:
                    # Check for timeout first (no pong within timeout window)
                    last_pong = self._last_pong.get(ws, now)
                    if now - last_pong > HEARTBEAT_TIMEOUT_SECONDS:
                        logger.warning(
                            "WebSocket client timed out (no PONG in %.0fs) — disconnecting",
                            HEARTBEAT_TIMEOUT_SECONDS,
                        )
                        stale.append(ws)
                        continue

                    # Send PING
                    try:
                        await ws.send_text(ping_payload)
                    except Exception:
                        logger.debug("PING send failed — marking client for disconnection", exc_info=True)
                        stale.append(ws)

                for ws in stale:
                    self.disconnect(ws)

        except asyncio.CancelledError:
            logger.debug("Heartbeat loop cancelled")

    async def _flush_channel(self, channel: str) -> None:
        """Send all buffered messages for a channel to subscribed clients.

        If only one message is buffered, it is sent as a plain JSON object
        for backward compatibility. Multiple messages are sent as a JSON array.
        """
        messages = self._buffers.pop(channel, [])
        if not messages:
            return

        # Backward compatibility: single message sent as-is, not wrapped in array
        payload = json.dumps(messages[0]) if len(messages) == 1 else json.dumps(messages)

        disconnected: list[WebSocket] = []
        for ws, channels in self._connections.items():
            if channel in channels:
                try:
                    await ws.send_text(payload)
                except Exception:
                    logger.debug("WS send failed for client", exc_info=True)
                    disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(ws)

    async def _flush_loop(self) -> None:
        """Periodically flush all channel buffers at FLUSH_INTERVAL_SECONDS."""
        try:
            while True:
                await asyncio.sleep(FLUSH_INTERVAL_SECONDS)
                # Snapshot channel names to avoid mutation during iteration
                channels = list(self._buffers.keys())
                for channel in channels:
                    await self._flush_channel(channel)
        except asyncio.CancelledError:
            # Flush remaining messages before shutting down
            channels = list(self._buffers.keys())
            for channel in channels:
                await self._flush_channel(channel)


manager = ConnectionManager()
