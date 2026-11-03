"""Fan-out broadcaster for run events.

A run can have zero or more live WebSocket subscribers (e.g. multiple
browser tabs open on the same run). Events emitted before any subscriber
connects — the very first "Analyzing route mapping..." line, for instance —
are buffered per run_id and replayed to late joiners so nothing is lost.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket

from app.schemas.test_models import RunEvent

_HISTORY_LIMIT = 2000


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._history: dict[str, list[RunEvent]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def connect(self, run_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[run_id].append(websocket)
            backlog = list(self._history[run_id])
        for event in backlog:
            await websocket.send_json(event.model_dump(mode="json"))

    async def disconnect(self, run_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._connections[run_id]:
                self._connections[run_id].remove(websocket)

    async def broadcast(self, run_id: str, event: RunEvent) -> None:
        async with self._lock:
            self._history[run_id].append(event)
            if len(self._history[run_id]) > _HISTORY_LIMIT:
                self._history[run_id] = self._history[run_id][-_HISTORY_LIMIT:]
            sockets = list(self._connections[run_id])

        stale: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_json(event.model_dump(mode="json"))
            except Exception:
                stale.append(socket)

        if stale:
            async with self._lock:
                for socket in stale:
                    if socket in self._connections[run_id]:
                        self._connections[run_id].remove(socket)
