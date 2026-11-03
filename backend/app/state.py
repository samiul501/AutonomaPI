"""Process-local state. Fine for a single-instance dev/demo deployment — swap
for Redis (or a DB-backed run table) before scaling to multiple workers,
since WebSocket fan-out and these dicts are currently in-process only.
"""

from __future__ import annotations

from app.executor.test_runner import TestRunner
from app.schemas.openapi_models import ParsedSpec

SPEC_STORE: dict[str, ParsedSpec] = {}
RUN_STORE: dict[str, TestRunner] = {}
