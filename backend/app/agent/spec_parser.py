"""Loads a Swagger 2.0 / OpenAPI 3.x document (from a URL or raw text) and
flattens it into `EndpointSpec` objects the rest of the agent can reason
about — resolving `$ref` pointers, security schemes, and request/response
schemas along the way.

Structured JSON/YAML specs are the primary, fully-supported input. A
free-form PDF/Markdown doc is a distinct problem (NLP extraction of routes
from prose) and is intentionally left as an extension point rather than
faked here — see `extract_openapi_from_freeform_text` below.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlsplit

import httpx
import yaml

from app.schemas.openapi_models import (
    EndpointSpec,
    HttpMethod,
    ParameterSpec,
    ParsedSpec,
    SecurityScheme,
    SecuritySchemeType,
)

_REF_KEY = "$ref"


class SpecParseError(Exception):
    """Raised when the input document can't be parsed as Swagger/OpenAPI."""


class SpecParser:
    def __init__(self, raw_document: dict[str, Any], source_url: Optional[str] = None):
        self._root = raw_document
        self._ref_cache: dict[str, Any] = {}
        self._source_url = source_url

    # ---- construction -----------------------------------------------------

    @classmethod
    async def from_url(cls, url: str) -> "SpecParser":
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
        return cls(
            cls._load_text(response.text, content_type=response.headers.get("content-type", "")),
            source_url=str(response.url),
        )

    @classmethod
    def from_text(cls, text: str, filename: Optional[str] = None) -> "SpecParser":
        hint = (filename or "").lower()
        content_type = "application/json" if hint.endswith(".json") else ""
        return cls(cls._load_text(text, content_type=content_type))

    @staticmethod
    def _load_text(text: str, content_type: str = "") -> dict[str, Any]:
        text = text.strip()
        if "json" in content_type or text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                raise SpecParseError(f"Could not parse document as JSON: {exc}") from exc
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise SpecParseError(f"Could not parse document as YAML/JSON: {exc}") from exc
        if not isinstance(loaded, dict):
            raise SpecParseError("Document did not resolve to a JSON/YAML object.")
        return loaded

    # ---- $ref resolution ----------------------------------------------------

    def _resolve(self, node: Any, _depth: int = 0) -> Any:
        if _depth > 25:
            return node
        if isinstance(node, dict):
            if _REF_KEY in node and isinstance(node[_REF_KEY], str):
                ref = node[_REF_KEY]
                if ref in self._ref_cache:
                    return self._ref_cache[ref]
                self._ref_cache[ref] = {}  # placeholder breaks reference cycles
                resolved = self._resolve(self._lookup_ref(ref), _depth + 1)
                self._ref_cache[ref] = resolved
                return resolved
            return {k: self._resolve(v, _depth + 1) for k, v in node.items()}
        if isinstance(node, list):
            return [self._resolve(item, _depth + 1) for item in node]
        return node

    def _lookup_ref(self, ref: str) -> Any:
        if not ref.startswith("#/"):
            raise SpecParseError(f"External $ref not supported: {ref}")
        node: Any = self._root
        for part in ref.lstrip("#/").split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, dict) or part not in node:
                raise SpecParseError(f"Broken $ref: {ref}")
            node = node[part]
        return node

    # ---- public API -----------------------------------------------------------

    def parse(self) -> ParsedSpec:
        info = self._root.get("info", {})
        base_url = self._resolve_base_url()

        security_schemes = self._parse_security_schemes()
        global_security = self._security_names(self._root.get("security", []))

        endpoints: list[EndpointSpec] = []
        for path, path_item in (self._root.get("paths") or {}).items():
            path_item = self._resolve(path_item)
            shared_params = path_item.get("parameters", [])
            for method in HttpMethod:
                operation = path_item.get(method.value)
                if not operation:
                    continue
                endpoints.append(
                    self._build_endpoint(
                        path=path,
                        method=method,
                        operation=operation,
                        shared_params=shared_params,
                        global_security=global_security,
                    )
                )

        return ParsedSpec(
            title=info.get("title", "Untitled API"),
            version=str(info.get("version", "1.0.0")),
            base_url=base_url,
            security_schemes=security_schemes,
            endpoints=endpoints,
        )

    # ---- internals --------------------------------------------------------------

    def _resolve_base_url(self) -> Optional[str]:
        """OpenAPI 3.x `servers[0].url` is frequently relative (e.g. `/api/v3`,
        as the public Swagger Petstore demo does) — that's only meaningful
        resolved against the origin the spec was fetched from, not handed to
        an HTTP client verbatim. Swagger 2.0's `host`/`basePath`/`schemes`
        get the equivalent treatment. And a locally-served spec (e.g. a
        FastAPI app's auto-generated /openapi.json) commonly declares no
        `servers` at all — in that case, fall back to the origin the spec
        itself was fetched from, since that's almost always where the API
        actually lives too.
        """
        servers = self._root.get("servers") or []
        if servers:
            base_url = servers[0].get("url")
        else:
            host = self._root.get("host")
            if host:
                base_path = self._root.get("basePath", "")
                scheme = (self._root.get("schemes") or ["https"])[0]
                base_url = f"{scheme}://{host}{base_path}"
            elif self._source_url:
                origin = urlsplit(self._source_url)
                return f"{origin.scheme}://{origin.netloc}"
            else:
                return None

        if base_url and self._source_url and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", base_url):
            base_url = urljoin(self._source_url, base_url)
        return base_url

    def _parse_security_schemes(self) -> dict[str, SecurityScheme]:
        raw_schemes = (
            self._root.get("components", {}).get("securitySchemes")
            or self._root.get("securityDefinitions")  # Swagger 2.0
            or {}
        )
        schemes: dict[str, SecurityScheme] = {}
        for name, raw in raw_schemes.items():
            raw = self._resolve(raw)
            scheme_type = raw.get("type")
            if scheme_type == "http" and raw.get("scheme") == "bearer":
                schemes[name] = SecurityScheme(name=name, type=SecuritySchemeType.HTTP_BEARER, scheme="bearer")
            elif scheme_type in ("http", "basic") and raw.get("scheme", "basic") == "basic":
                schemes[name] = SecurityScheme(name=name, type=SecuritySchemeType.HTTP_BASIC, scheme="basic")
            elif scheme_type == "apiKey":
                schemes[name] = SecurityScheme(
                    name=name,
                    type=SecuritySchemeType.API_KEY,
                    location=raw.get("in", "header"),
                    param_name=raw.get("name", "X-API-Key"),
                )
            elif scheme_type == "oauth2":
                schemes[name] = SecurityScheme(name=name, type=SecuritySchemeType.OAUTH2, flows=raw.get("flows"))
            elif scheme_type == "openIdConnect":
                schemes[name] = SecurityScheme(name=name, type=SecuritySchemeType.OPENID_CONNECT)
        return schemes

    @staticmethod
    def _security_names(security_block: list[dict[str, Any]]) -> list[str]:
        names: list[str] = []
        for requirement in security_block:
            names.extend(requirement.keys())
        return names

    def _build_endpoint(
        self,
        *,
        path: str,
        method: HttpMethod,
        operation: dict[str, Any],
        shared_params: list[dict[str, Any]],
        global_security: list[str],
    ) -> EndpointSpec:
        operation = self._resolve(operation)
        raw_params = [*shared_params, *operation.get("parameters", [])]
        parameters = [
            ParameterSpec(
                name=p["name"],
                location=p.get("in", "query"),
                required=p.get("required", False) or p.get("in") == "path",
                schema=self._resolve(p.get("schema", {})) or {"type": p.get("type", "string")},
                description=p.get("description"),
            )
            for p in raw_params
        ]

        request_body_schema = None
        request_body_required = False
        if "requestBody" in operation:  # OpenAPI 3.x
            body = self._resolve(operation["requestBody"])
            request_body_required = body.get("required", False)
            content = body.get("content", {})
            json_content = content.get("application/json") or next(iter(content.values()), {})
            request_body_schema = json_content.get("schema")
        elif method in (HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH):
            body_params = [p for p in operation.get("parameters", []) if p.get("in") == "body"]  # Swagger 2.0
            if body_params:
                request_body_schema = self._resolve(body_params[0].get("schema", {}))
                request_body_required = body_params[0].get("required", False)

        response_schemas: dict[str, dict[str, Any]] = {}
        for status, resp in (operation.get("responses") or {}).items():
            resp = self._resolve(resp)
            content = resp.get("content", {})
            json_content = content.get("application/json") or {}
            schema = json_content.get("schema") or resp.get("schema")  # Swagger 2.0 fallback
            if schema:
                response_schemas[str(status)] = schema

        security = self._security_names(operation["security"]) if "security" in operation else global_security
        operation_id = operation.get("operationId") or f"{method.value}_{re.sub(r'[{}/]', '_', path).strip('_')}"

        return EndpointSpec(
            operation_id=operation_id,
            path=path,
            method=method,
            tags=operation.get("tags", []),
            summary=operation.get("summary") or operation.get("description"),
            parameters=parameters,
            request_body_schema=request_body_schema,
            request_body_required=request_body_required,
            response_schemas=response_schemas,
            security=security,
            resource_name=self._infer_resource_name(path),
        )

    @staticmethod
    def _infer_resource_name(path: str) -> str:
        segments = [s for s in path.split("/") if s and not s.startswith("{")]
        return segments[-1].lower() if segments else "root"


def extract_openapi_from_freeform_text(document_text: str) -> dict[str, Any]:
    """Extension point: turn a prose PDF/Markdown API doc into an OpenAPI-shaped
    dict via an LLM extraction pass, then feed the result into `SpecParser`.
    Deliberately not implemented with a fake heuristic here — free-text route
    extraction needs an LLM call, and per the local data-masking rule
    (see app/agent/masking.py) only masked, non-sensitive text should ever be
    sent upstream for that extraction.
    """
    raise NotImplementedError(
        "Free-form document ingestion needs an LLM extraction pass; upload a JSON/YAML "
        "OpenAPI/Swagger file or point at a spec URL for now."
    )
