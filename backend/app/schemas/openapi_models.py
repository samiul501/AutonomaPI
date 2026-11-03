"""Normalized, framework-agnostic representation of an OpenAPI/Swagger document.

The agent never re-parses the raw spec after this point — every downstream
module (auth detection, dependency chaining, payload generation, execution)
works off `ParsedSpec` / `EndpointSpec`, whether the source was Swagger 2.0
or OpenAPI 3.x.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class HttpMethod(str, Enum):
    GET = "get"
    POST = "post"
    PUT = "put"
    PATCH = "patch"
    DELETE = "delete"
    OPTIONS = "options"
    HEAD = "head"


class SecuritySchemeType(str, Enum):
    HTTP_BEARER = "http_bearer"
    HTTP_BASIC = "http_basic"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    OPENID_CONNECT = "openid_connect"


class SecurityScheme(BaseModel):
    name: str
    type: SecuritySchemeType
    location: Optional[str] = None  # "header" | "query" | "cookie" — apiKey only
    param_name: Optional[str] = None  # header/query name the credential is injected under
    scheme: Optional[str] = None  # e.g. "bearer" | "basic"
    flows: Optional[dict[str, Any]] = None


class ParameterSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    location: str  # path | query | header | cookie
    required: bool = False
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")
    description: Optional[str] = None


class EndpointSpec(BaseModel):
    operation_id: str
    path: str
    method: HttpMethod
    tags: list[str] = Field(default_factory=list)
    summary: Optional[str] = None
    parameters: list[ParameterSpec] = Field(default_factory=list)
    request_body_schema: Optional[dict[str, Any]] = None
    request_body_required: bool = False
    response_schemas: dict[str, dict[str, Any]] = Field(default_factory=dict)
    security: list[str] = Field(default_factory=list)  # names of required security schemes; empty = public
    resource_name: Optional[str] = None  # heuristic-derived, e.g. "users"

    @property
    def path_params(self) -> list[str]:
        return [p.name for p in self.parameters if p.location == "path"]


class ParsedSpec(BaseModel):
    title: str
    version: str
    base_url: Optional[str] = None
    security_schemes: dict[str, SecurityScheme] = Field(default_factory=dict)
    endpoints: list[EndpointSpec] = Field(default_factory=list)
