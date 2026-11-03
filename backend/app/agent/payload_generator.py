"""AI-Driven Positive & Negative Fuzzing — the dynamic payload generator.

Given an OpenAPI JSON Schema fragment for a request body, produces:
  - one realistic, schema-conformant positive payload, and
  - a bounded set of adversarial negative payloads: type mismatches, missing
    required fields, boundary violations, SQL injection, and XSS probes.

This is schema-driven rather than a live LLM call per field — it's
deterministic, offline, and fast enough to run against every property of
every endpoint in a large spec without burning API quota. The `ReasoningAgent`
(see reasoning_agent.py) is the layer that narrates *why* the plan looks the
way it does; this module purely synthesizes the *data*.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from faker import Faker

from app.schemas.test_models import CaseCategory

fake = Faker()

SQL_INJECTION_PAYLOADS = ["' OR 1=1 --", "'; DROP TABLE users; --", "' UNION SELECT NULL,NULL--"]
XSS_PAYLOADS = ["<script>alert(1)</script>", "\"><img src=x onerror=alert(1)>"]
OVERSIZED_STRING = "A" * 10_000


@dataclass
class NegativeCase:
    category: CaseCategory
    description: str
    body: Any


class PayloadGenerator:
    def __init__(self, max_negative_cases: int = 12):
        self.max_negative_cases = max_negative_cases

    # ---- positive -----------------------------------------------------------

    def generate_positive(self, schema: dict[str, Any] | None) -> Any:
        return self._value_for(schema or {})

    def _value_for(self, schema: dict[str, Any]) -> Any:
        if "example" in schema:
            return schema["example"]
        if "anyOf" in schema or "oneOf" in schema:
            # Pydantic v2 renders Optional[X] as anyOf: [X, {"type": "null"}] —
            # generate a real X value rather than falling through to the
            # untyped default (which silently ignores X's own constraints).
            branches = schema.get("anyOf") or schema.get("oneOf") or []
            non_null = [b for b in branches if b.get("type") != "null"]
            return self._value_for(non_null[0] if non_null else (branches[0] if branches else {}))
        if schema.get("enum"):
            return random.choice(schema["enum"])

        schema_type = schema.get("type", "object" if "properties" in schema else "string")

        if schema_type == "object":
            props = schema.get("properties", {})
            return {name: self._value_for(sub_schema) for name, sub_schema in props.items()}
        if schema_type == "array":
            item_schema = schema.get("items", {})
            return [self._value_for(item_schema) for _ in range(2)]
        if schema_type == "integer":
            minimum, maximum = self._numeric_bounds(schema, 1, 1000)
            return fake.random_int(min=int(minimum), max=int(maximum))
        if schema_type == "number":
            minimum, maximum = self._numeric_bounds(schema, 1, 1000)
            return round(random.uniform(float(minimum), float(maximum)), 2)
        if schema_type == "boolean":
            return fake.boolean()
        return self._string_for(schema)

    @staticmethod
    def _numeric_bounds(schema: dict[str, Any], default_min: float, default_max: float) -> tuple[float, float]:
        """Reads minimum/maximum, falling back to exclusiveMinimum/Maximum (+/-1)
        when only the exclusive form is present. JSON Schema allows either
        bound to be a float even when the field's `type` is "integer" — e.g.
        Pydantic v2 emits `{"type": "integer", "minimum": 0.0}` for
        `Field(ge=0)` on an `int` — so callers must still coerce to `int()`
        themselves for the integer case.
        """
        minimum = schema.get("minimum")
        if minimum is None and "exclusiveMinimum" in schema:
            minimum = schema["exclusiveMinimum"] + 1
        maximum = schema.get("maximum")
        if maximum is None and "exclusiveMaximum" in schema:
            maximum = schema["exclusiveMaximum"] - 1
        minimum = default_min if minimum is None else minimum
        maximum = default_max if maximum is None else maximum
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        return minimum, maximum

    def _string_for(self, schema: dict[str, Any]) -> str:
        fmt = schema.get("format")
        name_hint = (schema.get("title") or "").lower()
        by_format = {
            "email": fake.email,
            "date": fake.date,
            "date-time": fake.iso8601,
            "uuid": lambda: str(fake.uuid4()),
            "uri": fake.url,
            "password": lambda: fake.password(length=12),
        }
        if fmt in by_format:
            return by_format[fmt]()
        if "email" in name_hint:
            return fake.email()
        if "name" in name_hint:
            return fake.name()

        min_len = schema.get("minLength", 0)
        text = fake.word()
        if len(text) < min_len:
            text = text.ljust(min_len, "x")
        return text

    # ---- negative -----------------------------------------------------------

    def generate_negative(self, schema: dict[str, Any] | None) -> list[NegativeCase]:
        schema = schema or {}
        base = self.generate_positive(schema)
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        cases: list[NegativeCase] = []
        if isinstance(base, dict) and properties:
            for prop_name, prop_schema in properties.items():
                cases.extend(self._mutations_for_property(base, prop_name, prop_schema, required))
        else:
            cases.append(NegativeCase(CaseCategory.TYPE_MISMATCH, "Send an integer where the body expects an object", 12345))

        cases.append(NegativeCase(CaseCategory.BOUNDARY, "Send a completely empty request body", {}))
        random.shuffle(cases)
        return cases[: self.max_negative_cases]

    def _mutations_for_property(
        self, base: dict[str, Any], prop_name: str, prop_schema: dict[str, Any], required: set[str]
    ) -> list[NegativeCase]:
        mutations: list[NegativeCase] = []
        prop_type = prop_schema.get("type", "string")

        wrong_value = self._wrong_type_value(prop_type)
        mutations.append(self._with_override(
            base, prop_name, wrong_value, CaseCategory.TYPE_MISMATCH,
            f"'{prop_name}' sent as {type(wrong_value).__name__} instead of {prop_type}",
        ))

        if prop_name in required:
            mutated = {k: v for k, v in base.items() if k != prop_name}
            mutations.append(NegativeCase(CaseCategory.MISSING_REQUIRED, f"Required field '{prop_name}' omitted", mutated))

        if prop_type == "string":
            mutations.append(self._with_override(base, prop_name, "", CaseCategory.BOUNDARY, f"'{prop_name}' sent as empty string"))
            mutations.append(self._with_override(base, prop_name, OVERSIZED_STRING, CaseCategory.BOUNDARY, f"'{prop_name}' sent as an oversized 10k-char string"))
        elif prop_type in ("integer", "number"):
            mutations.append(self._with_override(base, prop_name, -1, CaseCategory.BOUNDARY, f"'{prop_name}' sent as a negative number"))
            mutations.append(self._with_override(base, prop_name, 999_999_999, CaseCategory.BOUNDARY, f"'{prop_name}' sent as an out-of-range large number"))

        if prop_type == "string":
            for payload in SQL_INJECTION_PAYLOADS:
                mutations.append(self._with_override(base, prop_name, payload, CaseCategory.SQL_INJECTION, f"SQL injection probe in '{prop_name}'"))
            for payload in XSS_PAYLOADS:
                mutations.append(self._with_override(base, prop_name, payload, CaseCategory.XSS, f"XSS probe in '{prop_name}'"))

        return mutations

    @staticmethod
    def _with_override(base: dict[str, Any], key: str, value: Any, category: CaseCategory, description: str) -> NegativeCase:
        mutated = dict(base)
        mutated[key] = value
        return NegativeCase(category, description, mutated)

    @staticmethod
    def _wrong_type_value(declared_type: str) -> Any:
        return {
            "string": 12345,
            "integer": "not-a-number",
            "number": "not-a-number",
            "boolean": "not-a-boolean",
            "array": "not-an-array",
            "object": "not-an-object",
        }.get(declared_type, 12345)
