"""Produces the human-readable 'agent is thinking' narration that streams
into the UI's reasoning log terminal.

Runs on pure heuristics — fast, free, deterministic, and it never has to
leave the process. The actual LLM-backed reasoning (endpoint-specific
adversarial test case generation, gated on GEMINI_API_KEY — see
app/core/config.py) lives in `LLMCaseGenerator` (llm_case_generator.py);
this class only narrates whatever TestRunner decided, heuristic or
LLM-sourced alike. Whatever gets sent to the model must go through
`DataMasker` first — raw request/response bodies or credentials are never
forwarded to an external model.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from app.agent.dependency_graph import ChainStep
from app.agent.masking import DataMasker
from app.schemas.openapi_models import EndpointSpec, ParsedSpec
from app.schemas.test_models import LogLevel

EmitFn = Callable[[LogLevel, str], Awaitable[None]]


class ReasoningAgent:
    def __init__(self, emit: EmitFn):
        self._emit = emit

    async def announce_route_mapping(self, parsed_spec: ParsedSpec) -> None:
        await self._emit(LogLevel.THOUGHT, "Analyzing route mapping...")
        resources = {e.resource_name for e in parsed_spec.endpoints}
        await self._emit(
            LogLevel.INFO,
            f"Parsed '{parsed_spec.title}' v{parsed_spec.version}: "
            f"{len(parsed_spec.endpoints)} endpoints across {len(resources)} resources.",
        )

    async def announce_auth(self, public_count: int, protected_count: int) -> None:
        await self._emit(
            LogLevel.THOUGHT,
            f"Security scan complete — {protected_count} protected endpoint(s), "
            f"{public_count} public endpoint(s) will bypass auth automatically.",
        )

    async def announce_chain(self, target: EndpointSpec, plan: list[ChainStep]) -> None:
        dependencies = [step for step in plan if step.purpose == "dependency"]
        if not dependencies:
            return
        chain_desc = " -> ".join(f"{s.endpoint.method.value.upper()} {s.endpoint.path}" for s in dependencies)
        await self._emit(
            LogLevel.THOUGHT,
            f"Chaining dependency found: {chain_desc} -> {target.method.value.upper()} {target.path}",
        )

    async def announce_generation(self, target: EndpointSpec, positive: int, negative: int) -> None:
        await self._emit(
            LogLevel.INFO,
            f"Generated {positive} positive and {negative} negative case(s) for "
            f"{target.method.value.upper()} {target.path}.",
        )

    async def announce_result(self, method: str, path: str, verdict: str, status_code: int | None) -> None:
        level = LogLevel.ERROR if verdict in ("failed", "critical_leak") else LogLevel.SUCCESS
        safe_path = DataMasker.mask_text(path)
        await self._emit(level, f"{method.upper()} {safe_path} -> {status_code} [{verdict}]")

    async def announce_critical_leak(self, description: str) -> None:
        await self._emit(LogLevel.WARNING, f"CRITICAL: {DataMasker.mask_text(description)}")
