"""Models for the test matrix, results, and the events streamed to the UI."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, computed_field


class CaseCategory(str, Enum):
    POSITIVE = "positive"
    TYPE_MISMATCH = "type_mismatch"
    MISSING_REQUIRED = "missing_required"
    BOUNDARY = "boundary"
    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    AUTH_BYPASS = "auth_bypass"  # stripped/invalid credential
    BOLA = "bola"  # nonexistent/foreign object id probe
    DEPENDENCY = "dependency"  # chaining/setup call — not independently scored


class TestVerdict(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    CRITICAL_LEAK = "critical_leak"
    ERROR = "error"


class TestCase(BaseModel):
    id: str
    endpoint_operation_id: str
    method: str
    path: str
    category: CaseCategory
    description: str
    headers: dict[str, str] = Field(default_factory=dict)
    query_params: dict[str, Any] = Field(default_factory=dict)
    path_params: dict[str, Any] = Field(default_factory=dict)
    body: Any = None


class TestResult(BaseModel):
    case: TestCase
    status_code: Optional[int] = None
    elapsed_ms: Optional[float] = None
    verdict: TestVerdict
    reason: str
    response_snippet: Optional[str] = None  # always pre-masked, see app/agent/masking.py
    executed_at: datetime = Field(default_factory=datetime.utcnow)


class LogLevel(str, Enum):
    INFO = "info"
    THOUGHT = "thought"
    WARNING = "warning"
    SUCCESS = "success"
    ERROR = "error"


class LogEvent(BaseModel):
    run_id: str
    level: LogLevel
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunMetrics(BaseModel):
    total_cases: int = 0
    passed: int = 0
    failed: int = 0
    critical_leaks: int = 0
    errors: int = 0

    @computed_field  # type: ignore[misc]
    @property
    def success_rate(self) -> float:
        if self.total_cases == 0:
            return 0.0
        return round((self.passed / self.total_cases) * 100, 2)


class RunEvent(BaseModel):
    """Envelope broadcast over the run's WebSocket channel."""

    type: str  # "log" | "result" | "metrics" | "status"
    payload: dict[str, Any]
