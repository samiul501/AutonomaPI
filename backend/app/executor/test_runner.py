"""The agent's hands: takes a parsed spec + credentials, builds a full
dependency-aware test matrix, executes it, and streams every reasoning step
and result to the UI over the run's WebSocket channel in real time.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.agent.auth_detector import AuthDetector
from app.agent.dependency_graph import ChainStep, DependencyGraph
from app.agent.leak_detector import find_leak_signature
from app.agent.llm_case_generator import LLMCaseGenerator
from app.agent.masking import DataMasker
from app.agent.payload_generator import NegativeCase, PayloadGenerator
from app.agent.reasoning_agent import ReasoningAgent
from app.core.config import settings
from app.executor.http_client import AsyncHTTPExecutor
from app.schemas.openapi_models import EndpointSpec, HttpMethod, ParsedSpec
from app.schemas.test_models import (
    CaseCategory,
    LogEvent,
    LogLevel,
    RunEvent,
    RunMetrics,
    RunStatus,
    TestCase,
    TestResult,
    TestVerdict,
)
from app.ws.connection_manager import ConnectionManager

_INVALID_ID_PROBE = "999999999"


class TestRunner:
    def __init__(
        self,
        run_id: str,
        parsed_spec: ParsedSpec,
        credentials: dict[str, str],
        connection_manager: ConnectionManager,
    ):
        self.run_id = run_id
        self.parsed_spec = parsed_spec
        self.credentials = credentials
        self.connections = connection_manager

        self.auth_detector = AuthDetector(parsed_spec)
        self.dependency_graph = DependencyGraph(parsed_spec)
        self.payload_generator = PayloadGenerator(max_negative_cases=settings.max_negative_cases_per_endpoint)
        self.llm_case_generator = self._build_llm_case_generator()
        self.reasoning_agent = ReasoningAgent(self._emit_log)

        self.status = RunStatus.PENDING
        self.metrics = RunMetrics()
        self.results: list[TestResult] = []

        self._auth_headers, self._auth_query = self.auth_detector.build_auth_headers(credentials)

    def _build_llm_case_generator(self) -> LLMCaseGenerator | None:
        if not settings.gemini_api_key:
            return None
        try:
            return LLMCaseGenerator(
                settings.gemini_api_key, settings.gemini_model, max_cases=settings.max_negative_cases_per_endpoint
            )
        except Exception:  # noqa: BLE001 — construction should never be able to fail, but heuristics are the safe fallback either way
            return None

    # ---- streaming helpers --------------------------------------------------

    async def _emit_log(self, level: LogLevel, message: str) -> None:
        event = LogEvent(run_id=self.run_id, level=level, message=message)
        await self.connections.broadcast(self.run_id, RunEvent(type="log", payload=event.model_dump(mode="json")))

    async def _emit_result(self, result: TestResult) -> None:
        self.results.append(result)
        self.metrics.total_cases += 1
        if result.verdict == TestVerdict.PASSED:
            self.metrics.passed += 1
        elif result.verdict == TestVerdict.CRITICAL_LEAK:
            self.metrics.critical_leaks += 1
            self.metrics.failed += 1
        elif result.verdict == TestVerdict.FAILED:
            self.metrics.failed += 1
        else:
            self.metrics.errors += 1

        await self.connections.broadcast(self.run_id, RunEvent(type="result", payload=result.model_dump(mode="json")))
        await self.connections.broadcast(self.run_id, RunEvent(type="metrics", payload=self.metrics.model_dump()))

    async def _emit_status(self, status: RunStatus) -> None:
        self.status = status
        await self.connections.broadcast(self.run_id, RunEvent(type="status", payload={"status": status.value}))

    # ---- orchestration --------------------------------------------------------

    async def run(self) -> None:
        try:
            await self._run()
        except Exception as exc:  # noqa: BLE001 — last-resort net: the UI must never hang on "Running" forever.
            await self._emit_log(LogLevel.ERROR, f"Run aborted by an unexpected error: {exc}")
            await self._emit_status(RunStatus.FAILED)

    async def _run(self) -> None:
        await self._emit_status(RunStatus.RUNNING)
        await self.reasoning_agent.announce_route_mapping(self.parsed_spec)

        public = [e for e in self.parsed_spec.endpoints if self.auth_detector.is_public(e)]
        protected = [e for e in self.parsed_spec.endpoints if not self.auth_detector.is_public(e)]
        await self.reasoning_agent.announce_auth(len(public), len(protected))

        base_url = self.parsed_spec.base_url or "http://localhost"
        executor = AsyncHTTPExecutor(base_url=base_url, timeout=settings.request_timeout_seconds)
        try:
            for endpoint in self.parsed_spec.endpoints:
                try:
                    await self._run_endpoint(endpoint, executor)
                except Exception as exc:  # noqa: BLE001 — one bad endpoint must not abort the whole run.
                    await self._emit_log(
                        LogLevel.ERROR,
                        f"Skipping {endpoint.method.value.upper()} {endpoint.path} after an internal error: {exc}",
                    )
        finally:
            await executor.aclose()

        await self._emit_log(
            LogLevel.SUCCESS,
            f"Run complete — {self.metrics.total_cases} cases executed, {self.metrics.success_rate}% success rate.",
        )
        await self._emit_status(RunStatus.COMPLETED)

    async def _run_endpoint(self, target: EndpointSpec, executor: AsyncHTTPExecutor) -> None:
        plan = self.dependency_graph.build_execution_plan(target)
        await self.reasoning_agent.announce_chain(target, plan)
        dependency_steps = [step for step in plan if step.purpose == "dependency"]

        async def provision_path_values() -> dict[str, Any]:
            values: dict[str, Any] = {}
            for step in dependency_steps:
                await self._execute_dependency_step(step, executor, values)
            return values

        # DELETE consumes the resource the dependency chain created for it —
        # reusing the same id for a later case would silently 404 regardless
        # of whether that case's real behavior (e.g. a missing auth check)
        # would otherwise have succeeded. Every case against a DELETE target
        # gets its own freshly provisioned resource; other methods are safe
        # to share one since GET/PUT don't destroy what they act on.
        needs_fresh_resource = target.method == HttpMethod.DELETE and bool(dependency_steps)

        path_values = await provision_path_values()

        positive_body = self.payload_generator.generate_positive(target.request_body_schema) if target.request_body_schema else None
        negative_cases = await self._generate_negative_cases(target, positive_body)
        await self.reasoning_agent.announce_generation(target, positive=1, negative=len(negative_cases))

        is_public = self.auth_detector.is_public(target)

        await self._execute_scored_case(
            target, executor, path_values,
            category=CaseCategory.POSITIVE,
            description="Baseline request with a fully valid, schema-conformant payload",
            body=positive_body,
            strip_auth=False,
        )

        for negative in negative_cases:
            if needs_fresh_resource:
                path_values = await provision_path_values()
            await self._execute_scored_case(
                target, executor, path_values,
                category=negative.category, description=negative.description, body=negative.body, strip_auth=False,
            )

        if not is_public:
            if needs_fresh_resource:
                path_values = await provision_path_values()
            await self._execute_scored_case(
                target, executor, path_values,
                category=CaseCategory.AUTH_BYPASS,
                description="Request replayed with the Authorization/API-key credential stripped",
                body=positive_body,
                strip_auth=True,
            )

        if target.path_params:
            bola_path_values = {**path_values, **{p: _INVALID_ID_PROBE for p in target.path_params}}
            await self._execute_scored_case(
                target, executor, bola_path_values,
                category=CaseCategory.BOLA,
                description="Request replayed against a nonexistent/foreign object id to probe object-level authorization",
                body=positive_body,
                strip_auth=False,
            )

    async def _generate_negative_cases(self, target: EndpointSpec, positive_body: Any) -> list[NegativeCase]:
        if not target.request_body_schema:
            return []
        if self.llm_case_generator:
            llm_cases = await self.llm_case_generator.generate_negative(target, positive_body)
            if llm_cases:
                await self._emit_log(
                    LogLevel.THOUGHT,
                    f"Gemini proposed {len(llm_cases)} endpoint-specific adversarial case(s) for "
                    f"{target.method.value.upper()} {target.path} based on its actual fields.",
                )
                return llm_cases
            await self._emit_log(
                LogLevel.WARNING,
                f"LLM case generation unavailable for {target.method.value.upper()} {target.path} — "
                "falling back to heuristic fuzzing.",
            )
        return self.payload_generator.generate_negative(target.request_body_schema)

    async def _execute_dependency_step(self, step: ChainStep, executor: AsyncHTTPExecutor, path_values: dict[str, Any]) -> None:
        endpoint = step.endpoint
        body = self.payload_generator.generate_positive(endpoint.request_body_schema) if endpoint.request_body_schema else None
        resolved_path = self._fill_path(endpoint.path, path_values)
        headers, query = self._auth_for(endpoint)

        result = await executor.execute(method=endpoint.method.value, path=resolved_path, headers=headers, query_params=query, json_body=body)
        if result.status_code and 200 <= result.status_code < 300 and isinstance(result.body, dict):
            for param_name, field_name in step.extract.items():
                if field_name in result.body:
                    path_values[param_name] = result.body[field_name]
        else:
            await self._emit_log(
                LogLevel.WARNING,
                f"Dependency setup call {endpoint.method.value.upper()} {endpoint.path} returned "
                f"{result.status_code}; downstream chain may fail.",
            )

    async def _execute_scored_case(
        self,
        target: EndpointSpec,
        executor: AsyncHTTPExecutor,
        path_values: dict[str, Any],
        *,
        category: CaseCategory,
        description: str,
        body: Any,
        strip_auth: bool,
    ) -> None:
        case = TestCase(
            id=str(uuid.uuid4()),
            endpoint_operation_id=target.operation_id,
            method=target.method.value,
            path=target.path,
            category=category,
            description=description,
            path_params=dict(path_values),
            body=body,
        )

        headers, query = ({}, {}) if strip_auth else self._auth_for(target)
        resolved_path = self._fill_path(target.path, path_values)
        result = await executor.execute(method=target.method.value, path=resolved_path, headers=headers, query_params=query, json_body=body)

        verdict, reason = self._judge(category, result.status_code)

        # A human tester doesn't stop at the status code: a "successful"
        # response can still leak internals, and a "successful" write can
        # still be a no-op. Both checks can only escalate an already-passing
        # verdict — they never soften a genuine rejection into a pass.
        if verdict == TestVerdict.PASSED:
            leak_signature = find_leak_signature(result.body)
            if leak_signature:
                verdict = TestVerdict.CRITICAL_LEAK
                reason = f"Response body appears to leak internal details ({leak_signature!r})."
            elif category == CaseCategory.POSITIVE and target.path_params and target.method in (
                HttpMethod.PUT, HttpMethod.PATCH, HttpMethod.DELETE,
            ):
                state_issue = await self._verify_state_change(target, executor, path_values, body)
                if state_issue:
                    verdict = TestVerdict.CRITICAL_LEAK
                    reason = state_issue

        await self._emit_result(TestResult(
            case=case,
            status_code=result.status_code,
            elapsed_ms=result.elapsed_ms,
            verdict=verdict,
            reason=reason,
            response_snippet=self._snippet(result.body),
        ))
        await self.reasoning_agent.announce_result(target.method.value, target.path, verdict.value, result.status_code)
        if verdict == TestVerdict.CRITICAL_LEAK:
            await self.reasoning_agent.announce_critical_leak(
                f"{description} — server returned {result.status_code} instead of rejecting the request"
            )

    async def _verify_state_change(
        self,
        target: EndpointSpec,
        executor: AsyncHTTPExecutor,
        path_values: dict[str, Any],
        sent_body: Any,
    ) -> str | None:
        """A human QA tester doesn't trust a 200 on a write — they re-fetch
        the resource to confirm the change actually happened. Re-requests
        the same resolved path with GET; a server that doesn't support GET
        there just yields no verdict either way (never a false positive).
        """
        resolved_path = self._fill_path(target.path, path_values)
        headers, query = self._auth_for(target)
        check = await executor.execute(method="GET", path=resolved_path, headers=headers, query_params=query)

        if target.method == HttpMethod.DELETE:
            if check.status_code is not None and 200 <= check.status_code < 300:
                return "DELETE returned success, but the resource is still reachable via GET afterward — the delete didn't actually take effect."
            return None

        if check.status_code is None or not (200 <= check.status_code < 300):
            return None
        if not isinstance(check.body, dict) or not isinstance(sent_body, dict):
            return None

        mismatched = [key for key, value in sent_body.items() if key in check.body and check.body[key] != value]
        if mismatched:
            return f"Update returned success, but a follow-up GET shows unchanged value(s) for: {', '.join(mismatched)}."
        return None

    # ---- judgement & utilities ------------------------------------------------

    def _judge(self, category: CaseCategory, status_code: int | None) -> tuple[TestVerdict, str]:
        if status_code is None:
            return TestVerdict.ERROR, "Request failed at the transport level (timeout/connection error)."

        if category == CaseCategory.POSITIVE:
            if 200 <= status_code < 300:
                return TestVerdict.PASSED, "Valid payload accepted as expected."
            return TestVerdict.FAILED, f"Valid payload was rejected with {status_code}."

        # Every other category is an attack/malformed-input probe: the API should reject it (4xx).
        if 400 <= status_code < 500:
            return TestVerdict.PASSED, "Malicious/malformed input correctly rejected."
        if 200 <= status_code < 300:
            leak_categories = {CaseCategory.SQL_INJECTION, CaseCategory.AUTH_BYPASS, CaseCategory.BOLA, CaseCategory.XSS}
            if category in leak_categories:
                return TestVerdict.CRITICAL_LEAK, "Attack payload was accepted — potential security vulnerability."
            return TestVerdict.FAILED, "Malformed input was accepted when it should have been rejected."
        return TestVerdict.FAILED, f"Unexpected status code {status_code} for a negative case."

    def _auth_for(self, endpoint: EndpointSpec) -> tuple[dict[str, str], dict[str, Any]]:
        if self.auth_detector.is_public(endpoint):
            return {}, {}
        return dict(self._auth_headers), dict(self._auth_query)

    @staticmethod
    def _fill_path(path: str, path_values: dict[str, Any]) -> str:
        resolved = path
        for name, value in path_values.items():
            resolved = resolved.replace("{" + name + "}", str(value))
        return resolved

    @staticmethod
    def _snippet(body: Any, limit: int = 500) -> str:
        text = DataMasker.mask_text(str(body))
        return text[:limit]
