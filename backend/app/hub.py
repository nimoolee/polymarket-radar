from __future__ import annotations

import asyncio
import json
from collections import deque
from datetime import datetime, timezone

from fastapi import WebSocket
from pydantic import BaseModel

from .config import settings

UTC = timezone.utc

class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self.events: deque[dict] = deque(maxlen=settings.frontend_event_buffer)
        self.connection_status: dict = {"gamma": "unknown", "clob": "unknown"}

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)

    async def broadcast(self, event_type: str, data: BaseModel | dict | list) -> None:
        payload_data = _to_jsonable(data)
        if event_type == "connection_status" and isinstance(payload_data, dict):
            self.connection_status.update(payload_data)
            if "error" not in payload_data and not any(
                value in {"error", "reconnecting"} for value in self.connection_status.values()
            ):
                self.connection_status.pop("error", None)
        payload = {"type": event_type, "data": payload_data, "sent_at": datetime.now(UTC).isoformat()}
        if event_type == "push_event":
            self.events.appendleft(payload_data)
        message = json.dumps(payload)
        async with self._lock:
            clients = list(self._clients)
        for client in clients:
            try:
                await client.send_text(message)
            except RuntimeError:
                await self.disconnect(client)


manager = ConnectionManager()


def _to_jsonable(data):
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")
    if isinstance(data, list):
        return [_to_jsonable(item) for item in data]
    if isinstance(data, dict):
        return {key: _to_jsonable(value) for key, value in data.items()}
    return data
