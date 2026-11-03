"""Smart Authentication Detector.

Turns the security schemes declared in a spec into concrete UI input
requirements (what to render, and what kind of secret it expects), and
classifies each endpoint as public (auto-bypassed) or protected (needs a
credential injected before execution).
"""

from __future__ import annotations

from typing import Any

from app.schemas.openapi_models import EndpointSpec, ParsedSpec, SecuritySchemeType


class AuthDetector:
    def __init__(self, parsed_spec: ParsedSpec):
        self.parsed_spec = parsed_spec

    def required_ui_fields(self) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = []
        for scheme in self.parsed_spec.security_schemes.values():
            if scheme.type == SecuritySchemeType.HTTP_BEARER:
                fields.append({
                    "scheme": scheme.name,
                    "type": "bearer_token",
                    "label": "Bearer Token",
                    "placeholder": "eyJhbGciOi...",
                    "secret": True,
                })
            elif scheme.type == SecuritySchemeType.HTTP_BASIC:
                fields.append({
                    "scheme": scheme.name,
                    "type": "basic_auth",
                    "label": "Basic Auth (base64 user:pass)",
                    "secret": True,
                })
            elif scheme.type == SecuritySchemeType.API_KEY:
                fields.append({
                    "scheme": scheme.name,
                    "type": "api_key",
                    "label": f"API Key ({scheme.param_name})",
                    "placeholder": scheme.param_name,
                    "secret": True,
                    "location": scheme.location,
                    "param_name": scheme.param_name,
                })
            elif scheme.type in (SecuritySchemeType.OAUTH2, SecuritySchemeType.OPENID_CONNECT):
                fields.append({
                    "scheme": scheme.name,
                    "type": "oauth2_token",
                    "label": "OAuth2 Access Token",
                    "placeholder": "Paste a valid access token",
                    "secret": True,
                })
        return fields

    def is_public(self, endpoint: EndpointSpec) -> bool:
        return len(endpoint.security) == 0

    def build_auth_headers(self, credentials: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
        """credentials: {scheme_name: secret_value} collected from the UI.
        Returns (headers, query_params) attached to every protected request.
        """
        headers: dict[str, str] = {}
        query: dict[str, str] = {}
        for scheme_name, value in credentials.items():
            scheme = self.parsed_spec.security_schemes.get(scheme_name)
            if not scheme or not value:
                continue
            if scheme.type in (SecuritySchemeType.HTTP_BEARER, SecuritySchemeType.OAUTH2, SecuritySchemeType.OPENID_CONNECT):
                headers["Authorization"] = f"Bearer {value}"
            elif scheme.type == SecuritySchemeType.HTTP_BASIC:
                headers["Authorization"] = f"Basic {value}"
            elif scheme.type == SecuritySchemeType.API_KEY:
                if scheme.location == "query":
                    query[scheme.param_name or scheme.name] = value
                else:
                    headers[scheme.param_name or scheme.name] = value
        return headers, query
