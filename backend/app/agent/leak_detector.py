"""Scans a response body for signs of information disclosure — stack
traces, raw DB errors, internal file paths — regardless of the HTTP status
code. A well-behaved-looking 200 response can still leak internals that a
status-code-only check would never notice; this is the part of testing
where a human reads the actual response instead of just the status line.
"""

from __future__ import annotations

import re
from typing import Any

_LEAK_PATTERNS = [
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"at System\.[A-Za-z.]+"),  # .NET stack frames
    re.compile(r"\bSQLSTATE\[|\bORA-\d{5}\b"),  # raw DB error codes
    re.compile(r"django\.db\.utils"),
    re.compile(r"[A-Za-z]:\\[^\s\"']+\\[^\s\"']+"),  # Windows file paths
    re.compile(r"/(?:home|var|usr)/[^\s\"']+"),  # Unix file paths
    re.compile(r"\bstack ?trace\b", re.IGNORECASE),
]


def find_leak_signature(body: Any) -> str | None:
    text = str(body)
    for pattern in _LEAK_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None
