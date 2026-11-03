"""Real-time streaming channel: the AI Agent Reasoning Log Terminal, the test
matrix, and the summary metric cards on the frontend all subscribe here.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.routes.run import connection_manager

router = APIRouter(tags=["stream"])


@router.websocket("/ws/runs/{run_id}")
async def stream_run(websocket: WebSocket, run_id: str):
    await connection_manager.connect(run_id, websocket)
    try:
        while True:
            # The client doesn't need to send anything — this just keeps the
            # socket open and lets us detect disconnects promptly.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await connection_manager.disconnect(run_id, websocket)
