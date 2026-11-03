"""Start and inspect autonomous test runs.

Starting a run kicks off `TestRunner.run()` as a background asyncio task and
returns immediately with a `run_id` — the frontend then opens
`/ws/runs/{run_id}` (see stream.py) to watch the agent's reasoning log and
results arrive live, and can poll GET /api/runs/{run_id} for a point-in-time
snapshot (e.g. after a page refresh).
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.executor.test_runner import TestRunner
from app.state import RUN_STORE, SPEC_STORE
from app.ws.connection_manager import ConnectionManager

router = APIRouter(prefix="/api/runs", tags=["runs"])

# Shared with stream.py so WebSocket subscribers and the run being executed
# talk through the same broadcaster instance.
connection_manager = ConnectionManager()


class StartRunRequest(BaseModel):
    spec_id: str
    credentials: dict[str, str] = {}


@router.post("")
async def start_run(payload: StartRunRequest):
    parsed_spec = SPEC_STORE.get(payload.spec_id)
    if parsed_spec is None:
        raise HTTPException(status_code=404, detail="Unknown spec_id — ingest the spec first via /api/specs.")

    run_id = str(uuid.uuid4())
    runner = TestRunner(run_id, parsed_spec, payload.credentials, connection_manager)
    RUN_STORE[run_id] = runner
    asyncio.create_task(runner.run())
    return {"run_id": run_id}


@router.get("/{run_id}")
async def get_run(run_id: str):
    runner = RUN_STORE.get(run_id)
    if runner is None:
        raise HTTPException(status_code=404, detail="Unknown run_id.")
    return {
        "run_id": run_id,
        "status": runner.status.value,
        "metrics": runner.metrics.model_dump(),
        "results": [r.model_dump(mode="json") for r in runner.results],
    }
