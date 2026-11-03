"""Data Dependency & Chaining Engine.

Understands endpoint hierarchies well enough to know that testing
`DELETE /api/v1/users/{id}` first requires calling `POST /api/v1/users` to
mint a real id, then wiring the response's id field into the path param.

Resource grouping and creator lookup are heuristic (resource name from the
last static path segment, "id"-like field from the creator's 2xx response
schema) rather than LLM-driven — this keeps chaining deterministic and fast
for the overwhelming majority of REST-shaped APIs, and is cheap to run for
every endpoint in a large spec.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.openapi_models import EndpointSpec, HttpMethod, ParsedSpec

_ID_LIKE_SUFFIXES = ("id", "uuid")


@dataclass
class ChainStep:
    endpoint: EndpointSpec
    extract: dict[str, str] = field(default_factory=dict)  # path_param_name -> response field to pull the value from
    purpose: str = "dependency"  # "dependency" | "target"


class DependencyGraph:
    def __init__(self, parsed_spec: ParsedSpec):
        self.parsed_spec = parsed_spec
        self._by_resource: dict[str, list[EndpointSpec]] = {}
        for endpoint in parsed_spec.endpoints:
            self._by_resource.setdefault(endpoint.resource_name or "root", []).append(endpoint)

    def build_execution_plan(self, target: EndpointSpec) -> list[ChainStep]:
        """Returns the ordered list of calls needed to test `target`: zero or
        more dependency (setup) steps, followed by the target itself.
        """
        if not target.path_params:
            return [ChainStep(endpoint=target, purpose="target")]

        plan: list[ChainStep] = []
        visited: set[str] = set()
        self._resolve_dependencies(target, plan, visited)
        plan.append(ChainStep(endpoint=target, purpose="target"))
        return plan

    def _resolve_dependencies(self, endpoint: EndpointSpec, plan: list[ChainStep], visited: set[str]) -> None:
        resource = endpoint.resource_name or "root"
        if resource in visited:
            return
        visited.add(resource)

        creator = self._find_creator(resource)
        if creator is None:
            return
        if creator.path_params:
            self._resolve_dependencies(creator, plan, visited)

        extract: dict[str, str] = {}
        if endpoint.path_params:
            field_name = self._guess_id_field(creator)
            for param_name in endpoint.path_params:
                extract[param_name] = field_name

        plan.append(ChainStep(endpoint=creator, extract=extract, purpose="dependency"))

    def _find_creator(self, resource: str) -> EndpointSpec | None:
        candidates = self._by_resource.get(resource, [])
        posts = [e for e in candidates if e.method == HttpMethod.POST and not e.path_params]
        if posts:
            return posts[0]
        gets = [e for e in candidates if e.method == HttpMethod.GET]
        return gets[0] if gets else None

    @staticmethod
    def _guess_id_field(creator: EndpointSpec) -> str:
        for status, schema in creator.response_schemas.items():
            if not status.startswith("2"):
                continue
            props = (schema or {}).get("properties", {})
            for prop_name in props:
                lowered = prop_name.lower()
                if lowered in _ID_LIKE_SUFFIXES or lowered.endswith(_ID_LIKE_SUFFIXES):
                    return prop_name
        return "id"
