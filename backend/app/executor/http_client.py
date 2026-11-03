"""Thin async wrapper around httpx. Every test case — dependency setup calls
and scored test calls alike — is executed through this single chokepoint.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx


@dataclass
class ExecutionResult:
    status_code: Optional[int]
    elapsed_ms: float
    headers: dict[str, str]
    body: Any
    error: Optional[str] = None


class AsyncHTTPExecutor:
    def __init__(self, base_url: str, timeout: float = 15.0):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def execute(
        self,
        *,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        query_params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> ExecutionResult:
        started = time.perf_counter()
        kwargs: dict[str, Any] = {"headers": headers or {}, "params": query_params or {}}
        if json_body is not None:
            kwargs["json"] = json_body

        try:
            response = await self._client.request(method.upper(), path, **kwargs)
        except httpx.HTTPError as exc:
            return ExecutionResult(
                status_code=None,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                headers={},
                body=None,
                error=str(exc),
            )

        elapsed_ms = (time.perf_counter() - started) * 1000
        try:
            body = response.json()
        except ValueError:
            body = response.text
        return ExecutionResult(status_code=response.status_code, elapsed_ms=elapsed_ms, headers=dict(response.headers), body=body)
