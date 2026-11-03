"""Local Data Masking & Leak Prevention.

Scrubs secrets and PII entirely on-box before anything is written to a log,
persisted in a report, or handed to an external LLM provider for reasoning
elaboration. No masking decision here ever depends on a network call, so it
holds even if the LLM integration is disabled or misconfigured.

Every place that touches user-supplied credentials or live response bodies —
`TestRunner`, `ReasoningAgent`, the PDF exporter — must route through this
module before that data leaves the process boundary (a log line, a broadcast
event, an outbound LLM prompt).
"""

from __future__ import annotations

import re
from typing import Any

_SENSITIVE_KEYS = {
    "password", "token", "authorization", "auth", "secret", "api_key", "apikey",
    "access_token", "refresh_token", "client_secret", "ssn", "credit_card", "cvv",
}

_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9\-_.]+", re.IGNORECASE),
    re.compile(r"eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]*"),  # JWT
    re.compile(r"sk-[A-Za-z0-9]{16,}"),  # generic API-key-style secrets
    re.compile(r"\b\d{13,16}\b"),  # credit-card-like digit runs
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # emails
]

MASK = "[MASKED]"


class DataMasker:
    @classmethod
    def mask_text(cls, text: str) -> str:
        masked = text
        for pattern in _PATTERNS:
            masked = pattern.sub(MASK, masked)
        return masked

    @classmethod
    def mask_json(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: (MASK if key.lower() in _SENSITIVE_KEYS else cls.mask_json(val))
                for key, val in value.items()
            }
        if isinstance(value, list):
            return [cls.mask_json(item) for item in value]
        if isinstance(value, str):
            return cls.mask_text(value)
        return value

    @classmethod
    def mask_headers(cls, headers: dict[str, str]) -> dict[str, str]:
        return {k: (MASK if k.lower() in ("authorization", "x-api-key", "cookie") else v) for k, v in headers.items()}
