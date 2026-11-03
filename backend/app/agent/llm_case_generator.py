"""LLM-elaborated negative test cases — the human-like adversarial layer.

The heuristic `PayloadGenerator` (see payload_generator.py) is schema-typed
only: it fires the same fixed SQLi/XSS/boundary mutations at every string or
number field regardless of what that field actually represents, so a
"price" field and a "comment" field get identical treatment. This module
instead asks Gemini to look at the specific endpoint — its resource, its
declared fields, and a masked example payload — and propose the adversarial
cases a human security tester would actually try against *that* field: a
negative quantity on an order endpoint, a role field pushed to "admin", a
currency/unit mixup, a self-referencing id, a locale/unicode edge case.

Runs only when GEMINI_API_KEY is configured (see app/core/config.py) — a
free key with no card required, from https://aistudio.google.com/app/apikey.
Talks to the plain Gemini REST API over `httpx` (already a project
dependency) rather than pulling in a dedicated SDK. Any failure here —
network, timeout, malformed JSON, an unexpected shape — returns None so the
caller (TestRunner) falls back to the deterministic heuristic generator; a
test run must never stall or error out because the LLM call misbehaved.

Everything sent to the model is masked first via DataMasker — only schema
field names/types and an example payload, never live credentials or
response data captured from a real run.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.agent.masking import DataMasker
from app.agent.payload_generator import NegativeCase
from app.schemas.openapi_models import EndpointSpec
from app.schemas.test_models import CaseCategory

_NEGATIVE_CATEGORIES = {
    CaseCategory.TYPE_MISMATCH.value,
    CaseCategory.MISSING_REQUIRED.value,
    CaseCategory.BOUNDARY.value,
    CaseCategory.SQL_INJECTION.value,
    CaseCategory.XSS.value,
    CaseCategory.BOLA.value,
}

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

_SYSTEM_PROMPT = """You are a senior API security tester designing negative/adversarial test cases for one HTTP endpoint.

Given the endpoint's method, resource, JSON schema, and an example valid request body, propose test payloads a skilled human tester would actually try against THIS endpoint. Reason about what each field means rather than only its JSON type — e.g. a negative "quantity", a "role" field escalated to "admin", a mismatched currency/unit, a self-referencing id, an oversized or unicode edge case in a "name" field. Prefer business-logic-aware probes over generic type mismatches whenever a field's name or context suggests something meaningful; fall back to type/boundary mutations for fields with no obvious semantic.

Respond with ONLY a JSON array (no prose, no markdown fences). Each element must be:
{"category": one of "type_mismatch" | "missing_required" | "boundary" | "sql_injection" | "xss" | "bola",
 "description": short human-readable description of the probe,
 "body": the full JSON request body to send, same shape as the example with your mutation applied}

Return at most {max_cases} elements, each targeting a distinct, meaningful weakness — no near-duplicates."""


class LLMCaseGenerator:
    def __init__(self, api_key: str, model: str, max_cases: int = 12):
        self._api_key = api_key
        self._model = model
        self._max_cases = max_cases

    async def generate_negative(self, target: EndpointSpec, positive_body: Any) -> list[NegativeCase] | None:
        if not target.request_body_schema:
            return None
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"{_API_BASE}/{self._model}:generateContent",
                    params={"key": self._api_key},
                    json={
                        "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT.replace("{max_cases}", str(self._max_cases))}]},
                        "contents": [{"role": "user", "parts": [{"text": self._describe_endpoint(target, positive_body)}]}],
                        "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 4096},
                    },
                )
                response.raise_for_status()
                raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                cases = json.loads(raw)
        except Exception:  # noqa: BLE001 — any LLM/network/parse failure falls back to heuristics
            return None

        parsed = self._parse_cases(cases)
        return parsed or None

    @staticmethod
    def _describe_endpoint(target: EndpointSpec, positive_body: Any) -> str:
        payload = {
            "method": target.method.value.upper(),
            "path": target.path,
            "resource": target.resource_name,
            "summary": target.summary,
            "request_body_schema": DataMasker.mask_json(target.request_body_schema or {}),
            "example_valid_body": DataMasker.mask_json(positive_body),
        }
        return json.dumps(payload)

    def _parse_cases(self, cases: Any) -> list[NegativeCase]:
        if not isinstance(cases, list):
            return []
        parsed: list[NegativeCase] = []
        for item in cases[: self._max_cases]:
            if not isinstance(item, dict):
                continue
            category = item.get("category")
            if category not in _NEGATIVE_CATEGORIES or "body" not in item:
                continue
            description = str(item.get("description") or "AI-proposed adversarial probe")
            parsed.append(NegativeCase(CaseCategory(category), f"[AI] {description}", item.get("body")))
        return parsed
