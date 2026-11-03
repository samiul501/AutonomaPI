"""Turns a raw example JSON value into a JSON-Schema-shaped dict, so a single
sample request body (pasted by hand, no OpenAPI doc involved) can still be
run through the same `PayloadGenerator` that spec-driven endpoints use.

Every field present in the example is treated as required — reasonable for
"here's a real request that works," which is the only kind of example this
is meant to receive.
"""

from __future__ import annotations

from typing import Any


def infer_schema_from_example(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):  # must precede the int check — bool is an int subclass
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        item_schema = infer_schema_from_example(value[0]) if value else {"type": "string"}
        return {"type": "array", "items": item_schema}
    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {key: infer_schema_from_example(val) for key, val in value.items()},
            "required": list(value.keys()),
        }
    return {"type": "string"}
